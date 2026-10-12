import { motion, useTransform } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { SketchRule } from '../../../components/sketch/Sketch.jsx';
import { Pinned } from '../Pinned.jsx';

const COMMITS = [
  { sha: 'a41f09c', kind: 'issue', move: '→ L0', text: 'shop-api connected. Every action class starts at zero trust.' },
  { sha: '4f1a2c8', kind: 'promote', move: 'L0 → L1', text: 'test-run: 3 verified runs; “npm test” runs on its own.' },
  { sha: '9c03e71', kind: 'promote', move: 'L1 → L2', text: 'test-run: 8 verified, 0 failed - below break-even.' },
  { sha: 'e58f3b1', kind: 'promote', move: 'L1 → L2', text: 'file-edit: 24 verified turns; edits run on their own.' },
  { sha: '2c9d1a0', kind: 'demote', move: 'L2 → L0', text: 'file-edit: over-editing, 210 lines in 3 files. Entire checkpoint 3f9c2a1.' },
  { sha: '48a5f4c', kind: 'restore', move: 'L0 → L1', text: '“Reverted format.js, reviewed the turn.” - reviewer' },
];
const ICON = { issue: 'flag', promote: 'arrow-up-right', demote: 'bolt', restore: 'refresh' };

/* Scene 07 - pinned horizontal track: the git ledger slides past as you
   scroll down, one commit per autonomy change. */
export function LedgerTrack() {
  return (
    <Pinned id="ledger" length={3} className="sc-ledger">
      {(p) => <Track p={p} />}
    </Pinned>
  );
}

function Track({ p }) {
  const x = useTransform(p, [0.05, 0.95], ['0%', '-62%']);
  return (
    <div className="sc-wrap sc-ledger-wrap">
      <div className="sc-ledger-head">
        <div className="sc-head"><span className="mono muted">(010)</span><ScrambleText className="mono" text="The ledger" /></div>
        <h2 className="sc-title serif">Every change is a <em className="italic">commit.</em></h2>
        <p className="sc-body">Promotions, demotions and restores are appended to <code className="mono">ledger/license_ledger.jsonl</code> and committed - a history you can diff, blame and audit.</p>
      </div>
      <div className="sc-ledger-rail">
        <SketchRule seed={1201} draw={false} />
        <motion.ol className="sc-ledger-track" style={{ x }}>
          {COMMITS.map((c) => (
            <li key={c.sha} className={`sc-commit is-${c.kind}`}>
              <span className="sc-commit-node"><HandIcon name={ICON[c.kind]} size={18} /></span>
              <span className="mono sc-commit-sha">commit {c.sha}</span>
              <b className="serif">{c.kind} · {c.move}</b>
              <p>{c.text}</p>
            </li>
          ))}
        </motion.ol>
      </div>
    </div>
  );
}
