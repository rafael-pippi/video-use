import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptionContainer} from '../CaptionContainer';
import {inter, playfair} from '../fonts';
import {keywordIndex, Page} from '../utils';

// Style 4 — "highlight": ~4-word pages; the keyword of the phrase is set
// in a contrasting serif italic font and the accent color.
export const Highlight: React.FC<{page: Page; accent: string}> = ({page, accent}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const kw = keywordIndex(page.tokens);
  const enter = spring({frame, fps, config: {damping: 16, mass: 0.6}, durationInFrames: 8});
  const opacity = interpolate(frame, [0, 4], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <CaptionContainer>
      <div
        style={{
          fontSize: width * 0.066,
          lineHeight: 1.3,
          textAlign: 'center',
          opacity,
          transform: `translateY(${(1 - enter) * 30}px)`,
          textShadow: '0 5px 20px rgba(0,0,0,0.6)',
        }}
      >
        {page.tokens.map((tok, i) => {
          const isKeyword = i === kw;
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                fontFamily: isKeyword ? playfair.fontFamily : inter.fontFamily,
                fontStyle: isKeyword ? 'italic' : 'normal',
                fontWeight: isKeyword ? 800 : 700,
                fontSize: isKeyword ? '1.25em' : '1em',
                color: isKeyword ? accent : 'white',
                textTransform: isKeyword ? 'none' : 'uppercase',
                WebkitTextStroke: isKeyword ? undefined : `${Math.max(2, width * 0.004)}px black`,
                paintOrder: 'stroke fill',
                marginRight: i < page.tokens.length - 1 ? '0.28em' : 0,
                verticalAlign: 'baseline',
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
