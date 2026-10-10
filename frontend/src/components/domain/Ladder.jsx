import { motion } from 'motion/react';
import { LEVELS } from '../../lib/format.js';
import { SketchBox } from '../sketch/Sketch.jsx';
import { HandIcon } from '../icons/HandIcon.jsx';
import './ladder.css';

/** The autonomy ladder: four hand-drawn rungs. The earned rung is inked solid,
 *  the next rung shows progress toward promotion, a quarantine crosses it out. */
export function Ladder({ level = 0, cleanRuns = 0, threshold = 3, quarantined = false, demotedFrom = null, compact = false, onPick }) {
  return (
    <div className={`ladder ${compact ? 'is-compact' : ''} ${quarantined ? 'is-quarantined' : ''}`}>
      {LEVELS.map((rung) => {
        const earned = rung.id <= level && !quarantined;
        const current = rung.id === level;
        const next = rung.id === level + 1 && !quarantined;
        const fellFrom = quarantined && demotedFrom === rung.id;
        const Tag = onPick ? 'button' : 'div';
        return (
          <SketchBox
            key={rung.id}
            as={Tag}
            seed={40 + rung.id}
            fill={earned && current ? 'solid' : earned ? 'hachure' : undefined}
            hachure={5}
            className={`ladder-rung ${current ? 'is-current' : ''} ${earned ? 'is-earned' : ''}`}
            onClick={onPick ? () => onPick(rung.id) : undefined}
            type={onPick ? 'button' : undefined}
          >
            <span className="ladder-code mono">{rung.code}</span>
            <span className="ladder-name">{rung.name}</span>
            {!compact && <span className="ladder-who">{rung.who}</span>}
            {next && (
              <span className="ladder-progress" aria-label={`${cleanRuns} of ${threshold} clean runs`}>
                {Array.from({ length: threshold }, (_, i) => (
                  <motion.i key={i} className={i < cleanRuns ? 'on' : ''} initial={false} animate={{ scaleY: i < cleanRuns ? 1 : 0.35 }} />
                ))}
              </span>
            )}
            {fellFrom && <span className="ladder-fell hand">fell from here</span>}
            {current && quarantined && <span className="ladder-lock"><HandIcon name="warn" size={16} /> quarantined</span>}
          </SketchBox>
        );
      })}
    </div>
  );
}
