import { motion } from 'motion/react';

/** Santioni-style display type: every line is drawn twice, clipped to its top
 *  and bottom halves, and the halves slide together into one word. */
export function SplitTitle({ lines, delay = 0, className = '' }) {
  return (
    <h1 className={`split-title ${className}`} aria-label={lines.join(' ')}>
      {lines.map((line, i) => (
        <span key={line} className="split-line" aria-hidden="true">
          <motion.span
            className="split-half split-top"
            initial={{ x: '-6%', opacity: 0 }}
            animate={{ x: '0%', opacity: 1 }}
            transition={{ duration: 1.2, delay: delay + i * 0.15, ease: [0.22, 1, 0.36, 1] }}
          >
            {line}
          </motion.span>
          <motion.span
            className="split-half split-bottom"
            initial={{ x: '6%', opacity: 0 }}
            animate={{ x: '0%', opacity: 1 }}
            transition={{ duration: 1.2, delay: delay + i * 0.15 + 0.05, ease: [0.22, 1, 0.36, 1] }}
          >
            {line}
          </motion.span>
          <span className="split-ghost">{line}</span>
        </span>
      ))}
    </h1>
  );
}
