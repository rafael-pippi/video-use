import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter} from '../fonts';
import {msToFrame, Page} from '../utils';

// Style 6 — "boxed": 3-word pages; a rounded accent box snaps onto the word
// being spoken (the classic creator/"Hormozi" look).
export const Boxed: React.FC<{page: Page; accent: string}> = ({page, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const t = page.startMs + (frame / fps) * 1000;
  return (
    <CaptionContainer>
      <div
        style={{
          fontFamily: inter.fontFamily,
          fontWeight: 900,
          fontSize: width * 0.07,
          lineHeight: 1.45,
          textTransform: 'uppercase',
          textAlign: 'center',
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = t >= tok.fromMs && t < tok.toMs;
          const activeStart = msToFrame(tok.fromMs - page.startMs, fps);
          const snap = spring({
            frame: frame - activeStart,
            fps,
            config: {damping: 14, mass: 0.5},
            durationInFrames: 6,
          });
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                position: 'relative',
                color: 'white',
                padding: '0.06em 0.22em',
                borderRadius: width * 0.012,
                backgroundColor: active ? accent : 'transparent',
                transform: active ? `scale(${0.9 + 0.14 * snap})` : 'scale(1)',
                WebkitTextStroke: active ? undefined : `${Math.max(3, width * 0.006)}px black`,
                paintOrder: 'stroke fill',
                textShadow: active ? 'none' : '0 4px 16px rgba(0,0,0,0.55)',
                marginRight: i < page.tokens.length - 1 ? '0.12em' : 0,
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
