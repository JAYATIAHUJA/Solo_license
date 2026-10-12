import { useSyncExternalStore } from 'react';
import { AnimatePresence, motion } from 'motion/react';
export const CODING_LEVELS = [
  { id: 0, code: 'L0', name: 'Asks you every time' },
  { id: 1, code: 'L1', name: 'Runs what you approved' },
  { id: 2, code: 'L2', name: 'Runs on its own' },
];
import { SIG_BOX, loadSignature, subscribeSignature } from '../../../lib/signature.js';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { Logo } from '../../../components/brand/Logo.jsx';

/** The physical "license" the agent carries: level, track record, holder's
 *  signature, stamps. Purely presentational - the scenes drive it. */
export function LicenseCard({ level = 0, runs = 0, threshold = 3, quarantined = false, stamp = null, style, taskClass = 'test-run' }) {
  const signature = useSyncExternalStore(subscribeSignature, loadSignature);
  const info = CODING_LEVELS[Math.min(level, CODING_LEVELS.length - 1)];
  return (
    <motion.div className={`lc ${quarantined ? 'is-q' : ''}`} style={style}>
      <div className="lc-top">
        <span className="lc-brand"><Logo size={18} /> Solo License</span>
        <span className="mono">№ 0001</span>
      </div>
      <div className="lc-mid">
        <div>
          <span className="mono lc-label">Action class</span>
          <b className="lc-class">{taskClass}</b>
          <span className="mono lc-label">Authorised to</span>
          <AnimatePresence mode="wait">
            <motion.b key={`${level}-${quarantined}`} className="lc-auth" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              {quarantined ? 'Asks you - paused' : info.name}
            </motion.b>
          </AnimatePresence>
        </div>
        <div className="lc-level">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={level} className="serif" initial={{ rotateX: -90, opacity: 0 }} animate={{ rotateX: 0, opacity: 1 }} exit={{ rotateX: 90, opacity: 0 }} transition={{ duration: 0.22 }}>
              L{level}
            </motion.span>
          </AnimatePresence>
          <div className="lc-rungs">
            {CODING_LEVELS.map((l) => <i key={l.id} className={l.id <= level && !quarantined ? 'on' : ''} />)}
          </div>
        </div>
      </div>
      <div className="lc-bottom">
        <div className="lc-sig">
          <svg viewBox={`0 0 ${SIG_BOX.w} ${SIG_BOX.h}`} aria-hidden="true"><path d={signature} /></svg>
          <span className="mono lc-label">Issued by a human</span>
        </div>
        <div className="lc-runs">
          <span className="mono lc-label">Verified runs</span>
          <div>
            {Array.from({ length: threshold }, (_, i) => (
              <motion.i key={i} animate={{ backgroundColor: i < runs ? 'var(--ink)' : 'rgba(0,0,0,0)' }} />
            ))}
          </div>
        </div>
      </div>
      <div className="lc-stamp">
        {stamp && <Stamp key={stamp.text} text={stamp.text} sub={stamp.sub} tone={stamp.tone} size="md" angle={stamp.angle ?? -8} />}
      </div>
    </motion.div>
  );
}
