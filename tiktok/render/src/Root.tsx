import React from 'react';
import {Composition} from 'remotion';
import {Main, VideoProps} from './Main';

const defaults: VideoProps = {
  fps: 30,
  durationInFrames: 90,
  audio: null,
  music: null,
  hook: {text: 'ჰუკი', end: 2},
  clips: [],
  words: [],
  overlays: [],
  sfx: [],
  flashes: [],
};

export const Root: React.FC = () => (
  <Composition
    id="Main"
    component={Main}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={90}
    defaultProps={defaults}
    calculateMetadata={({props}) => ({durationInFrames: props.durationInFrames, fps: props.fps})}
  />
);
