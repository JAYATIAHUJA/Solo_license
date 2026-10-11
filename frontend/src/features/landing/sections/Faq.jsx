import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const QA = [
  ['Does the LLM decide what the agent is allowed to do?', 'No. The model reads customer messages and writes the plan. Permission comes from the license state machine, and the truth about what happened comes from reading the database back.'],
  ['Do I need an API key to try it?', 'No. Without a key, a deterministic parser and planner run the same loop. Add an Anthropic or OpenAI key during setup (or later in Settings) and the agent uses the model.'],
  ['What happens after a demotion?', 'The task class sits at L0 and earns nothing until a person opens the evidence packet and restores it to a level they choose. That decision is written to the ledger as a git commit.'],
  ['Can I test failures on purpose?', 'Yes. The app has a fault switch: arm a quiet failure or a policy breach for the next run and watch the detection catch it.'],
  ['Where does my data live?', 'In a local SQLite file and a git-backed ledger in your repo. Keys are stored in that database and never shown back in full.'],
];

export function Faq() {
  const [open, setOpen] = useState(-1);
  return (
    <section className="lp-section lp-faq" id="faq">
      <SectionHead index="010" label="Questions" />
      <div className="lp-faq-grid">
        <h2 className="lp-h2 serif">Fair <em className="italic">questions.</em></h2>
        <div>
          {QA.map(([q, a], i) => (
            <div key={q}>
              <SketchRule seed={600 + i} draw={false} />
              <button className="lp-faq-q" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
                <span>{q}</span>
                <motion.span animate={{ rotate: open === i ? 45 : 0 }}><HandIcon name="plus" size={18} /></motion.span>
              </button>
              <AnimatePresence initial={false}>
                {open === i && (
                  <motion.p className="lp-faq-a" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                    {a}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          ))}
          <SketchRule seed={699} draw={false} />
        </div>
      </div>
    </section>
  );
}
