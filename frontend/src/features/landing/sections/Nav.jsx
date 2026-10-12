import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Logo } from '../../../components/brand/Logo.jsx';

const LINKS = [
  ['/#terminal', 'In your agent'],
  ['/#crash', 'The crash'],
  ['/#tour', 'Product'],
  ['/install', 'Install'],
  ['/#faq', 'FAQ'],
];

export function Nav() {
  const { scrollY } = useScroll();
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);
  useMotionValueEvent(scrollY, 'change', (y) => setSolid(y > 24));

  return (
    <header className={`lp-nav ${solid ? 'is-solid' : ''}`}>
      <div className="lp-nav-inner">
        <Link to="/" className="lp-logo"><Logo /> Solo License<sup>®</sup></Link>
        <nav className="lp-links" aria-label="Sections">
          {LINKS.map(([href, label]) => <a key={href} href={href}>{label}</a>)}
        </nav>
        <div className="lp-nav-cta">
          <a href="https://github.com/JAYATIAHUJA/Solo_license" className="btn btn-ghost btn-sm">GitHub</a>
          <Link to="/app" className="btn btn-ink btn-sm">Open app <HandIcon name="arrow-up-right" size={14} /></Link>
          <button className="lp-burger" onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}>
            <HandIcon name={open ? 'cross' : 'menu'} size={22} />
          </button>
        </div>
      </div>
      <AnimatePresence>
        {open && (
          <motion.nav
            className="lp-sheet"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
          >
            {LINKS.map(([href, label]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}</a>)}
            <Link to="/app" className="btn btn-ink">Open app</Link>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
