import type {Caption} from '@remotion/captions';

export type Token = {text: string; fromMs: number; toMs: number};
export type Page = {startMs: number; endMs: number; tokens: Token[]};

const SENTENCE_END = /[.!?…]$/;

// Word-count pagination (createTikTokStyleCaptions groups by time, but the
// styles here need exact word counts: 1, 3, 4, 5 words per page).
export const pageByWords = (
  captions: Caption[],
  maxWords: number,
  maxGapMs = 1200,
): Page[] => {
  const pages: Page[] = [];
  let current: Token[] = [];

  const close = () => {
    if (current.length === 0) {
      return;
    }
    pages.push({
      startMs: current[0].fromMs,
      endMs: current[current.length - 1].toMs,
      tokens: current,
    });
    current = [];
  };

  for (const c of captions) {
    const text = c.text.trim();
    if (!text) {
      continue;
    }
    const prev = current[current.length - 1];
    if (prev && (c.startMs - prev.toMs > maxGapMs || SENTENCE_END.test(prev.text))) {
      close();
    }
    current.push({text, fromMs: c.startMs, toMs: c.endMs});
    if (current.length >= maxWords) {
      close();
    }
  }
  close();

  // Extend each page's visible window toward the next page (capped) so
  // captions don't flicker off during the short gaps between words.
  for (let i = 0; i < pages.length; i++) {
    const next = pages[i + 1];
    const cap = pages[i].endMs + 500;
    pages[i].endMs = next ? Math.min(next.startMs, cap) : cap;
  }
  return pages;
};

export const msToFrame = (ms: number, fps: number): number =>
  Math.max(0, Math.round((ms / 1000) * fps));

// Shrink the base font size so `text` fits within `maxWidth` (rough
// 0.62em average glyph width for heavy sans weights).
export const fitFontSize = (text: string, maxWidth: number, base: number): number =>
  Math.min(base, maxWidth / (0.62 * Math.max(1, text.length)));

// The keyword of a page: the longest token with >= 4 chars (ties -> later
// word, which tends to carry the emphasis in speech).
export const keywordIndex = (tokens: Token[]): number => {
  let best = -1;
  let bestLen = 3;
  tokens.forEach((t, i) => {
    const len = t.text.replace(/[^\p{L}\p{N}]/gu, '').length;
    if (len >= bestLen) {
      best = i;
      bestLen = len;
    }
  });
  return best;
};
