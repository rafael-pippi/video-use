"""Cut every speech gap out of a video and remap word timestamps.

Transcript-aware silence cutting for the remotion-captions skill:

  1. Read a word-level transcript (ElevenLabs Scribe JSON, the Scribe-like
     JSON written by template/transcribe.mjs, or a Remotion Caption[] array).
  2. Find cut candidates from BOTH signals and union them: inter-word gaps
     >= --gap seconds in the transcript AND audio silences from ffmpeg
     silencedetect (whisper.cpp tiles token timestamps across pauses, so
     transcript gaps alone under-detect; silencedetect alone fails under
     music beds — the union covers both). Every cut region is clipped to
     word boundaries (Hard Rule 6: never cut inside a word) and shrunk by
     the edge pads (Hard Rule 7: 30-200ms window).
  3. Extract each segment with 30ms audio fades (Hard Rule 3), lossless
     -c copy concat (Hard Rule 2) -> cut.mp4.
  4. Remap every word to the output timeline (Hard Rule 5:
     out = word.start - segment_start + segment_offset) and write
     captions.json as Remotion Caption[] plus meta.json for the template's
     calculateMetadata.

Usage:
    python cut_silences.py <video> --transcript <transcript.json> \
        [--edit-dir <dir>] [--gap 0.5] [--pad-before 0.08] [--pad-after 0.12] \
        [--remotion-public <template>/public]

Outputs (in --edit-dir, default <video_parent>/edit):
    cut.mp4         silence-cut video (source resolution/fps preserved)
    captions.json   Remotion Caption[] on the output timeline
    meta.json       {src, width, height, fps, duration}
    cut_edl.json    kept ranges + removal report
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def ffprobe_props(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den or 1)
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": round(fps, 3),
        "duration": float(data["format"]["duration"]),
    }


def load_words(transcript_path: Path) -> list[dict]:
    """Normalize any supported transcript format to [{text, start, end}]."""
    data = json.loads(transcript_path.read_text())
    words: list[dict] = []
    if isinstance(data, dict) and "words" in data:
        # Scribe / transcribe.mjs format (seconds)
        for w in data["words"]:
            if w.get("type") not in (None, "word"):
                continue
            text = (w.get("text") or "").strip()
            if not text or w.get("start") is None or w.get("end") is None:
                continue
            words.append({"text": text, "start": float(w["start"]), "end": float(w["end"])})
    elif isinstance(data, list):
        # Remotion Caption[] (milliseconds)
        for c in data:
            text = (c.get("text") or "").strip()
            if not text:
                continue
            words.append({"text": text, "start": c["startMs"] / 1000.0, "end": c["endMs"] / 1000.0})
    else:
        sys.exit(f"unrecognized transcript format: {transcript_path}")
    words.sort(key=lambda w: w["start"])
    return words


def detect_silences(video: Path, noise_db: float, min_silence: float) -> list[list[float]]:
    """Audio silences via ffmpeg silencedetect. Returns [[start, end], ...]."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
         "-vn", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silences: list[list[float]] = []
    start = None
    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            start = float(line.rsplit("silence_start:", 1)[1].split("|")[0])
        elif "silence_end:" in line and start is not None:
            end = float(line.rsplit("silence_end:", 1)[1].split("|")[0])
            silences.append([start, end])
            start = None
    return silences


def repair_word_timestamps(words: list[dict], silences: list[list[float]]) -> list[dict]:
    """Snap word spans out of audio-verified silences.

    whisper.cpp tiles token timestamps wall-to-wall, so a word 'claims' the
    pause around it (e.g. a 2.3s span for a 0.3s word). Physics wins: a
    silencedetect interval contains no speech, so any word overlap is
    timestamp drift. Keep the largest non-silent piece of each word's span.
    Words with no non-silent piece (hallucinated/breath tokens) keep their
    original span. Scribe timestamps are barely affected (drift < pads).
    """
    if not silences:
        return words
    repaired: list[dict] = []
    for w in words:
        pieces = [[w["start"], w["end"]]]
        for s, e in silences:
            if e <= w["start"] or s >= w["end"]:
                continue
            nxt = []
            for p in pieces:
                if e <= p[0] or s >= p[1]:
                    nxt.append(p)
                    continue
                if p[0] < s:
                    nxt.append([p[0], s])
                if e < p[1]:
                    nxt.append([e, p[1]])
            pieces = nxt
        pieces = [p for p in pieces if p[1] - p[0] > 0.02]
        if pieces:
            best = max(pieces, key=lambda p: p[1] - p[0])
            repaired.append({**w, "start": best[0], "end": best[1]})
        else:
            repaired.append(dict(w))
    repaired.sort(key=lambda w: w["start"])
    return repaired


