import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { markIntroPlayed, saveSignature } from '../../../lib/signature.js';
import { Stamp } from '../../../components/fx/Stamp.jsx';
import { DitherField } from '../../../components/shader/PaperBackdrop.jsx';
import { SplitTitle } from './SplitTitle.jsx';
import { SignaturePad } from './SignaturePad.jsx';
import './gate.css';

const ANSWERS = {
  yes: 'Bold. Most people wouldn’t - not on day one.',
  no: 'Good. Neither would we. That’s why it has to earn it.',
};

/** First-visit intro: a question (Santioni), a signature (Zero), and an ink
 *  blot that floods the screen and reveals the site. Shown once. */
export function Gate({ onDone }) {
  const [phase, setPhase] = useState('ask'); // ask → answer → sign → issued → flood
  const [answer, setAnswer] = useState(null);

  useEffect(() => {
    document.documentElement.style.overflow = 'hidden';
    return () => { document.documentElement.style.overflow = ''; };
  }, []);

  function choose(kind) {
    setAnswer(kind);
    setPhase('answer');
    setTimeout(() => setPhase('sign'), 1900);
  }
  function signed(d) {
    saveSignature(d);
    setPhase('issued');
    setTimeout(() => setPhase('flood'), 1100);
    setTimeout(() => { markIntroPlayed(); onDone(); }, 2100);
  }
  function skip() { markIntroPlayed(); onDone(); }

  return (
    <motion.div className="gate" exit={{ opacity: 0 }} transition={{ duration: 0.6 }}>
      <DitherField className="gate-shader" shape="sphere" speed={0.25} size={3} />
      <button className="gate-skip mono" onClick={skip}>Skip intro →</button>

      <AnimatePresence mode="wait">
        {(phase === 'ask' || phase === 'answer') && (
          <motion.div key="ask" className="gate-card" exit={{ opacity: 0, y: -20 }} transition={{ duration: 0.4 }}>
            <p className="mono gate-kicker">Solo License - before we start</p>
            <SplitTitle lines={['Would you give', 'your coding agent', 'full access?']} />
            <AnimatePresence mode="wait">
              {phase === 'ask' ? (
                <motion.div key="btns" className="gate-choices" initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay: 0.9 } }} exit={{ opacity: 0 }}>
                  <button className="gate-choice" onClick={() => choose('yes')}>Yes</button>
                  <button className="gate-choice" onClick={() => choose('no')}>Not yet</button>
                </motion.div>
              ) : (
                <motion.p key="ans" className="gate-answer hand" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  {ANSWERS[answer]}
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {(phase === 'sign' || phase === 'issued' || phase === 'flood') && (
          <motion.div key="sign" className="gate-card gate-sign" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <p className="mono gate-kicker">License № 0001 · action class: test-run</p>
            <h2 className="serif gate-sign-title">Sign its <em className="italic">first</em> license.</h2>
            <p className="gate-sign-sub">It starts at <b>L0 - asks you</b>. Everything above that, it earns.</p>
            <div className="gate-sign-body">
              <SignaturePad onSigned={signed} />
              <div className="gate-stamp"><Stamp text="Issued" sub="L0 · asks you" show={phase !== 'sign'} size="lg" /></div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {phase === 'flood' && (
        <svg className="gate-flood" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <filter id="ink-blot" x="-50%" y="-50%" width="200%" height="200%">
              <feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="3" seed="9" />
              <feDisplacementMap in="SourceGraphic" scale="9" />
            </filter>
          </defs>
          <motion.circle cx="50" cy="56" fill="var(--ink)" filter="url(#ink-blot)" initial={{ r: 0 }} animate={{ r: 95 }} transition={{ duration: 0.9, ease: [0.7, 0, 0.3, 1] }} />
        </svg>
      )}
    </motion.div>
  );
}
