import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter} from '../fonts';
import {msToFrame, Page} from '../utils';

// Style 3 — "kinetic": words fly in one by one at their spoken timestamp,
// sliding up with a spring and a small alternating tilt.
export const Kinetic: React.FC<{page: Page; accent: string}> = ({page, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  return (
    <CaptionContainer>
      <div
        style={{
          fontFamily: inter.fontFamily,
          fontWeight: 800,
          fontSize: width * 0.068,
          lineHeight: 1.25,
          textTransform: 'uppercase',
          textAlign: 'center',
          maxWidth: '100%',
        }}
      >
        {page.tokens.map((tok, i) => {
          const startFrame = msToFrame(tok.fromMs - page.startMs, fps);
          const s = spring({
            frame: frame - startFrame,
            fps,
            config: {damping: 12, mass: 0.7},
            durationInFrames: 10,
          });
          const visible = frame >= startFrame;
          const tilt = (i % 2 === 0 ? -1 : 1) * 5 * (1 - s);
          const isLast = i === page.tokens.length - 1;
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                opacity: visible ? s : 0,
                transform: `translateY(${(1 - s) * 70}px) rotate(${tilt}deg) scale(${0.6 + 0.4 * s})`,
                color: isLast ? accent : 'white',
                WebkitTextStroke: `${Math.max(3, width * 0.006)}px black`,
                paintOrder: 'stroke fill',
                textShadow: '0 5px 18px rgba(0,0,0,0.5)',
                marginRight: i < page.tokens.length - 1 ? '0.3em' : 0,
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
