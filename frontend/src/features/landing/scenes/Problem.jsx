import { useState } from 'react';
import { motion, useMotionValueEvent, useTransform } from 'motion/react';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';

/* Scene 02 - the over-edit nobody asked for. Scroll plays it out:
   agent claims a one-line fix → the diff says otherwise → stamp. */
export function Problem() {
  return (
    <Pinned id="problem" length={2.2} className="sc-problem">
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
        <span className="mono muted">(003)</span>
        <ScrambleText className="mono" text="The diff nobody asked for" />
      </div>
      <h2 className="sc-title serif">
        You asked for <em className="italic">one line.</em><br />
        It changed <em className="italic">fifty.</em>
      </h2>

      <motion.div className="sc-problem-grid" animate={{ x: shake }} transition={{ duration: 0.45 }}>
        <motion.div style={{ y: chatY, opacity: chatO }}>
          <SketchBox className="sc-chat" seed={901}>
            <span className="mono muted">you → coding agent</span>
            <div className="sc-bubble">
              <HandIcon name="check" size={18} />
              <span>Fixed the off-by-one in <b>cart.js</b>. All done!</span>
            </div>
            <span className="sc-chat-meta mono">request · “fix the off-by-one in cart.js”</span>
          </SketchBox>
        </motion.div>

        <motion.div style={{ opacity: dbO, x: dbX }}>
          <SketchBox className="sc-db" seed={902}>
            <span className="mono muted">git diff --stat</span>
            <table>
              <thead><tr><th>file</th><th>asked for?</th><th>lines</th></tr></thead>
              <tbody>
                <tr><td>cart.js</td><td>yes</td><td>2</td></tr>
                <tr className={stage >= 2 ? 'is-hit' : ''}>
                  <td>format.js</td><td>no</td>
                  <td><motion.b key={stage >= 2 ? 'hit' : 'idle'} animate={stage >= 2 ? { scale: [1, 1.25, 1] } : {}} transition={{ duration: 0.4 }}>+38</motion.b></td>
                </tr>
                <tr><td>utils.js</td><td>no</td><td>+12</td></tr>
              </tbody>
            </table>
            {stage >= 2 && <motion.span className="sc-db-note hand" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>← nobody asked.</motion.span>}
          </SketchBox>
        </motion.div>

        <div className="sc-problem-stamp">
          <Stamp text="Over-edited" sub="asked ≠ changed" show={stage >= 3} tone="signal" size="lg" angle={-12} />
        </div>
      </motion.div>

      <motion.p className="sc-foot" animate={{ opacity: stage >= 4 ? 1 : 0, y: stage >= 4 ? 0 : 12 }}>
        Today you either approve every command, or hand over full access and review fifty-line diffs. Solo License checks <b>every</b> turn against what you asked and runs your tests - and an agent that over-edits or breaks them loses its license.
      </motion.p>
    </div>
  );
}
