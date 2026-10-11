import { motion } from 'motion/react';
import './stamp.css';

/** A rubber stamp that slams onto the page: drops from above, overshoots,
 *  settles at an angle, with a worn-ink texture. `show` drives it. */
export function Stamp({ text, sub, show = true, tone = 'ink', angle = -9, size = 'md', className = '' }) {
  return (
    <motion.div
      className={`stamp stamp-${tone} stamp-${size} ${className}`}
      initial={false}
      animate={show
        ? { opacity: 1, scale: [2.4, 0.94, 1], rotate: [angle - 8, angle + 2, angle], filter: ['blur(6px)', 'blur(0px)', 'blur(0px)'] }
        : { opacity: 0, scale: 2.4, rotate: angle - 8, filter: 'blur(6px)' }}
      transition={{ duration: 0.45, times: [0, 0.7, 1], ease: [0.2, 0.8, 0.2, 1] }}
      aria-hidden={!show}
    >
      <span className="stamp-text">{text}</span>
      {sub && <span className="stamp-sub">{sub}</span>}
    </motion.div>
  );
}
