import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const PROMPTS = [
  'My order ORD-1002 arrived damaged, refund $40 please',
  'Charged twice for ORD-1003 - refund $7.50',
  'Never received ORD-1004, I want my money back',
];

/** "Ask anything" bar (Think Company's hero idea), wired to the real agent:
 *  submitting opens the Agent desk with the message ready to run. */
export function AskBar() {
  const navigate = useNavigate();
  const [value, setValue] = useState('');
  const [hint, setHint] = useState(0);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setHint((h) => (h + 1) % PROMPTS.length), 3200);
    return () => clearInterval(t);
  }, []);

  function submit(e) {
    e.preventDefault();
    const message = value.trim() || PROMPTS[hint];
    navigate(`/app/agent?message=${encodeURIComponent(message)}`);
  }

  return (
    <form className={`lp-ask ${focused ? 'is-focused' : ''}`} onSubmit={submit}>
      <HandIcon name="message" size={18} />
      <div className="lp-ask-field">
        <input
          aria-label="Paste a customer message"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
        {!value && (
          <AnimatePresence mode="wait">
            <motion.span
              key={hint}
              className="lp-ask-hint"
              initial={{ y: 12, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -12, opacity: 0 }}
              transition={{ duration: 0.35 }}
            >
              {PROMPTS[hint]}
            </motion.span>
          </AnimatePresence>
        )}
      </div>
      <button className="btn btn-ink btn-sm" type="submit">Run it <HandIcon name="arrow-right" size={14} /></button>
    </form>
  );
}
