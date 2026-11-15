import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

// ----------------------------------------------------------------- types

export type Clip = {src: string; start: number; end: number; move: 'punch' | 'push' | 'pull' | 'drift'};
export type Word = {text: string; start: number; end: number; emph: boolean; page: number};
export type Overlay = {
  type: 'emoji' | 'number' | 'card' | 'check' | 'cross';
  value?: string | number;
  prefix?: string;
  suffix?: string;
  text?: string;
  start: number;
  end: number;
  slot: number; // alternates placement so pops don't sit in the same spot
};
export type Sfx = {src: string; start: number; volume: number};
export type VideoProps = {
  fps: number;
  durationInFrames: number;
  audio: string | null;
  music: string | null;
  hook: {text: string; end: number};
  clips: Clip[];
  words: Word[];
  overlays: Overlay[];
  sfx: Sfx[];
  flashes: number[];
};

const YELLOW = '#FFE600';
const PINK = '#FF2E63';
const FONT = 'TikTokGeo';

// ------------------------------------------------------------------ font

const useFont = () => {
  const [handle] = useState(() => delayRender('font'));
  useEffect(() => {
    const face = new FontFace(FONT, `url(${staticFile('TikTokGeo.ttf')})`);
    face
      .load()
      .then((f) => {
        document.fonts.add(f);
        continueRender(handle);
      })
      .catch(() => continueRender(handle));
  }, [handle]);
};

// ----------------------------------------------------------------- clips

const ClipView: React.FC<{clip: Clip; frames: number}> = ({clip, frames}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = Math.min(1, f / Math.max(1, frames));
  let scale = 1;
  let x = 0;
  if (clip.move === 'punch') {
    const hit = spring({frame: f, fps, config: {damping: 14, stiffness: 180}});
    scale = interpolate(hit, [0, 1], [1.3, 1.0]) + p * 0.05;
  } else if (clip.move === 'push') {
    scale = 1 + p * 0.12;
  } else if (clip.move === 'pull') {
    scale = 1.14 - p * 0.12;
  } else {
    scale = 1.12;
    x = interpolate(p, [0, 1], [-45, 45]);
  }
  const style: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transform: `translateX(${x}px) scale(${scale})`,
  };
  return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      {clip.src.endsWith('.png') || clip.src.endsWith('.jpg') ? (
        <Img src={staticFile(clip.src)} style={style} />
      ) : (
        <OffthreadVideo src={staticFile(clip.src)} muted style={style} />
      )}
    </AbsoluteFill>
  );
};

const Clips: React.FC<{clips: Clip[]}> = ({clips}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {clips.map((c, i) => {
        const from = Math.round(c.start * fps);
        const frames = Math.max(1, Math.round(c.end * fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={frames} layout="none">
            <ClipView clip={c} frames={frames} />
          </Sequence>
        );
      })}
    </>
  );
};

// Darkened top/bottom so white text always reads, plus subtle vignette.
const Shade: React.FC = () => (
  <AbsoluteFill
    style={{
      background:
        'linear-gradient(180deg, rgba(0,0,0,0.45) 0%, rgba(0,0,0,0) 28%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.55) 100%)',
      boxShadow: 'inset 0 0 220px rgba(0,0,0,0.55)',
    }}
  />
);

const Flashes: React.FC<{times: number[]}> = ({times}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  let o = 0;
  for (const t of times) {
    const s = Math.round(t * fps);
    if (f >= s && f < s + 5) o = Math.max(o, interpolate(f, [s, s + 5], [0.75, 0]));
  }
  return o > 0 ? <AbsoluteFill style={{backgroundColor: 'white', opacity: o}} /> : null;
};

// ------------------------------------------------------------------ hook

