---
name: remotion-captions
description: Cut every speech gap out of a video and burn animated word-level captions with Remotion. Six shipped caption styles — one word at a time, 3-word pages, kinetic fly-in, keyword highlight in a contrast font, karaoke fill, boxed active word — all driven by the same transcript, all customizable.
---

# Remotion Captions (silence-cut + animated captions)

Vendored sub-skill of `video-use`. Use it when the user wants the classic
short-form treatment: **remove all pauses** and **burn animated, word-synced
captions** rendered with [Remotion](https://www.remotion.dev/docs/ai/skills).

Everything inherits the video-use Hard Rules: never cut inside a word,
30–200ms edge padding, 30ms audio fades, lossless concat, output-timeline
timestamp remapping.

## Pipeline

```
transcript (word-level)                 Remotion template (this skill)
        │                                        │
cut_silences.py ── cut.mp4 ─────────────▶ public/cut.mp4
        ├───────── captions.json ───────▶ public/captions.json
        └───────── meta.json ───────────▶ public/meta.json
                                                 │
                              npx remotion render <StyleId> out/final.mp4
```

1. **Transcribe** (word-level, cached in `<edit>/transcripts/`):
   - Preferred: `helpers/transcribe.py` at the video-use root (ElevenLabs Scribe).
   - No API key? Local fallback from inside the installed template:
     `node transcribe.mjs <video> --model small --language auto`
     (whisper.cpp via `@remotion/install-whisper-cpp`; binaries + models cached
     in `~/.cache/whisper-cpp-remotion`). Use `--language pt` etc. when known —
     it beats auto-detection on short clips.
2. **Scaffold** the Remotion project once per editing session:
   `cp -r <this skill>/template/. <edit>/remotion/ && cd <edit>/remotion && npm install`
3. **Cut silences + remap captions**:
   ```
   python <this skill>/helpers/cut_silences.py <video> \
     --transcript <edit>/transcripts/<stem>.json \
     --edit-dir <edit> \
     --remotion-public <edit>/remotion/public
   ```
   Defaults: cut gaps ≥ 0.5s (`--gap`), pad 80ms before / 120ms after each
   speech segment (`--pad-before` / `--pad-after`). Tighten `--gap` to 0.35–0.4
   for aggressive social pacing; keep ≥ 0.5 for narrative content.
4. **Render** (from `<edit>/remotion/`):
   ```
   npx remotion render <StyleId> ../final_<style>.mp4
   ```
   Preview a strip first when iterating: `--frames=0-150`.

## The six styles

| Composition ID | Style | What it does |
|---|---|---|
| `OneWord` | 1 palavra por vez | One huge uppercase word, spring pop, black stroke |
| `ThreeWords` | 3 palavras | 3-word pages, the spoken word lights up in the accent color |
| `Kinetic` | com movimento | Words fly in one by one at their spoken timestamp (slide-up + tilt springs) |
| `Highlight` | palavra de destaque | ~4-word pages; the phrase keyword set in Playfair Display italic + accent, rest in Inter |
| `Karaoke` | preenchimento | Whole phrase visible dimmed; each word fills left-to-right as spoken |
| `Boxed` | caixa ativa | Rounded accent box snaps onto the spoken word (creator/"Hormozi" look) |

All take the same props: `{src, captions, captionStyle, accent}` — override
the accent per render with `--props='{"accent":"#FF5A00"}'`.

## How the template resolves inputs

`calculateMetadata` in `src/Root.tsx` fetches `public/meta.json` (width /
height / fps / duration written by `cut_silences.py` from ffprobe) and
`public/captions.json`. Duration, dimensions and fps therefore always match
the cut video — no browser codec probing, works for any aspect ratio. The
video itself is drawn with `OffthreadVideo` (ffmpeg-decoded, codec-safe).

`captions.json` is a Remotion `Caption[]` (`@remotion/captions`):
`{text: " word", startMs, endMs, timestampMs, confidence}` — times already on
the **output** timeline of `cut.mp4`. Word texts keep a leading space per the
Remotion caption convention.

Pagination is word-count based (`src/utils.ts: pageByWords`) — 1/3/4/5 words
per page depending on style, breaking early on sentence punctuation or gaps
> 1.2s. Each page's visible window extends to the next page's start (max
+500ms) so captions don't flicker between words.

## Customizing (artistic freedom applies)

- **Accent color**: `--props='{"accent":"#00E5FF"}'` — no rebuild needed.
- **Fonts**: `src/fonts.ts` bundles Inter + Playfair Display via `@fontsource`
  packages — no network at render time (headless Chrome often can't reach
  Google Fonts through sandbox proxies). Swap by installing another
  `@fontsource/<font>` and changing the imports + family names there.
- **Placement**: `src/CaptionContainer.tsx`. Vertical videos keep captions
  ~30% up from the bottom — that is a platform safe-zone rule (Reels/TikTok
  UI), not taste. Do not go below ~25% on vertical without a reason.
- **New style**: add a component under `src/styles/` taking
  `{page: Page; accent: string}`, register it in `CaptionedVideo.tsx`
  (`STYLE_COMPONENTS` + `WORDS_PER_PAGE`) and `Root.tsx` (`STYLES`).
- **Highlight keyword choice**: heuristic in `src/utils.ts: keywordIndex`
  (longest word ≥ 4 chars, later wins). Replace with an explicit list if the
  user names the words that matter.

## Verification (before showing the user)

- `ffprobe` the render: duration must equal `meta.json`'s duration ±0.1s.
- Extract 3–5 frames at caption times (`ffmpeg -ss <t> -i final.mp4 -frames:v 1`)
  and check: caption readable, inside safe zone, active-word state correct.
- Listen for pops at cut boundaries (or check waveform via the root skill's
  `timeline_view.py` against the rendered output).
- If whisper timestamps look shifted (captions consistently early/late),
  re-transcribe with a larger model before touching the components.

## Gotchas

- All `@remotion/*` packages + `remotion` must be the **same version**
  (`npx remotion versions` to check). Install/update them together.
- First render downloads Remotion's headless Chrome; first `transcribe.mjs`
  run downloads + builds whisper.cpp. Both cached afterwards.
- Rendering re-encodes the video once — that is inherent to burning Remotion
  captions. Do color grading on the segments *before* this stage if needed
  (EDL `grade` in the root skill), not after.
- `cut.mp4` preserves source resolution and fps; portrait stays portrait.
