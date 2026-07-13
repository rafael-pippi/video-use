// Local word-level transcription via whisper.cpp (@remotion/install-whisper-cpp).
// Fallback for when ELEVENLABS_API_KEY is not available. Produces the same
// Scribe-like transcript shape that video-use helpers consume:
//   { words: [{text, start, end, type: "word"}], text: "..." }
//
// Run from inside an npm-installed copy of this template:
//   node transcribe.mjs <video> [--model small] [--language auto|pt|en|...]
//        [--out <edit_dir>/transcripts/<stem>.json]
//
// whisper.cpp + models are cached in ~/.cache/whisper-cpp-remotion and only
// downloaded/built on first use.

import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, writeFileSync, rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  downloadWhisperModel,
  installWhisperCpp,
  toCaptions,
  transcribe,
} from '@remotion/install-whisper-cpp';

const WHISPER_VERSION = '1.5.5';

const args = process.argv.slice(2);
const positional = args.filter((a) => !a.startsWith('--'));
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

const video = positional[0];
if (!video || !existsSync(video)) {
  console.error('usage: node transcribe.mjs <video> [--model small] [--language auto] [--out path.json]');
  process.exit(1);
}

const model = flag('model', 'small');
const language = flag('language', 'auto');
const stem = path.basename(video).replace(/\.[^.]+$/, '');
const outPath = path.resolve(
  flag('out', path.join(path.dirname(path.resolve(video)), 'edit', 'transcripts', `${stem}.json`)),
);

if (existsSync(outPath)) {
  console.log(`cached: ${outPath}`);
  process.exit(0);
}

// Do NOT pre-create whisperDir — installWhisperCpp treats an existing dir
// without the built binary as a corrupted install.
const whisperDir = path.join(os.homedir(), '.cache', 'whisper-cpp-remotion', WHISPER_VERSION);

console.log(`installing whisper.cpp ${WHISPER_VERSION} → ${whisperDir} (cached after first run)`);
await installWhisperCpp({to: whisperDir, version: WHISPER_VERSION});
await downloadWhisperModel({model, folder: whisperDir});

// whisper.cpp wants 16kHz mono WAV.
const wav = path.join(os.tmpdir(), `${stem}-${process.pid}-16k.wav`);
const ff = spawnSync('ffmpeg', [
  '-y', '-i', video, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav,
]);
if (ff.status !== 0) {
  console.error(ff.stderr?.toString().slice(-2000));
  process.exit(1);
}

console.log(`transcribing ${path.basename(video)} (model=${model}, language=${language})`);
const whisperCppOutput = await transcribe({
  model,
  whisperPath: whisperDir,
  whisperCppVersion: WHISPER_VERSION,
  inputPath: wav,
  tokenLevelTimestamps: true,
  language,
});
rmSync(wav, {force: true});

const {captions} = toCaptions({whisperCppOutput});

const words = captions
  .map((c) => ({
    text: c.text.trim(),
    start: c.startMs / 1000,
    end: c.endMs / 1000,
    type: 'word',
  }))
  .filter((w) => w.text.length > 0);

mkdirSync(path.dirname(outPath), {recursive: true});
writeFileSync(
  outPath,
  JSON.stringify(
    {
      source: 'whisper.cpp',
      model,
      language: whisperCppOutput.result?.language ?? language,
      text: words.map((w) => w.text).join(' '),
      words,
    },
    null,
    2,
  ),
);
console.log(`saved: ${outPath} (${words.length} words)`);
