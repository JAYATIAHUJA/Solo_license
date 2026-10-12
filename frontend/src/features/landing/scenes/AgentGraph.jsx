import { useMemo, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useTransform } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { roughPath } from '../../../components/sketch/rough.js';
import { Pinned } from '../Pinned.jsx';

/* Node positions in a 1000×560 board (percent-free so connectors line up). */
const NODES = [
  { x: 110, y: 120, icon: 'message', title: 'Your request', out: '“fix the off-by-one in cart.js”', body: 'UserPromptSubmit opens a turn: the request and a snapshot of the working tree.' },
  { x: 400, y: 120, icon: 'spark', title: 'Permission prompt', out: 'Bash · npm test → action class test-run', body: 'Claude Code is about to ask you. The hook classifies the call instead - rules first, Jev only for the unknown.' },
  { x: 690, y: 120, icon: 'key', title: 'License check', out: 'test-run@shop-api · L1 · approved → allow', body: 'The license for this class, in this repo, decides. The model never does.' },
  { x: 690, y: 400, icon: 'play', title: 'The agent works', out: 'npm test ran · cart.js edited', body: 'Every tool result is recorded. A failed change counts against its class at once.' },
  { x: 400, y: 400, icon: 'eye', title: 'Turn check', out: '2 lines in 1 file · scope 5/5 · tests pass ✓', body: 'Once per turn: the diff against the request, then the tests. Only this counts as proof.' },
  { x: 110, y: 400, icon: 'dial', title: 'Move the dial', out: 'verified 3 of 3 → test-run earns L1', body: 'Verified: credit toward the next level. Over-edit or failing tests: straight to L0.' },
];
const W = 200;
const H = 92;

function edge(a, b, i) {
  const from = NODES[a];
  const to = NODES[b];
  const sameRow = from.y === to.y;
  const sx = sameRow ? from.x + (to.x > from.x ? W / 2 : -W / 2) : from.x;
  const sy = sameRow ? from.y : from.y + H / 2;
  const ex = sameRow ? to.x + (to.x > from.x ? -W / 2 : W / 2) : to.x;
  const ey = sameRow ? to.y : to.y - H / 2;
  const mx = (sx + ex) / 2;
  const my = (sy + ey) / 2;
  const d = sameRow ? `M${sx} ${sy} C ${mx} ${sy - 18}, ${mx} ${ey + 18}, ${ex} ${ey}` : `M${sx} ${sy} C ${sx + 40} ${my}, ${ex + 40} ${my}, ${ex} ${ey}`;
  return roughPath(d, { seed: 950 + i, roughness: 1, strokeWidth: 1.6, bowing: 1 })[0].d;
}

export function AgentGraph() {
  return (
    <Pinned id="agent" length={2.7} className="sc-agent">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Edge({ d, p, range }) {
  const length = useTransform(p, range, [0, 1]);
  return <motion.path d={d} style={{ pathLength: length }} className="ag-edge" />;
}

function Scene({ p }) {
  const [active, setActive] = useState(0);
  useMotionValueEvent(p, 'change', (v) => setActive(Math.min(NODES.length - 1, Math.max(0, Math.floor(((v - 0.05) / 0.85) * NODES.length)))));
  const edges = useMemo(() => NODES.slice(1).map((_, i) => edge(i, i + 1, i)), []);
  const node = NODES[active];

  return (
    <div className="sc-wrap sc-agent-wrap">
      <div className="sc-agent-copy">
        <div className="sc-head">
          <span className="mono muted">(005)</span>
          <ScrambleText className="mono" text="One loop, every run" />
        </div>
        <h2 className="sc-title serif">Watch it <em className="italic">work.</em></h2>
        <AnimatePresence mode="wait">
          <motion.div key={active} className="sc-agent-step" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }} transition={{ duration: 0.35 }}>
            <span className="mono muted">Step {String(active + 1).padStart(2, '0')} / 06</span>
            <b className="serif">{node.title}</b>
            <p>{node.body}</p>
            <code className="mono">{node.out}</code>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="ag-board">
        <svg viewBox="0 0 1000 560" className="ag-svg" aria-hidden="true">
          {edges.map((d, i) => {
            const start = 0.05 + ((i + 0.6) / NODES.length) * 0.85;
            return <Edge key={i} d={d} p={p} range={[start, start + 0.85 / NODES.length * 0.7]} />;
          })}
        </svg>
        {NODES.map((n, i) => (
          <motion.div
            key={n.title}
            className={`ag-node ${i === active ? 'is-active' : ''} ${i < active ? 'is-done' : ''}`}
            style={{ left: `${(n.x / 1000) * 100}%`, top: `${(n.y / 560) * 100}%` }}
            animate={{ scale: i === active ? 1.06 : 1, opacity: i <= active ? 1 : 0.35 }}
            transition={{ type: 'spring', stiffness: 260, damping: 22 }}
          >
            <HandIcon name={n.icon} size={22} />
            <span>{n.title}</span>
            {i < active && <i className="ag-check"><HandIcon name="check" size={12} /></i>}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
