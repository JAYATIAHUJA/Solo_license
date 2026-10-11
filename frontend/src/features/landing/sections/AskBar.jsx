import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const COMMANDS = [
  '/plugin marketplace add JAYATIAHUJA/Solo_license',
  '/plugin install solo-license@solo-license',
  'python -m sololicense.coding.install path/to/repo',
];

/** The install line, in the hero's "ask anything" bar: the commands cycle,
 *  one click copies the one on screen. */
export function AskBar() {
  const [i, setI] = useState(0);
  const [copied, setCopied] = useState(false);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return undefined;
    const t = setInterval(() => setI((n) => (n + 1) % COMMANDS.length), 3200);
    return () => clearInterval(t);
  }, [paused]);

  function copy(e) {
    e.preventDefault();
    navigator.clipboard?.writeText(COMMANDS[i])
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
      .catch(() => {});
  }

  return (
    <form
      className={`lp-ask ${paused ? 'is-focused' : ''}`}
      onSubmit={copy}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <HandIcon name="play" size={18} />
      <div className="lp-ask-field" aria-live="polite">
        <AnimatePresence mode="wait">
          <motion.code
            key={i}
            className="lp-ask-hint mono"
            style={{ color: 'var(--ink)', textTransform: 'none', letterSpacing: 0 }}
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -12, opacity: 0 }}
            transition={{ duration: 0.35 }}
          >
            {COMMANDS[i]}
          </motion.code>
        </AnimatePresence>
      </div>
      <button className="btn btn-ink btn-sm" type="submit">{copied ? 'Copied' : 'Copy'} <HandIcon name="arrow-right" size={14} /></button>
    </form>
  );
}
