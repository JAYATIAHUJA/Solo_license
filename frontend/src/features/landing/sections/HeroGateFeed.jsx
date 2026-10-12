import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';

/* What Solo License does, in one loop: an agent's tool calls arrive at the
   gate, each gets allow / ask / deny from what that kind of action has earned
   in this repo, the turn is checked at the end, and the licenses move.
   Illustrative only - the real thing runs in the app against the hooks. */
const STEPS = [
  { cmd: 'npm test', verdict: 'allow', why: 'test-run L1 · earned from 3 verified runs', set: { 'test-run': 1 } },
  { cmd: 'Edit cart.js', verdict: 'allow', why: 'file-edit L1 · checked at the end of the turn' },
  { cmd: 'npm install left-pad', verdict: 'ask', why: 'install-dep L0 · not earned here, you decide' },
  { cmd: 'git push --force origin main', verdict: 'deny', why: 'never allowed, at any level' },
  { cmd: 'turn check · 162 lines for a 1-line fix', verdict: 'back', why: 'over-edit: revert format.js · file-edit → L0', set: { 'file-edit': 0 } },
  { cmd: 'git checkout -- format.js · npm test', verdict: 'allow', why: 'verified: 2 lines, tests pass · file-edit → L1', set: { 'file-edit': 1 } },
];

const WORD = { allow: 'Allow', ask: 'Ask', deny: 'Deny', back: 'Sent back' };
const START = { 'test-run': 1, 'file-edit': 1, 'install-dep': 0, 'git-remote': 0 };
const VISIBLE = 4;

function levelsAt(step) {
  const levels = { ...START };
  for (let i = 0; i <= step; i += 1) Object.assign(levels, STEPS[i].set || {});
  return levels;
}

export function HeroGateFeed() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((n) => (n + 1) % STEPS.length), 2100);
    return () => clearInterval(t);
  }, []);
  const rows = STEPS.slice(0, step + 1).map((s, i) => ({ ...s, i })).slice(-VISIBLE);
  const levels = levelsAt(step);
  const changed = STEPS[step].set || {};

  return (
    <SketchBox className="lp-feed" seed={77}>
      <div className="lp-feed-top">
        <span className="mono">claude code · shop-api</span>
        <span className="mono">● live</span>
      </div>

      <ol className="lp-feed-rows" aria-live="polite">
        <AnimatePresence initial={false}>
          {rows.map((r) => (
            <motion.li
              key={`${r.i}-${r.cmd}`}
              layout
              className={`lp-feed-row is-${r.verdict}`}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            >
              <code className="lp-feed-cmd">{r.cmd}</code>
              <span className={`lp-feed-verdict mono is-${r.verdict}`}>{WORD[r.verdict]}</span>
              <small className="lp-feed-why">{r.why}</small>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>

      <div className="lp-feed-levels" aria-label="Licenses in shop-api">
        {Object.entries(levels).map(([cls, level]) => (
          <div key={cls} className={`lp-feed-level ${cls in changed ? 'is-moved' : ''}`}>
            <span className="mono muted">{cls}</span>
            <b className="serif">L{level}</b>
            <span className="lp-feed-rungs">{[0, 1, 2].map((r) => <i key={r} className={r < level ? 'on' : ''} />)}</span>
          </div>
        ))}
      </div>

      <div className="lp-feed-proof mono">
        <span>trace → neatlogs</span>
        <span>checkpoint → Entire</span>
        <span>$ saved → cfo.ai</span>
      </div>
    </SketchBox>
  );
}
