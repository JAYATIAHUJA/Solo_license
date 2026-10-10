import { useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useTransform } from 'motion/react';
import { LEVELS } from '../../../lib/format.js';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';
import { LicenseCard } from './LicenseCard.jsx';

const STORY = [
  { title: 'It starts with nothing.', body: 'At L0 the agent reads the request and recommends what to do. A person does the refund. Nothing it says touches money.', proof: 'Suggest only' },
  { title: 'It drafts. You click.', body: 'Three verified runs in a row and it earns L1: it prepares the refund, you approve it, and the database is read back to prove it happened.', proof: 'Draft + approve' },
  { title: 'Small refunds, on its own.', body: 'Three more clean runs and it acts alone — but only under a ceiling you set. Anything bigger still waits for a human.', proof: 'Auto under $50' },
  { title: 'Full auto. Still watched.', body: 'At L3 it handles every refund in the class. Each run is sampled for audit, and the license can be taken back at any moment.', proof: 'Full auto, audited' },
];

/* Scene 03 — Moto-card style: the license card stays pinned in the middle
   while the story scrolls past it, earning one rung per screen. */
export function Journey() {
  return (
    <Pinned id="journey" length={4.4} className="sc-journey">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Scene({ p }) {
  const [state, setState] = useState({ level: 0, runs: 0 });
  useMotionValueEvent(p, 'change', (v) => {
    const t = Math.min(0.9999, Math.max(0, (v - 0.04) / 0.92)) * 4;
    const level = Math.floor(t);
    const runs = level >= 3 ? 3 : Math.floor((t - level) * 4);
    setState((s) => (s.level === level && s.runs === runs ? s : { level, runs: Math.min(3, runs) }));
  });
  const rotateY = useTransform(p, [0, 0.5, 1], [-18, 10, -6]);
  const rotateX = useTransform(p, [0, 0.5, 1], [14, -4, 8]);
  const cardY = useTransform(p, [0, 0.08], [80, 0]);
  const story = STORY[state.level];
  const promoted = state.level > 0 && state.runs === 0;

  return (
    <div className="sc-wrap sc-journey-wrap">
      <div className="sc-journey-copy">
        <div className="sc-head">
          <span className="mono muted">(003)</span>
          <ScrambleText className="mono" text="How it earns the keys" />
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={state.level} initial={{ opacity: 0, y: 30, filter: 'blur(8px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: 0, y: -30, filter: 'blur(8px)' }} transition={{ duration: 0.5 }}>
            <span className="sc-big-level serif">{LEVELS[state.level].code}</span>
            <h2 className="sc-title serif">{story.title}</h2>
            <p className="sc-body">{story.body}</p>
          </motion.div>
        </AnimatePresence>
        <ol className="sc-steps">
          {LEVELS.map((l) => (
            <li key={l.id} className={l.id === state.level ? 'is-on' : l.id < state.level ? 'is-done' : ''}>
              <span className="mono">{l.code}</span> {l.name}
            </li>
          ))}
        </ol>
      </div>

      <div className="sc-journey-card" style={{ perspective: 1400 }}>
        <LicenseCard
          level={state.level}
          runs={state.runs}
          stamp={promoted ? { text: `Promoted · ${LEVELS[state.level].code}`, sub: '3 clean runs', tone: 'ink', angle: -7 } : null}
          style={{ rotateY, rotateX, y: cardY }}
        />
        <p className="sc-card-note hand">{state.level < 3 ? `${3 - state.runs} clean run${3 - state.runs === 1 ? '' : 's'} to ${LEVELS[state.level + 1].code}` : 'top rung — audited'}</p>
      </div>
    </div>
  );
}
