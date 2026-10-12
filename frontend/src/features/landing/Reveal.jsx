import { motion } from 'motion/react';
import { ScrambleText } from '../../components/fx/ScrambleText.jsx';

const EASE = [0.22, 1, 0.36, 1];

/** Fade + rise when scrolled into view. */
export function Reveal({ as = 'div', delay = 0, y = 28, className = '', children, ...rest }) {
  const Tag = motion[as];
  return (
    <Tag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-12% 0px' }}
      transition={{ duration: 0.9, delay, ease: EASE }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** Split a headline into words that slide up out of a mask, one by one.
 *  The in-view trigger sits on each visible mask, not on the hidden word: an
 *  element clipped by its overflow-hidden parent never counts as in view, so
 *  a word waiting below its mask would never be revealed. */
export function MaskWords({ text, delay = 0, stagger = 0.06, className = '', animateOnMount = false }) {
  const words = text.split(' ');
  const trigger = animateOnMount
    ? { initial: 'hidden', animate: 'shown' }
    : { initial: 'hidden', whileInView: 'shown', viewport: { once: true, margin: '-10% 0px' } };
  return (
    <span className={className} aria-label={text}>
      {words.map((word, i) => (
        <motion.span key={`${word}-${i}`} aria-hidden="true" {...trigger}
          style={{ display: 'inline-block', overflow: 'hidden', verticalAlign: 'top', paddingBottom: '0.08em',
            marginRight: i < words.length - 1 ? '0.25em' : 0 }}>
          <motion.span
            style={{ display: 'block' }}
            variants={{ hidden: { y: '110%' }, shown: { y: '0%' } }}
            transition={{ duration: 1, delay: delay + i * stagger, ease: EASE }}
          >
            {word}
          </motion.span>
        </motion.span>
      ))}
    </span>
  );
}

/** Section heading row: index number, label, and a hand-drawn rule. */
export function SectionHead({ index, label, children }) {
  return (
    <div className="lp-head">
      <span className="mono">({index})</span>
      <ScrambleText className="mono" text={label} />
      {children}
    </div>
  );
}
