import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';

// Vertical platforms (Reels / TikTok / Shorts) cover the bottom ~25-30% of
// the frame with UI (caption, username, action rail). Captions sit above
// that zone; on landscape a smaller offset is enough.
export const CaptionContainer: React.FC<{children: React.ReactNode}> = ({children}) => {
  const {width, height} = useVideoConfig();
  const vertical = height > width;
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingLeft: width * 0.06,
        paddingRight: width * 0.06,
        paddingBottom: vertical ? height * 0.3 : height * 0.12,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
