import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent } from 'motion/react';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Pinned } from '../Pinned.jsx';
import { LicenseCard } from './LicenseCard.jsx';

const LOG = [
  ['gate.allow', 'file-edit · L2 · runs on its own'],
  ['tool.Edit', 'cart.js · format.js · utils.js'],
  ['turn.check', '210 lines in 3 files · scope 1/5'],
  ['verify.tests', 'npm test · 2 failing'],
  ['detection.over_editing', 'asked for 1 line · changed 210'],
];

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
  const lines = stage === 0 ? 1 : stage === 1 ? 4 : 5;

  useEffect(() => {
    document.documentElement.dataset.invert = dark ? '1' : '';
  }, [dark]);
  useEffect(() => () => { delete document.documentElement.dataset.invert; }, []);

  const level = stage >= 2 ? 0 : 2;

  return (
    <motion.div className="sc-crash-stage" animate={{ backgroundColor: dark ? '#0e0e0d' : 'rgba(14,14,13,0)', color: dark ? '#f3f1ec' : '#0e0e0d' }} transition={{ duration: 0.5 }}>
      <motion.div className="sc-wrap sc-crash-wrap" animate={stage === 2 ? { x: [0, -16, 13, -8, 5, 0], y: [0, 6, -4, 2, 0] } : {}} transition={{ duration: 0.5 }}>
        <div className="sc-crash-copy">
          <div className="sc-head"><span className="mono">(006)</span><span className="mono">The crash</span></div>
          <AnimatePresence mode="wait">
            <motion.h2 key={stage} className="sc-title serif" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
              {['Turn #48. Same agent, same repo.', 'Something is off.', 'One bad turn. Back to zero.', 'And it stays there.'][stage]}
            </motion.h2>
          </AnimatePresence>
          <ol className="sc-log mono">
            {LOG.slice(0, lines).map(([name, attr], i) => (
              <motion.li key={name} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className={name.startsWith('detection') ? 'is-alert' : ''}>
                <span>{String(i + 1).padStart(2, '0')}</span><b>{name}</b><em>{attr}</em>
              </motion.li>
            ))}
          </ol>
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
          <div className="sc-crash-card">
            <LicenseCard level={level} runs={level === 2 ? 3 : 0} quarantined={stage >= 2} stamp={null} taskClass="file-edit" />
            <div className="sc-crash-stamp"><Stamp text="Paused" sub="over_editing" tone="signal" size="lg" show={stage >= 2} angle={-10} /></div>
          </div>
          {stage >= 2 && (
            <motion.p className="sc-crash-note hand" initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay: 0.4 } }}>
              <HandIcon name="arrow-left" size={18} /> L2 → L0 in one turn
            </motion.p>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
