import { useState } from 'react';
import { useMotionValueEvent, useTransform } from 'motion/react';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';
import { CODING_LEVELS as LEVELS, LicenseCard } from './LicenseCard.jsx';

const STORY = [
  { title: 'It starts with nothing.', body: 'In a new repo every kind of action asks you first, exactly like Claude Code does today. Each command you approve - and each turn whose diff and tests check out - is evidence.' },
  { title: 'What you approved, it runs.', body: 'After 3 verified runs, the command families you already approved run on their own. `npm test` stops asking; `pytest`, which you never approved, still asks.' },
  { title: 'The whole class, on its own.', body: 'When the evidence proves its failure rate is below the cost of one mistake, the whole class runs alone. Pushes cap at L1; deploys and database changes always ask. One failure takes it all back.' },
];

/* Scene 03 - Moto-card style: the license card stays pinned in the middle
   while the story scrolls past it, earning one rung per screen. */
export function Journey() {
  return (
    <Pinned id="journey" length={2.9} className="sc-journey">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Scene({ p }) {
  const [state, setState] = useState({ level: 0, runs: 0 });
  useMotionValueEvent(p, 'change', (v) => {
    const t = Math.min(0.9999, Math.max(0, (v - 0.04) / 0.92)) * LEVELS.length;
    const level = Math.floor(t);
    const runs = level >= LEVELS.length - 1 ? 3 : Math.floor((t - level) * 4);
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
          <span className="mono muted">(004)</span>
          <ScrambleText className="mono" text="How it earns the keys" />
        </div>
        <div>
          <span className="sc-big-level serif">{LEVELS[state.level].code}</span>
          <h2 className="sc-title serif">{story.title}</h2>
          <p className="sc-body">{story.body}</p>
        </div>
        <hr className="sc-rule" />
      </div>

      <div className="sc-journey-card" style={{ perspective: 1400 }}>
        <LicenseCard
          level={state.level}
          runs={state.runs}
          stamp={promoted ? { text: `Promoted · ${LEVELS[state.level].code}`, sub: 'verified runs', tone: 'ink', angle: -7 } : null}
          style={{ rotateY, rotateX, y: cardY }}
        />
        <p className="sc-card-note hand">{state.level < LEVELS.length - 1 ? `${3 - state.runs} verified run${3 - state.runs === 1 ? '' : 's'} to ${LEVELS[state.level + 1].code}` : 'top rung - one failure away from L0'}</p>
      </div>
    </div>
  );
}
