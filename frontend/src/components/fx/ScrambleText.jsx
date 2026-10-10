import { useEffect, useRef, useState } from 'react';
import { useInView } from 'motion/react';

const GLYPHS = '#%&/<>[]{}=+*01';

/** Text that decrypts itself into place when it scrolls into view
 *  (in the spirit of reactbits' DecryptedText). */
export function ScrambleText({ text, className = '', duration = 900 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [out, setOut] = useState(text.replace(/\S/g, ' '));

  useEffect(() => {
    if (!inView) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setOut(text); return undefined; }
    const start = performance.now();
    let raf;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const settled = Math.floor(p * text.length);
      setOut(text.split('').map((ch, i) => (i < settled || ch === ' ' ? ch : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join(''));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, text, duration]);

  return <span ref={ref} className={className} aria-label={text}><span aria-hidden="true">{out}</span></span>;
}
