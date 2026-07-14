import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {Caption} from '@remotion/captions';
import {msToFrame, Page, pageByWords} from './utils';
import {OneWord} from './styles/OneWord';
import {ThreeWords} from './styles/ThreeWords';
import {Kinetic} from './styles/Kinetic';
import {Highlight} from './styles/Highlight';
import {Karaoke} from './styles/Karaoke';
import {Boxed} from './styles/Boxed';

export type CaptionStyle =
  | 'one-word'
  | 'three-words'
  | 'kinetic'
  | 'highlight'
  | 'karaoke'
  | 'boxed';

export type CaptionedVideoProps = {
  src: string;
  captions: Caption[];
  captionStyle: CaptionStyle;
  accent: string;
};

const WORDS_PER_PAGE: Record<CaptionStyle, number> = {
  'one-word': 1,
  'three-words': 3,
  kinetic: 4,
  highlight: 4,
  karaoke: 5,
  boxed: 3,
};

const STYLE_COMPONENTS: Record<CaptionStyle, React.FC<{page: Page; accent: string}>> = {
  'one-word': OneWord,
  'three-words': ThreeWords,
  kinetic: Kinetic,
  highlight: Highlight,
  karaoke: Karaoke,
  boxed: Boxed,
};

export const CaptionedVideo: React.FC<CaptionedVideoProps> = ({
  src,
  captions,
  captionStyle,
  accent,
}) => {
  const {fps} = useVideoConfig();
  const pages = React.useMemo(
    () => pageByWords(captions, WORDS_PER_PAGE[captionStyle]),
    [captions, captionStyle],
  );
  const StyleComponent = STYLE_COMPONENTS[captionStyle];
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <OffthreadVideo src={staticFile(src)} />
      {pages.map((page, i) => {
        const from = msToFrame(page.startMs, fps);
        const durationInFrames = Math.max(1, msToFrame(page.endMs, fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={durationInFrames}>
            <StyleComponent page={page} accent={accent} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
