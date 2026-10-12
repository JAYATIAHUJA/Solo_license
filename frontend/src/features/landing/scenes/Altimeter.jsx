import { useEffect, useState } from 'react';
import { motion, useScroll, useSpring } from 'motion/react';

const STOPS = [
  ['top', 'Intro'],
  ['terminal', 'In your agent'],
  ['problem', 'Problem'],
  ['journey', 'Earning'],
  ['agent', 'The loop'],
  ['crash', 'The crash'],
  ['detections', 'Detections'],
  ['fixes', 'Remediation'],
  ['ledger', 'Ledger'],
  ['faq', 'FAQ'],
];

/** Zero-style scroll scale on the right edge: a needle tracks page progress
 *  and the label names the scene you are in. Click a tick to jump. */
export function Altimeter() {
  const { scrollYProgress } = useScroll();
  const needle = useSpring(scrollYProgress, { stiffness: 120, damping: 24 });
  const [current, setCurrent] = useState('top');

  useEffect(() => {
    const els = STOPS.map(([id]) => document.getElementById(id)).filter(Boolean);
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setCurrent(e.target.id); });
    }, { rootMargin: '-45% 0px -45% 0px' });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  const go = (id) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (window.__lenis) window.__lenis.scrollTo(el);
    else el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <nav className="alt" aria-label="Page progress">
      <div className="alt-scale">
        {STOPS.map(([id, label], i) => (
          <button key={id} className={`alt-tick ${current === id ? 'is-on' : ''}`} style={{ top: `${(i / (STOPS.length - 1)) * 100}%` }} onClick={() => go(id)} aria-label={label}>
            <i />
            <span className="mono">{String(i + 1).padStart(2, '0')}</span>
          </button>
        ))}
        <motion.span className="alt-needle" style={{ scaleY: needle }} />
      </div>
      <span className="alt-label mono">{STOPS.find(([id]) => id === current)?.[1]}</span>
    </nav>
  );
}
