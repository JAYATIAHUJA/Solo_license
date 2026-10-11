import { useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent } from 'motion/react';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';

/* Scene - what it looks like inside the agent. A real-looking coding-agent
   session types itself out as you scroll; Solo License's answers appear
   inline exactly where the agent would otherwise stop and ask you. */
const LINES = [
  { kind: 'you', text: 'fix the off-by-one in discount.js' },
  { kind: 'tool', text: 'Bash(npm test)' },
  { kind: 'gate', tone: 'ok', text: 'auto-approved · test-run is L1 in shop-api (approved 3×, verified 3×)' },
  { kind: 'out', text: '✗ the 10th item is already discounted  - expected 1, got 0' },
  { kind: 'tool', text: 'Edit(discount.js)  - count > 10 → count >= 10' },
  { kind: 'tool', text: 'Edit(format.js)  - “tidied while I was here” · +160 lines' },
  { kind: 'agent', text: 'Done! Fixed the off-by-one and cleaned up formatting.' },
  { kind: 'gate', tone: 'bad', text: 'sent back · over-editing: 162 lines in 2 files for this request (scope 2/5). Revert format.js.' },
  { kind: 'tool', text: 'Bash(git checkout -- format.js)' },
  { kind: 'gate', tone: 'ok', text: 'verified · 2 lines in 1 file · scope 5/5 · npm test passed' },
  { kind: 'you', text: 'ship it' },
  { kind: 'tool', text: 'Bash(git push --force origin main)' },
  { kind: 'gate', tone: 'bad', text: 'blocked · force-pushes a protected branch. Never allowed, at any level.' },
];

const AGENTS = ['Claude Code', 'Codex', 'Cursor', 'Gemini CLI', 'Windsurf', 'Copilot', 'OpenCode', 'Cline'];

export function Terminal() {
  return (
    <Pinned id="terminal" length={3.2} className="sc-terminal">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Scene({ p }) {
  const [shown, setShown] = useState(1);
  const [agent, setAgent] = useState(0);
  useMotionValueEvent(p, 'change', (v) => {
    setShown(Math.max(1, Math.min(LINES.length, Math.ceil(((v - 0.04) / 0.86) * LINES.length))));
    setAgent(Math.min(AGENTS.length - 1, Math.floor(v * AGENTS.length)));
  });

  return (
    <div className="sc-wrap sc-term-wrap">
      <div className="sc-term-copy">
        <div className="sc-head">
          <span className="mono muted">(002)</span>
          <ScrambleText className="mono" text="Inside your agent" />
        </div>
        <h2 className="sc-title serif">It asks less <em className="italic">because</em> it earned it.</h2>
        <p className="sc-body">
          Solo License answers the permission prompt for the agent - only for the kinds of actions it has
          already proven it does right in this repo. At the end of every turn it checks the diff against what you
          asked and runs your tests. Everything else still comes to you.
        </p>
        <p className="mono sc-term-agents">
          works in{' '}
          <AnimatePresence mode="wait">
            <motion.b key={agent} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}>
              {AGENTS[agent]}
            </motion.b>
          </AnimatePresence>
        </p>
      </div>

      <div className="term" role="img" aria-label="A coding-agent session with Solo License's decisions inline">
        <div className="term-chrome"><i /><i /><i /><span className="mono">~/shop-api · agent session</span></div>
        <ol className="term-body mono">
          {LINES.slice(0, shown).map((l, i) => (
            <motion.li
              key={i}
              className={`term-line is-${l.kind} ${l.tone ? `is-${l.tone}` : ''}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25 }}
            >
              <span className="term-mark">{{ you: '>', tool: '⏺', gate: '§', out: '⎿', agent: '⏺' }[l.kind]}</span>
              <span>{l.kind === 'gate' ? <><b>Solo License</b> {l.text}</> : l.text}</span>
            </motion.li>
          ))}
          <li className="term-line term-cursor"><span className="term-mark">&gt;</span><i /></li>
        </ol>
      </div>
    </div>
  );
}