def _subtract_intervals(intervals: list[list[float]], holes: list[list[float]]) -> list[list[float]]:
    """Interval-set subtraction: intervals minus holes. Both sorted [s, e] lists."""
    out: list[list[float]] = []
    for s, e in intervals:
        pieces = [[s, e]]
        for hs, he in holes:
            if he <= s or hs >= e:
                continue
            next_pieces: list[list[float]] = []
            for ps, pe in pieces:
                if he <= ps or hs >= pe:
                    next_pieces.append([ps, pe])
                    continue
                if ps < hs:
                    next_pieces.append([ps, hs])
                if he < pe:
                    next_pieces.append([he, pe])
            pieces = next_pieces
        out.extend(pieces)
    return out


def _merge_intervals(intervals: list[list[float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for r in sorted(intervals):
        if merged and r[0] <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], r[1])
        else:
            merged.append(list(r))
    return merged


def build_segments(
    words: list[dict],
    duration: float,
    gap: float,
    pad_before: float,
    pad_after: float,
    silences: list[list[float]] | None = None,
    carve: list[list[float]] | None = None,
    min_cut: float = 0.2,
    carve_margin: float = 0.12,
) -> list[dict]:
    """Compute keep-ranges from the union of transcript gaps and audio
    silences, clipped to word boundaries and shrunk by the edge pads.

    `carve` (permissive-threshold silences) punches holes in the word-span
    protection: whisper.cpp stretches a word's timestamps across real pauses,
    and without carving those pauses are unremovable. Each carve interval is
    shrunk by carve_margin on both sides before it weakens protection, so a
    quiet word tail is never clipped. Cuts smaller than min_cut are not worth
    the boundary risk."""
    silences = silences or []
    carve = carve or []

    # Candidate cut regions: transcript gaps + head/tail dead air + audio
    # silences (strict), + permissive silences long enough to qualify as gaps.
    regions: list[list[float]] = []
    for a, b in zip(words, words[1:]):
        if b["start"] - a["end"] >= gap:
            regions.append([a["end"], b["start"]])
    if words[0]["start"] > 0:
        regions.append([0.0, words[0]["start"]])
    if duration > words[-1]["end"]:
        regions.append([words[-1]["end"], duration])
    regions.extend([list(s) for s in silences])
    regions.extend([list(c) for c in carve if c[1] - c[0] >= gap])
    merged = _merge_intervals(regions)

    # Protection = word spans minus margin-shrunk carve silences. Never cut
    # inside actual speech; do allow cutting measured silence that whisper
    # tiled a word span across.
    #
    # Word-core rule: soft-spoken words (a whispered sign-off, a trailing
    # syllable) can sit entirely below the permissive floor and read as
    # "silence". Whisper transcribed a word there, so audio exists: if the
    # carve holes would leave less than 0.12s of a word's span protected,
    # keep that word's full span protected instead of trusting the carve.
    holes = [[s + carve_margin, e - carve_margin]
             for s, e in carve if (e - s) > 2 * carve_margin + 0.05]
    protected: list[list[float]] = []
    for w in words:
        pieces = _subtract_intervals([[w["start"], w["end"]]], holes)
        if sum(e - s for s, e in pieces) < 0.12:
            protected.append([w["start"], w["end"]])
        else:
            protected.extend(pieces)
    protected = _merge_intervals(protected)

    clipped = sorted(_subtract_intervals(merged, protected))

    # Shrink by pads (keep air around speech) and drop slivers.
    cuts: list[list[float]] = []
    for s, e in clipped:
        s2 = s if s <= 1e-6 else s + pad_after
        e2 = e if e >= duration - 1e-6 else e - pad_before
        if e2 - s2 >= min_cut:
            cuts.append([s2, e2])

    # Complement -> keep segments, then assign words (midpoint, falling back
    # to max overlap for words whose span straddles a carved cut).
    segments: list[dict] = []
    cursor = 0.0
    for s, e in cuts + [[duration, duration]]:
        if s - cursor > 1e-3:
            segments.append({"start": cursor, "end": s, "words": []})
        cursor = max(cursor, e)
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        home = None
        for seg in segments:
            if seg["start"] - 1e-6 <= mid <= seg["end"] + 1e-6:
                home = seg
                break
        if home is None and segments:
            home = max(segments, key=lambda s: min(s["end"], w["end"]) - max(s["start"], w["start"]))
        if home is not None:
            home["words"].append(w)
    return segments


def extract_segment(source: Path, start: float, end: float, out_path: Path, fps: float) -> None:
    duration = end - start
    fade_out_start = max(0.0, duration - 0.03)
    af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03"
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-af", af,
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", f"{fps:g}",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def concat_segments(paths: list[Path], out_path: Path, work_dir: Path) -> None:
    concat_list = work_dir / "_concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in paths))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", "-movflags", "+faststart", str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    concat_list.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Cut speech gaps and remap captions to the output timeline")
    ap.add_argument("video", type=Path)
    ap.add_argument("--transcript", type=Path, required=True, help="Word-level transcript JSON")
    ap.add_argument("--edit-dir", type=Path, default=None, help="Output dir (default <video_parent>/edit)")
    ap.add_argument("--gap", type=float, default=0.5, help="Min silence (s) between words to cut (default 0.5)")
    ap.add_argument("--noise-db", type=float, default=-32.0,
                    help="silencedetect noise floor in dB (default -32)")
    ap.add_argument("--carve-db", type=float, default=None,
                    help="Permissive noise floor for carving pauses out of stretched "
                         "word spans (default noise_db + 6)")
    ap.add_argument("--no-carve", action="store_true",
                    help="Disable stretched-word pause carving")
    ap.add_argument("--no-silencedetect", action="store_true",
                    help="Use transcript gaps only (skip ffmpeg silencedetect)")
    ap.add_argument("--pad-before", type=float, default=0.08, help="Padding before first word (default 0.08)")
    ap.add_argument("--pad-after", type=float, default=0.12, help="Padding after last word (default 0.12)")
    ap.add_argument("--remotion-public", type=Path, default=None,
                    help="If set, copy cut.mp4 + captions.json + meta.json into this Remotion public/ dir")
    args = ap.parse_args()

    if not 0.03 <= args.pad_before <= 0.2 or not 0.03 <= args.pad_after <= 0.2:
        sys.exit("padding must stay in the 30-200ms working window (Hard Rule 7)")

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")
    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    props = ffprobe_props(video)
    words = load_words(args.transcript.resolve())
    if not words:
        sys.exit("transcript has no words")

    silences = [] if args.no_silencedetect else detect_silences(video, args.noise_db, args.gap)
    words = repair_word_timestamps(words, silences)
    carve_db = args.carve_db if args.carve_db is not None else args.noise_db + 6
    carve = ([] if (args.no_silencedetect or args.no_carve)
             else detect_silences(video, carve_db, 0.4))
    segments = build_segments(words, props["duration"], args.gap, args.pad_before,
                              args.pad_after, silences=silences, carve=carve)

    kept = sum(s["end"] - s["start"] for s in segments)
    removed = props["duration"] - kept
    print(f"source: {props['duration']:.2f}s, {len(words)} words, "
          f"{len(silences)} audio silence(s) >= {args.gap}s, "
          f"{len(carve)} carve silence(s) @ {carve_db:g}dB")
    print(f"keeping {len(segments)} segment(s), cutting {removed:.2f}s of silence "
          f"({removed / props['duration'] * 100:.0f}%)")

    clips_dir = edit_dir / "clips_cut"
    clips_dir.mkdir(exist_ok=True)
    seg_paths: list[Path] = []
    for i, seg in enumerate(segments):
        quote = (f"\"{seg['words'][0]['text']} … {seg['words'][-1]['text']}\""
                 if seg["words"] else "(sem fala transcrita)")
        print(f"  [{i:02d}] {seg['start']:7.2f}-{seg['end']:7.2f}  ({seg['end'] - seg['start']:5.2f}s)  {quote}")
        p = clips_dir / f"seg_{i:02d}.mp4"
        extract_segment(video, seg["start"], seg["end"], p, props["fps"])
        seg_paths.append(p)

    cut_path = edit_dir / "cut.mp4"
    concat_segments(seg_paths, cut_path, edit_dir)

    # Remap word times to the output timeline (Hard Rule 5).
    captions = []
    offset = 0.0
    for seg in segments:
        seg_dur = seg["end"] - seg["start"]
        for w in seg["words"]:
            start = max(0.0, w["start"] - seg["start"]) + offset
            end = min(seg_dur, w["end"] - seg["start"]) + offset
            captions.append({
                # Leading space: Remotion caption pagination expects it.
                "text": " " + w["text"],
                "startMs": round(start * 1000),
                "endMs": round(max(start, end) * 1000),
                "timestampMs": round((start + max(start, end)) / 2 * 1000),
                "confidence": None,
            })
        offset += seg_dur

    out_props = ffprobe_props(cut_path)
    fps = round(out_props["fps"]) or 30
    meta = {
        "src": "cut.mp4",
        "width": out_props["width"],
        "height": out_props["height"],
        "fps": fps,
        "duration": out_props["duration"],
    }

    (edit_dir / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=1))
    (edit_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    (edit_dir / "cut_edl.json").write_text(json.dumps({
        "source": str(video),
        "gap_threshold_s": args.gap,
        "pad_before_s": args.pad_before,
        "pad_after_s": args.pad_after,
        "ranges": [{"start": round(s["start"], 3), "end": round(s["end"], 3)} for s in segments],
        "removed_s": round(removed, 3),
        "output_duration_s": round(out_props["duration"], 3),
    }, indent=2))

    print(f"cut.mp4: {out_props['duration']:.2f}s  captions.json: {len(captions)} words")

    if args.remotion_public:
        pub = args.remotion_public.resolve()
        pub.mkdir(parents=True, exist_ok=True)
        for name in ("cut.mp4", "captions.json", "meta.json"):
            shutil.copy2(edit_dir / name, pub / name)
        print(f"copied cut.mp4 + captions.json + meta.json → {pub}")


if __name__ == "__main__":
    main()
