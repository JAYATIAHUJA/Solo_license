import { useState } from 'react';
import { motion, useMotionValueEvent, useTransform } from 'motion/react';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';

/* Scene 02 — the failure nobody sees. Scroll plays it out:
   agent claims success → database row refuses to move → stamp. */
export function Problem() {
  return (
    <Pinned id="problem" length={2.6} className="sc-problem">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

function Scene({ p }) {
  const [stage, setStage] = useState(0);
  useMotionValueEvent(p, 'change', (v) => setStage(v < 0.18 ? 0 : v < 0.4 ? 1 : v < 0.62 ? 2 : v < 0.8 ? 3 : 4));

  const chatY = useTransform(p, [0.05, 0.2], [40, 0]);
  const chatO = useTransform(p, [0.05, 0.2], [0, 1]);
  const dbO = useTransform(p, [0.22, 0.36], [0, 1]);
  const dbX = useTransform(p, [0.22, 0.36], [60, 0]);
  const shake = stage >= 3 ? [0, -10, 8, -5, 3, 0] : 0;

  return (
    <div className="sc-wrap">
      <div className="sc-head">
        <span className="mono muted">(002)</span>
        <ScrambleText className="mono" text="The failure nobody sees" />
      </div>
      <h2 className="sc-title serif">
        The tool said <em className="italic">“done.”</em><br />
        The database said <em className="italic">nothing.</em>
      </h2>

      <motion.div className="sc-problem-grid" animate={{ x: shake }} transition={{ duration: 0.45 }}>
        <motion.div style={{ y: chatY, opacity: chatO }}>
          <SketchBox className="sc-chat" seed={901}>
            <span className="mono muted">agent · refund tool</span>
            <div className="sc-bubble">
              <HandIcon name="check" size={18} />
              <span>Refund processed for <b>ORD-1002</b> — <b>$40.00</b>.</span>
            </div>
            <span className="sc-chat-meta mono">tool.result · ok=true</span>
          </SketchBox>
        </motion.div>

        <motion.div style={{ opacity: dbO, x: dbX }}>
          <SketchBox className="sc-db" seed={902}>
            <span className="mono muted">sqlite · orders</span>
            <table>
              <thead><tr><th>order_id</th><th>amount</th><th>refunded_amount</th></tr></thead>
              <tbody>
                <tr><td>ORD-1001</td><td>25.00</td><td>0.00</td></tr>
                <tr className={stage >= 2 ? 'is-hit' : ''}>
                  <td>ORD-1002</td><td>40.00</td>
                  <td><motion.b key={stage >= 2 ? 'hit' : 'idle'} animate={stage >= 2 ? { scale: [1, 1.25, 1] } : {}} transition={{ duration: 0.4 }}>0.00</motion.b></td>
                </tr>
                <tr><td>ORD-1003</td><td>15.00</td><td>0.00</td></tr>
              </tbody>
            </table>
            {stage >= 2 && <motion.span className="sc-db-note hand" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>← still zero.</motion.span>}
          </SketchBox>
        </motion.div>

        <div className="sc-problem-stamp">
          <Stamp text="Unverified" sub="claim ≠ reality" show={stage >= 3} tone="signal" size="lg" angle={-12} />
        </div>
      </motion.div>

      <motion.p className="sc-foot" animate={{ opacity: stage >= 4 ? 1 : 0, y: stage >= 4 ? 0 : 12 }}>
        Most agents would mark this “done” and move on. Solo License reads the database back after <b>every</b> action — and a mismatch costs the agent its license.
      </motion.p>
    </div>
  );
}
