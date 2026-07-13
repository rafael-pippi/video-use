"""Cut every speech gap out of a video and remap word timestamps.

Transcript-aware silence cutting for the remotion-captions skill:

  1. Read a word-level transcript (ElevenLabs Scribe JSON, the Scribe-like
     JSON written by template/transcribe.mjs, or a Remotion Caption[] array).
  2. Group words into speech segments wherever the inter-word gap is below
     --gap seconds. Pad each segment edge (Hard Rule 7: 30-200ms window),
     never cutting inside a word (Hard Rule 6).
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


def build_segments(
    words: list[dict],
    duration: float,
    gap: float,
    pad_before: float,
    pad_after: float,
) -> list[dict]:
    """Group words into padded keep-ranges. Merge ranges that (after padding)
    touch or leave a sliver smaller than 120ms — a cut that small is not
    worth the boundary risk."""
    groups: list[list[dict]] = []
    current = [words[0]]
    for w in words[1:]:
        if w["start"] - current[-1]["end"] >= gap:
            groups.append(current)
            current = [w]
        else:
            current.append(w)
    groups.append(current)

    segments = []
    for g in groups:
        start = max(0.0, g[0]["start"] - pad_before)
        end = min(duration, g[-1]["end"] + pad_after)
        segments.append({"start": start, "end": end, "words": g})

    merged = [segments[0]]
    for seg in segments[1:]:
        if seg["start"] - merged[-1]["end"] < 0.12:
            merged[-1]["end"] = seg["end"]
            merged[-1]["words"].extend(seg["words"])
        else:
            merged.append(seg)
    return merged


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

    segments = build_segments(words, props["duration"], args.gap, args.pad_before, args.pad_after)

    kept = sum(s["end"] - s["start"] for s in segments)
    removed = props["duration"] - kept
    print(f"source: {props['duration']:.2f}s, {len(words)} words")
    print(f"keeping {len(segments)} segment(s), cutting {removed:.2f}s of silence "
          f"({removed / props['duration'] * 100:.0f}%)")

    clips_dir = edit_dir / "clips_cut"
    clips_dir.mkdir(exist_ok=True)
    seg_paths: list[Path] = []
    for i, seg in enumerate(segments):
        print(f"  [{i:02d}] {seg['start']:7.2f}-{seg['end']:7.2f}  ({seg['end'] - seg['start']:5.2f}s)  "
              f"\"{seg['words'][0]['text']} … {seg['words'][-1]['text']}\"")
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
