import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { SectionHead } from '../Reveal.jsx';

const QA = [
  ['Isn\u2019t this what Claude Code\u2019s auto mode does?', 'Auto mode asks one question about each call: is this action dangerous? Solo License asks a different one: has this agent earned this kind of action, in this repo, and did it actually work? It learns from verified outcomes, takes autonomy back on a failure, sends over-edited turns back, and records every change. The two work side by side.'],
  ['Does it call an AI on every edit?', 'No. The PermissionRequest hook only fires when Claude Code would show you a prompt, and it is answered from a lookup in milliseconds. A model (Jev, a calibrated classifier) is only asked about commands no rule recognises, and to grade the diff once at the end of a turn.'],
  ['Why hooks and not an MCP server?', 'An MCP tool is something the model may choose to call, so a gate built on it can be skipped. Hooks are run by Claude Code itself on every permission prompt and every turn. The agent cannot go around them.'],
  ['What if the Solo License API is down?', 'Claude Code simply asks you, as it always did. Nothing is ever allowed silently: every failure path ends in “ask a person”.'],
  ['How does it decide when the agent may act alone?', 'From evidence, priced by your costs. Running alone pays only when the failure rate is below the developer time an approval costs \u00f7 the cost of one mistake of that kind. Running tests earns it in a handful of runs; pushing to a remote needs hundreds; deploys and database changes always ask.'],
  ['What happens after a demotion?', 'That action class asks you before every action again. The turn shows what was asked, the diff, the tests and its Entire checkpoint; you can rewind the repo (the changes are kept in git stash) and resume the class at a level you choose. That decision is a git commit.'],
  ['Where does my data live?', 'In a local SQLite file and a git-backed ledger in your repo. Traces go to neatlogs if you add a key, and diffs to Jev only if you add a TypeSafe key.'],
  ['What happens when the agent gets it wrong?', 'It is told what to undo, not just stopped. A failed install comes back with the command that restores the manifest and lockfile. If you mark a decision as wrong, that action class drops to L0 and the agent is told to revert on its next prompt. The same call repeated gets guidance at three tries and is stopped at five. Each of these is a neatlogs incident with its Entire checkpoint.'],
];

export function Faq() {
  const [open, setOpen] = useState(-1);
  return (
    <section className="lp-section lp-faq" id="faq">
      <SectionHead index="013" label="Questions" />
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
