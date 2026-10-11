import { useMemo } from 'react';
import { motion } from 'motion/react';
import { LEVELS } from '../../lib/format.js';
import { roughLine } from '../sketch/rough.js';
import './level-stepper.css';

/** Compact autonomy ladder for the app: four stops on one hand-drawn line.
 *  Earned stops are inked, the current one is large, the next shows the
 *  clean-run ticks still needed. A quarantine strikes the line through. */
export function LevelStepper({ level = 0, cleanRuns = 0, threshold = 3, quarantined = false, demotedFrom = null }) {
  const line = useMemo(() => roughLine(0, 6, 1000, 6, { seed: 31, roughness: 0.7, strokeWidth: 1.4 }), []);
  const fill = quarantined ? 0 : (level + (level < 3 ? cleanRuns / threshold : 0)) / 3;

  return (
    <div className={`stepper ${quarantined ? 'is-q' : ''}`}>
      <div className="stepper-track" aria-hidden="true">
        <svg viewBox="0 0 1000 12" preserveAspectRatio="none">{line.map((p, i) => <path key={i} d={p.d} />)}</svg>
        <motion.i className="stepper-fill" initial={false} animate={{ scaleX: fill }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} />
      </div>
      <ol className="stepper-stops">
        {LEVELS.map((l) => {
          const earned = !quarantined && l.id <= level;
          const current = l.id === level;
          const next = !quarantined && l.id === level + 1;
          return (
            <li key={l.id} style={{ left: `${(l.id / 3) * 100}%` }} className={`${earned ? 'is-earned' : ''} ${current ? 'is-current' : ''}`}>
              <span className="stepper-dot" />
              <b className="mono">{l.code}</b>
              <span className="stepper-name">{l.name}</span>
              {next && (
                <span className="stepper-ticks" aria-label={`${cleanRuns} of ${threshold} clean runs`}>
                  {Array.from({ length: threshold }, (_, i) => <i key={i} className={i < cleanRuns ? 'on' : ''} />)}
                </span>
              )}
              {quarantined && demotedFrom === l.id && <span className="stepper-fell hand">fell from here</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
