import { motion, useReducedMotion } from 'motion/react';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const EASE = [0.22, 1, 0.36, 1];

const BEATS = [
  {
    code: 'tool-failed',
    title: 'A failed install.',
    log: [
      ['tool.failed', 'npm install · exit 1', true],
      ['remediation.sent', 'install-dep → L0'],
    ],
    told: '`npm install left-pad@9` failed and install-dep is back to asking. Undo the partial change (`git checkout -- package.json package-lock.json`) and continue without it.',
  },
  {
    code: 'flagged',
    title: 'You mark it wrong.',
    log: [
      ['turn.flagged', 'wrong file · by you', true],
      ['remediation.queued', 'file-edit → L0'],
    ],
    told: 'Your last turn was flagged by the user: wrong file. file-edit is back to asking. Revert that turn’s changes before continuing… Then ask the user what they want instead.',
  },
  {
    code: 'loop-stop',
    title: 'The same call, again.',
    loop: true,
    told: 'This is the 5th time `npm test -- cart.test.js` runs with nothing edited in between. Stopping here so a person can look: say what you were trying to do and ask the user how to proceed.',
  },
];

/** Three moments where the agent is told what to undo, not just stopped. */
export function Remedies() {
  const still = useReducedMotion();
  const enter = (delay) => (still
    ? {}
    : { initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: '-10% 0px' }, transition: { duration: 0.7, delay, ease: EASE } });

  return (
    <section className="lp-section" id="fixes">
      <SectionHead index="008" label="Remediation" />
      <div className="lp-split">
        <h2 className="lp-h2 serif">It tells the agent <em className="italic">how to fix it.</em></h2>
        <p className="lp-copy">On its next call the agent is told the exact undo.</p>
      </div>
      <SketchRule seed={420} />
      <ol className="lp-fix">
        {BEATS.map((beat, i) => (
          <motion.li key={beat.code} className="lp-fix-beat" {...enter(i * 0.12)}>
            <div className="lp-fix-top">
              <span className="mono muted">0{i + 1}</span>
              <code className="mono">{beat.code}</code>
            </div>
            <h3 className="serif">{beat.title}</h3>
            {beat.loop ? <LoopTicks still={still} /> : (
              <ol className="sc-log mono lp-fix-log">
                {beat.log.map(([name, attr, alert]) => (
                  <li key={name} className={alert ? 'is-alert' : ''}><b>{name}</b><em>{attr}</em></li>
                ))}
              </ol>
            )}
            <div className="lp-fix-told">
              <span className="mono muted">Agent is told</span>
              <p>{beat.told.split('`').map((part, k) => (k % 2 ? <code key={k} className="mono">{part}</code> : part))}</p>
            </div>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}

/** Five attempts at one call: guidance at the third, stopped at the fifth. */
function LoopTicks({ still }) {
  return (
    <div className="lp-fix-loop">
      <code className="mono">npm test -- cart.test.js</code>
      <div className="lp-fix-ticks">
        {[1, 2, 3, 4, 5].map((n) => (
          <div key={n} className={n === 5 ? 'is-alert' : ''}>
            <motion.i
              initial={still ? false : { scaleY: 0 }}
              whileInView={{ scaleY: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.25, delay: still ? 0 : 0.4 + n * 0.18, ease: EASE }}
            />
            <span className="mono">{n}</span>
          </div>
        ))}
      </div>
      <p className="mono lp-fix-loop-note"><span>3 · guidance</span><span className="lp-alert">5 · stopped</span></p>
    </div>
  );
}
