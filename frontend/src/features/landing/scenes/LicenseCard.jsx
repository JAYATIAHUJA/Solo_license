import { useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { LEVELS } from '../../../lib/format.js';
import { SIG_BOX, loadSignature } from '../../../lib/signature.js';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { Logo } from '../../../components/brand/Logo.jsx';

/** The physical "license" the agent carries: level, track record, holder's
 *  signature, stamps. Purely presentational - the scenes drive it. */
export function LicenseCard({ level = 0, runs = 0, threshold = 3, quarantined = false, stamp = null, style }) {
  const signature = useMemo(loadSignature, []);
  const info = LEVELS[level];
  return (
    <motion.div className={`lc ${quarantined ? 'is-q' : ''}`} style={style}>
      <div className="lc-top">
        <span className="lc-brand"><Logo size={18} /> Solo License</span>
        <span className="mono">№ 0001</span>
      </div>
      <div className="lc-mid">
        <div>
          <span className="mono lc-label">Task class</span>
          <b className="lc-class">refund</b>
          <span className="mono lc-label">Authorised to</span>
          <AnimatePresence mode="wait">
            <motion.b key={`${level}-${quarantined}`} className="lc-auth" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              {quarantined ? 'Suggest only - quarantined' : info.name}
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
            {[0, 1, 2, 3].map((r) => <i key={r} className={r <= level && !quarantined ? 'on' : ''} />)}
          </div>
        </div>
      </div>
      <div className="lc-bottom">
        <div className="lc-sig">
          <svg viewBox={`0 0 ${SIG_BOX.w} ${SIG_BOX.h}`} aria-hidden="true"><path d={signature} /></svg>
          <span className="mono lc-label">Issued by a human</span>
        </div>
        <div className="lc-runs">
          <span className="mono lc-label">Clean runs</span>
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