const Hook: React.FC<{text: string; end: number}> = ({text, end}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const endF = Math.round(end * fps);
  if (f > endF) return null;
  const s = spring({frame: f, fps, config: {damping: 9, stiffness: 160}});
  const out = interpolate(f, [endF - 6, endF], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const shake = f < 12 ? Math.sin(f * 2.2) * (12 - f) * 0.9 : 0;
  return (
    <AbsoluteFill style={{alignItems: 'center', top: 210}}>
      <div
        style={{
          transform: `translateX(${shake}px) scale(${s * out}) rotate(-2.5deg)`,
          background: YELLOW,
          color: '#111',
          fontFamily: FONT,
          fontSize: 76,
          lineHeight: 1.25,
          padding: '26px 40px',
          borderRadius: 28,
          maxWidth: 900,
          textAlign: 'center',
          boxShadow: '0 14px 0 #000, 0 20px 50px rgba(0,0,0,0.5)',
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

// -------------------------------------------------------------- captions

const Captions: React.FC<{words: Word[]}> = ({words}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = f / fps;
  // current page = last page whose first word has started
  let page = -1;
  for (const w of words) if (w.start <= t + 0.02) page = w.page;
  if (page < 0) return null;
  const pageWords = words.filter((w) => w.page === page);
  const last = pageWords[pageWords.length - 1];
  const next = words.find((w) => w.page === page + 1);
  if (!next && t > last.end + 0.6) return null;
  const pageStart = Math.round(pageWords[0].start * fps);
  const pop = spring({frame: f - pageStart, fps, config: {damping: 12, stiffness: 220}});
  return (
    <AbsoluteFill style={{top: 1140, alignItems: 'center'}}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '22px 30px',
          maxWidth: 960,
          transform: `scale(${interpolate(pop, [0, 1], [0.6, 1])})`,
        }}
      >
        {pageWords.map((w, i) => {
          const active = t >= w.start - 0.02 && t < w.end + 0.05;
          const said = t >= w.start - 0.02;
          return (
            <span
              key={i}
              style={{
                fontFamily: FONT,
                fontSize: 104,
                lineHeight: 1.18,
                color: w.emph ? '#111' : active ? YELLOW : 'white',
                background: w.emph ? YELLOW : 'transparent',
                padding: w.emph ? '0 18px' : 0,
                borderRadius: 18,
                opacity: said ? 1 : 0.55,
                transform: `scale(${active ? 1.06 : 1}) rotate(${w.emph ? -2 : 0}deg)`,
                WebkitTextStroke: w.emph ? '0px' : '14px black',
                paintOrder: 'stroke fill',
                textShadow: w.emph ? 'none' : '0 8px 18px rgba(0,0,0,0.6)',
                boxShadow: w.emph ? '0 8px 0 #000' : 'none',
                display: 'inline-block',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// -------------------------------------------------------------- overlays

const fmt = (n: number) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

const OverlayView: React.FC<{o: Overlay; frames: number}> = ({o, frames}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const inS = spring({frame: f, fps, config: {damping: 8, stiffness: 170}});
  const outS = interpolate(f, [frames - 6, frames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const bob = Math.sin(f / 7) * 8;
  const left = o.slot % 3 === 0 ? '50%' : o.slot % 3 === 1 ? '27%' : '73%';
  const base: React.CSSProperties = {
    position: 'absolute',
    top: 700,
    left,
    transform: `translate(-50%, ${bob}px) scale(${inS * outS}) rotate(${interpolate(inS, [0, 1], [-18, 0])}deg)`,
  };
  if (o.type === 'emoji' || o.type === 'check' || o.type === 'cross') {
    const glyph = o.type === 'check' ? '✅' : o.type === 'cross' ? '❌' : String(o.value ?? '');
    return <div style={{...base, fontSize: 250, filter: 'drop-shadow(0 18px 24px rgba(0,0,0,0.55))'}}>{glyph}</div>;
  }
  if (o.type === 'number') {
    const target = Number(o.value ?? 0);
    const prog = interpolate(f, [0, 22], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
    const shown = Number.isInteger(target) ? fmt(target * prog) : (target * prog).toFixed(1);
    return (
      <div
        style={{
          ...base,
          left: '50%',
          fontFamily: FONT,
          fontSize: 150,
          color: 'white',
          background: `linear-gradient(135deg, ${PINK}, #FF8A00)`,
          padding: '10px 46px 22px',
          borderRadius: 34,
          whiteSpace: 'nowrap',
          boxShadow: '0 14px 0 #000, 0 24px 60px rgba(0,0,0,0.5)',
        }}
      >
        {o.prefix ?? ''}
        {shown}
        {o.suffix ?? ''}
      </div>
    );
  }
  // card: short keyword card sliding in from the side
  const slide = interpolate(inS, [0, 1], [o.slot % 2 ? 700 : -700, 0]);
  return (
    <div
      style={{
        position: 'absolute',
        top: 700,
        left: '50%',
        width: 'max-content',
        transform: `translate(calc(-50% + ${slide}px), ${bob}px) scale(${outS}) rotate(${o.slot % 2 ? 3 : -3}deg)`,
        fontFamily: FONT,
        fontSize: 82,
        color: 'white',
        background: 'rgba(20,20,30,0.88)',
        border: `6px solid ${YELLOW}`,
        padding: '18px 40px 26px',
        borderRadius: 30,
        maxWidth: 900,
        textAlign: 'center',
        boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
      }}
    >
      {o.text}
    </div>
  );
};

const Overlays: React.FC<{overlays: Overlay[]}> = ({overlays}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {overlays.map((o, i) => {
        const from = Math.round(o.start * fps);
        const frames = Math.max(8, Math.round(o.end * fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={frames} layout="none">
            <OverlayView o={o} frames={frames} />
          </Sequence>
        );
      })}
    </>
  );
};

// ------------------------------------------------------------ progress

const Progress: React.FC = () => {
  const f = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        height: 12,
        width: `${(f / durationInFrames) * 100}%`,
        background: `linear-gradient(90deg, ${YELLOW}, ${PINK})`,
        boxShadow: '0 0 18px rgba(255,230,0,0.8)',
      }}
    />
  );
};

// ----------------------------------------------------------------- main

export const Main: React.FC<VideoProps> = (p) => {
  useFont();
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <Clips clips={p.clips} />
      <Shade />
      <Flashes times={p.flashes} />
      <Overlays overlays={p.overlays} />
      <Hook text={p.hook.text} end={p.hook.end} />
      <Captions words={p.words} />
      <Progress />
      {p.audio ? <Audio src={staticFile(p.audio)} /> : null}
      {p.music ? <Audio src={staticFile(p.music)} volume={0.08} loop /> : null}
      {p.sfx.map((s, i) => (
        <Sequence key={i} from={Math.max(0, Math.round(s.start * fps))} layout="none">
          <Audio src={staticFile(s.src)} volume={s.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
