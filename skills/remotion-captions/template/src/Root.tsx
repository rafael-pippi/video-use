import React from 'react';
import {CalculateMetadataFunction, Composition, staticFile} from 'remotion';
import {CaptionedVideo, CaptionedVideoProps, CaptionStyle} from './CaptionedVideo';

// One composition per caption style, all reading the same inputs from
// public/: cut.mp4 (silence-cut video), captions.json (output-timeline
// word captions) and meta.json (width/height/fps/duration of cut.mp4).
const STYLES: {id: string; style: CaptionStyle}[] = [
  {id: 'OneWord', style: 'one-word'},
  {id: 'ThreeWords', style: 'three-words'},
  {id: 'Kinetic', style: 'kinetic'},
  {id: 'Highlight', style: 'highlight'},
  {id: 'Karaoke', style: 'karaoke'},
  {id: 'Boxed', style: 'boxed'},
];

const calculateMetadata: CalculateMetadataFunction<CaptionedVideoProps> = async ({props}) => {
  const meta = await fetch(staticFile('meta.json')).then((r) => r.json());
  const captions = await fetch(staticFile('captions.json')).then((r) => r.json());
  return {
    durationInFrames: Math.max(1, Math.round(meta.duration * meta.fps)),
    fps: meta.fps,
    width: meta.width,
    height: meta.height,
    props: {...props, src: meta.src ?? props.src, captions},
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {STYLES.map(({id, style}) => (
        <Composition
          key={id}
          id={id}
          component={CaptionedVideo}
          durationInFrames={300}
          fps={30}
          width={1080}
          height={1920}
          defaultProps={{
            src: 'cut.mp4',
            captions: [],
            captionStyle: style,
            accent: '#FFD400',
          }}
          calculateMetadata={calculateMetadata}
        />
      ))}
    </>
  );
};
