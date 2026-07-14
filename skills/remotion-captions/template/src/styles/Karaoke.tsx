import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter} from '../fonts';
import {Page} from '../utils';

// Style 5 — "karaoke": the whole phrase stays visible dimmed; each word
// fills to full white as it is spoken (left-to-right sweep inside the word).
export const Karaoke: React.FC<{page: Page; accent: string}> = ({page, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const t = page.startMs + (frame / fps) * 1000;
  const dim = 'rgba(255,255,255,0.38)';
  return (
    <CaptionContainer>
      <div
        style={{
          fontFamily: inter.fontFamily,
          fontWeight: 800,
          fontSize: width * 0.062,
          lineHeight: 1.35,
          textTransform: 'uppercase',
          textAlign: 'center',
          filter: 'drop-shadow(0 4px 14px rgba(0,0,0,0.7))',
        }}
      >
        {page.tokens.map((tok, i) => {
          const spoken = t >= tok.toMs;
          const active = t >= tok.fromMs && t < tok.toMs;
          const progress = active
            ? Math.min(1, Math.max(0, (t - tok.fromMs) / Math.max(1, tok.toMs - tok.fromMs)))
            : 0;
          const style: React.CSSProperties = {
            display: 'inline-block',
            marginRight: i < page.tokens.length - 1 ? '0.28em' : 0,
            transform: active ? 'scale(1.06)' : 'scale(1)',
          };
          if (active) {
            // Left-to-right fill sweep, synced to word progress.
            const p = (progress * 100).toFixed(1);
            style.backgroundImage = `linear-gradient(90deg, ${accent} ${p}%, ${dim} ${p}%)`;
            style.WebkitBackgroundClip = 'text';
            style.backgroundClip = 'text';
            style.color = 'transparent';
          } else {
            style.color = spoken ? 'white' : dim;
          }
          return (
            <span key={i} style={style}>
              {tok.text}
            </span>
          );
        })}
      </div>
    </CaptionContainer>
  );
};
