import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter} from '../fonts';
import {Page} from '../utils';

// Style 2 — "three-words": 3-word pages, the word being spoken lights up
// in the accent color.
export const ThreeWords: React.FC<{page: Page; accent: string}> = ({page, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const t = page.startMs + (frame / fps) * 1000;
  const pop = spring({frame, fps, config: {damping: 15, mass: 0.5}, durationInFrames: 7});
  return (
    <CaptionContainer>
      <div
        style={{
          fontFamily: inter.fontFamily,
          fontWeight: 900,
          fontSize: width * 0.075,
          lineHeight: 1.2,
          textTransform: 'uppercase',
          textAlign: 'center',
          transform: `scale(${0.85 + 0.15 * pop})`,
          WebkitTextStroke: `${Math.max(3, width * 0.007)}px black`,
          paintOrder: 'stroke fill',
          textShadow: '0 5px 20px rgba(0,0,0,0.55)',
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = t >= tok.fromMs && t < tok.toMs;
          return (
            <span
              key={i}
              style={{
                color: active ? accent : 'white',
                display: 'inline-block',
                transform: active ? 'scale(1.12)' : 'scale(1)',
                marginRight: i < page.tokens.length - 1 ? '0.28em' : 0,
              }}
            >
              {tok.text}
            </span>
          );
        })}
      </div>
    </CaptionContainer>
  );
};
