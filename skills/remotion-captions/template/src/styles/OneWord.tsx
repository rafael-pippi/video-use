import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter} from '../fonts';
import {fitFontSize, Page} from '../utils';

// Style 1 — "one-word": a single word at a time, punchy spring pop.
export const OneWord: React.FC<{page: Page; accent: string}> = ({page}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const token = page.tokens[0];
  const pop = spring({frame, fps, config: {damping: 13, mass: 0.6}, durationInFrames: 9});
  const fontSize = fitFontSize(token.text, width * 0.88, width * 0.13);
  return (
    <CaptionContainer>
      <div
        style={{
          fontFamily: inter.fontFamily,
          fontWeight: 900,
          fontSize,
          lineHeight: 1.1,
          color: 'white',
          textTransform: 'uppercase',
          textAlign: 'center',
          transform: `scale(${0.7 + 0.3 * pop})`,
          WebkitTextStroke: `${Math.max(4, width * 0.009)}px black`,
          paintOrder: 'stroke fill',
          textShadow: '0 6px 24px rgba(0,0,0,0.55)',
        }}
      >
        {token.text}
      </div>
    </CaptionContainer>
  );
};
