import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const RULES = [
  {
    code: 'state_mismatch',
    title: 'The world didn’t change.',
    fires: 'The amount the database actually moved differs from the refund the agent meant to make.',
    example: 'Tool returns “Refund processed.” orders.refunded_amount moved $0.00. Caught.',
  },
  {
    code: 'missing_verification',
    title: 'It said done without looking.',
    fires: 'An execution completed but no read-back of the database ran afterwards.',
    example: 'A run reports success with no verify.readback span. Caught.',
  },
  {
    code: 'policy_breach',
    title: 'It reached past its license.',
    fires: 'The agent executed while its current level only allowed a suggestion or a draft.',
    example: 'L0 class attempts AUTO_EXECUTE on a $120 refund. Caught.',
  },
];

/** Index-style list; hovering or tapping a row opens its detail. */
export function Detections() {
  const [open, setOpen] = useState(0);
  return (
    <section className="lp-section" id="detections">
      <SectionHead index="006" label="Detections" />
      <div className="lp-split">
        <h2 className="lp-h2 serif">Three ways to <em className="italic">lose</em> the keys.</h2>
        <p className="lp-copy">Each rule is a pure function over observed facts. Any one of them firing demotes the task class to L0 and quarantines it until a person signs off.</p>
      </div>
      <div className="lp-index">
        {RULES.map((rule, i) => (
          <div key={rule.code} className={`lp-index-row ${open === i ? 'is-open' : ''}`} onMouseEnter={() => setOpen(i)}>
            <SketchRule seed={300 + i} />
            <button className="lp-index-head" onClick={() => setOpen(i)} aria-expanded={open === i}>
              <span className="mono">0{i + 1}</span>
              <span className="lp-index-title serif">{rule.title}</span>
              <code className="mono">{rule.code}</code>
              <HandIcon name={open === i ? 'minus' : 'plus'} size={18} />
            </button>
            <AnimatePresence initial={false}>
              {open === i && (
                <motion.div className="lp-index-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
                  <div>
                    <span className="mono muted">Fires when</span>
                    <p>{rule.fires}</p>
                  </div>
                  <div>
                    <span className="mono muted">Example</span>
                    <p className="hand lp-index-example">{rule.example}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
        <SketchRule seed={399} />
      </div>
    </section>
  );
}
