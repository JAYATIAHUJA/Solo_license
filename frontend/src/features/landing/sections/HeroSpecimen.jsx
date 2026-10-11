import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

/* A looping specimen of one action class's life in one repo: approvals earn
   it, it runs alone, then a turn breaks the tests and the dial crashes.
   Illustrative only - the real thing runs in the app against the hooks. */
const FRAMES = [
  { level: 0, runs: 0, line: 'npm test · Claude Code asked you · approved', icon: 'message' },
  { level: 0, runs: 1, line: 'npm test · ran · verified', icon: 'check' },
  { level: 0, runs: 2, line: 'npm test · ran · verified', icon: 'check' },
  { level: 1, runs: 0, line: '3 verified runs → promoted to L1 · commit 4f1a2c', icon: 'commit' },
  { level: 1, runs: 1, line: 'npm test · ran on its own · no prompt', icon: 'check' },
  { level: 0, runs: 0, line: 'turn check - tests fail after the edit → L0', icon: 'warn', alert: true },
];

export function HeroSpecimen() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % FRAMES.length), 2200);
    return () => clearInterval(t);
  }, []);
  const f = FRAMES[i];

  return (
    <SketchBox className="lp-specimen" seed={77}>
      <div className="lp-specimen-top">
        <span className="mono">test-run @ shop-api</span>
        <span className={`mono ${f.alert ? 'lp-alert' : ''}`}>{f.alert ? '● paused' : '● live'}</span>
      </div>
      <div className="lp-specimen-level">
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={f.level}
            className="serif"
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            L{f.level}
          </motion.span>
        </AnimatePresence>
        <div className="lp-specimen-rungs">
          {[0, 1, 2].map((r) => (
            <motion.i key={r} animate={{ backgroundColor: r <= f.level && !f.alert ? '#0e0e0d' : 'rgba(0,0,0,0)' }} />
          ))}
        </div>
      </div>
      <div className="lp-specimen-runs">
        <span className="mono muted">verified runs</span>
        <span className="lp-ticks">
          {[0, 1, 2].map((r) => <i key={r} className={r < f.runs ? 'on' : ''} />)}
        </span>
      </div>
      <AnimatePresence mode="wait">
        <motion.p
          key={i}
          className={`lp-specimen-line ${f.alert ? 'lp-alert' : ''}`}
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -10 }}
          transition={{ duration: 0.3 }}
        >
          <HandIcon name={f.icon} size={16} /> {f.line}
        </motion.p>
      </AnimatePresence>
    </SketchBox>
  );
}
