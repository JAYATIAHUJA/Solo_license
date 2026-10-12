import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent } from 'motion/react';
import { Pinned } from '../Pinned.jsx';

/* What the agent session shows at each stage: lines are added, never removed. */
const SESSION = [
  [
    { kind: 'you', text: 'fix the off-by-one in cart.js' },
    { kind: 'tool', text: 'Edit(cart.js)  - count > 10 → count >= 10' },
    { kind: 'gate', tone: 'ok', text: 'auto-approved · file-edit is L2 in shop-api' },
  ],
  [
    { kind: 'tool', text: 'Edit(format.js)  - “tidied while I was here” · +120 lines' },
    { kind: 'tool', text: 'Edit(utils.js)  - “renamed helpers” · +90 lines' },
    { kind: 'agent', text: 'Done! Fixed the off-by-one and cleaned things up.' },
  ],
  [
    { kind: 'gate', tone: 'bad', alert: true, text: 'sent back · over-editing: 210 lines in 3 files for a 1-line request (scope 1/5). file-edit L2 → L0' },
  ],
  [
    { kind: 'you', text: 'ok, also update the readme' },
    { kind: 'tool', text: 'Edit(README.md)' },
    { kind: 'gate', tone: 'bad', text: 'asks you first · file-edit stays at L0 until a person resumes it' },
  ],
];
const MARK = { you: '>', tool: '⏺', gate: '§', out: '⎿', agent: '⏺' };


/* Scene 05 - the page itself goes dark the moment the detection fires
   (Moto's theme-invert), the level crashes, and the card is stamped. */
export function Crash() {
  return (
    <Pinned id="crash" length={2.4} className="sc-crash">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Scene({ p }) {
  const [stage, setStage] = useState(0);
  useMotionValueEvent(p, 'change', (v) => setStage(v < 0.12 ? 0 : v < 0.42 ? 1 : v < 0.72 ? 2 : 3));
  const dark = stage >= 1 && stage < 3 ? true : stage === 3;
  const session = SESSION.slice(0, stage + 1).flat();

  // Invert the page chrome (nav, scale) only while the dark stage actually
  // sits under the viewport's middle, not for the whole time `dark` is set.
  const stageRef = useRef(null);
  useEffect(() => {
    const sync = () => {
      const r = stageRef.current?.getBoundingClientRect();
      const mid = window.innerHeight / 2;
      const covered = dark && r && r.top <= mid && r.bottom >= mid;
      document.documentElement.dataset.invert = covered ? '1' : '';
    };
    sync();
    window.addEventListener('scroll', sync, { passive: true });
    window.addEventListener('resize', sync);
    return () => { window.removeEventListener('scroll', sync); window.removeEventListener('resize', sync); };
  }, [dark]);
  useEffect(() => () => { delete document.documentElement.dataset.invert; }, []);

  const level = stage >= 2 ? 0 : 2;

  return (
    <motion.div ref={stageRef} className="sc-crash-stage" animate={{ backgroundColor: dark ? '#0e0e0d' : 'rgba(14,14,13,0)', color: dark ? '#f3f1ec' : '#0e0e0d' }} transition={{ duration: 0.5 }}>
      <motion.div className="sc-wrap sc-crash-wrap" animate={stage === 2 ? { x: [0, -16, 13, -8, 5, 0], y: [0, 6, -4, 2, 0] } : {}} transition={{ duration: 0.5 }}>
        <div className="sc-crash-copy">
          <div className="sc-head"><span className="mono">The crash</span></div>
          <AnimatePresence mode="wait">
            <motion.h2 key={stage} className="sc-title serif" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
              {['Turn #48. Same agent, same repo.', 'Something is off.', 'One bad turn. Back to zero.', 'And it stays there.'][stage]}
            </motion.h2>
          </AnimatePresence>
          <motion.p className="sc-body" animate={{ opacity: stage === 3 ? 1 : 0 }}>
            A paused class asks you before every action again. A person reads the turn - with its Entire checkpoint - rewinds it if needed and resumes it at a level they choose. That decision is committed to git with their reason.
          </motion.p>
        </div>

        <div className="sc-crash-visual">
          <div className="sc-crash-level serif" aria-live="polite">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={level}
                initial={level === 0 ? { y: '-120%', scale: 1.4 } : { opacity: 0 }}
                animate={{ y: '0%', scale: 1, opacity: 1 }}
                exit={{ y: '120%', opacity: 0, transition: { duration: 0.15 } }}
                transition={level === 0 ? { type: 'spring', stiffness: 520, damping: 18 } : { duration: 0.3 }}
              >
                L{level}
              </motion.span>
            </AnimatePresence>
          </div>
          <div className="term sc-crash-term" role="img" aria-label="A coding-agent session where Solo License pauses the agent after an over-edit">
          <div className="term-chrome">
            <i /><i /><i />
            <span className="mono">~/shop-api · agent session</span>
            <span className={`sc-crash-chip mono ${level === 0 ? 'is-l0' : ''}`}>file-edit · L{level}</span>
          </div>
          <ol className="term-body mono">
            {session.map((l) => (
              <motion.li
                key={l.text}
                className={`term-line is-${l.kind} ${l.tone ? `is-${l.tone}` : ''} ${l.alert ? 'is-alert' : ''}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25 }}
              >
                <span className="term-mark">{MARK[l.kind]}</span>
                <span>{l.kind === 'gate' ? <><b>Solo License</b> {l.text}</> : l.text}</span>
              </motion.li>
            ))}
            <li className="term-line term-cursor"><span className="term-mark">&gt;</span><i /></li>
          </ol>
        </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
