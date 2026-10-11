import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const RULES = [
  {
    code: 'over_editing',
    title: 'It changed more than you asked.',
    fires: 'At the end of a turn, the diff is out of proportion to the request - graded 1 to 5 by Jev, or by a size-and-spread rule.',
    example: '“Fix the off-by-one in cart.js” → 162 lines in 2 files. Sent back with the files to revert.',
  },
  {
    code: 'tests_failed',
    title: 'It left the repo broken.',
    fires: 'The repo’s own tests fail after the turn’s changes.',
    example: 'npm test: 1 failing after the edit. Sent back to fix it; the class that changed code drops to L0.',
  },
  {
    code: 'forbidden_action',
    title: 'It reached for something it must never do.',
    fires: 'Deleting outside the project, piping a download into a shell, force-pushing main, sudo, dropping a database.',
    example: 'git push --force origin main → denied at any level. Caught.',
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
        <p className="lp-copy">Each check runs once per turn, not once per edit. Any one of them firing demotes the action class that did it to L0, and the agent is told exactly what to fix.</p>
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
