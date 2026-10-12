import { motion, useReducedMotion } from 'motion/react';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const EASE = [0.22, 1, 0.36, 1];

const BEATS = [
  {
    code: 'remediation',
    title: 'A failed install.',
    log: [
      ['tool.Bash', 'npm install left-pad@9'],
      ['verify.install', 'exit 1 · ERESOLVE', true],
    ],
    told: 'Restore package.json and package-lock.json: git checkout -- package.json package-lock.json',
  },
  {
    code: 'flagged',
    title: 'You mark it wrong.',
    log: [
      ['turn.flagged', 'marked wrong · by you', true],
      ['license.flag', 'file-edit · L2 → L0'],
    ],
    told: 'Your last turn was flagged by the user. Revert its changes before anything else.',
  },
  {
    code: 'loop-stop',
    title: 'The same failing call.',
    loop: true,
    told: 'Five blocked attempts this turn. Stop trying variations and tell the user what is failing.',
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
        <p className="lp-copy">Taking the keys away is half of it. On the next hook, the agent gets the exact undo. Each moment below is a neatlogs incident and an Entire checkpoint, linked from its permission history row.</p>
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
              <p className="hand">“{beat.told}”</p>
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
