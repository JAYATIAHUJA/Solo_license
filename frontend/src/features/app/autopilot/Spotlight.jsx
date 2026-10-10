import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

const PAD = 8;
const CALLOUT_W = 340;

function measureEl(el) {
  const r = el.getBoundingClientRect();
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 };
}

/** Dims and blurs the page except one element, and points at it with a short
 *  explanation. `selector` null = blur everything and show the note centred
 *  (used while a step is working or when the target is not on screen). */
export function Spotlight({ selector, label, title, text, busy, reserveRight = 0 }) {
  const [rect, setRect] = useState(null);
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight });

  useEffect(() => {
    let el = null;
    let tries = 0;
    let findTimer;
    const measure = () => {
      setViewport({ w: window.innerWidth, h: window.innerHeight });
      if (el && el.isConnected) setRect(measureEl(el));
    };
    const find = () => {
      el = selector ? document.querySelector(selector) : null;
      if (el) {
        el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        measure();
      } else if (selector && tries < 40) {
        tries += 1;
        findTimer = window.setTimeout(find, 150);
      }
    };
    setRect(null);
    find();
    // Layout shifts while data refreshes and while the smooth scroll runs.
    const tick = window.setInterval(measure, 250);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.clearTimeout(findTimer);
      window.clearInterval(tick);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [selector]);

  const { w, h } = viewport;
  const narrow = w < 700;
  const hole = selector && rect ? rect : null;

  let callout;
  let arrow = null;
  if (narrow || !hole) {
    callout = narrow
      ? { top: 12, left: 12, width: w - 24 }
      : { top: Math.max(24, h / 2 - 120), left: Math.max(16, (w - reserveRight) / 2 - CALLOUT_W / 2), width: CALLOUT_W };
  } else {
    const maxLeft = w - reserveRight - CALLOUT_W - 16;
    const left = Math.max(16, Math.min(hole.left, maxLeft));
    const below = h - (hole.top + hole.height) > 200;
    const top = below ? hole.top + hole.height + 14 : Math.max(12, hole.top - 14 - 190);
    callout = { top, left, width: CALLOUT_W };
    const pointX = Math.max(left + 18, Math.min(hole.left + Math.min(hole.width / 2, 120), left + CALLOUT_W - 18));
    arrow = { left: pointX - left - 9, side: below ? 'top' : 'bottom' };
  }

  const panes = hole
    ? [
        { top: 0, left: 0, width: w, height: Math.max(0, hole.top) },
        { top: hole.top + hole.height, left: 0, width: w, height: Math.max(0, h - hole.top - hole.height) },
        { top: hole.top, left: 0, width: Math.max(0, hole.left), height: hole.height },
        { top: hole.top, left: hole.left + hole.width, width: Math.max(0, w - hole.left - hole.width), height: hole.height },
      ]
    : [{ top: 0, left: 0, width: w, height: h }];

  return createPortal(
    <div className="sp" aria-hidden={false}>
      {panes.map((p, i) => <div key={i} className="sp-pane" style={p} />)}
      {hole && <div className="sp-ring" style={hole} />}
      <div className="sp-note" style={callout} role="status" aria-live="polite">
        {arrow && <i className={`sp-arrow sp-arrow-${arrow.side}`} style={{ left: arrow.left }} />}
        <span className="sp-label">{label}</span>
        <b>{title}</b>
        <p>{text}</p>
        {busy && <p className="sp-busy">Working on it…</p>}
      </div>
    </div>,
    document.body,
  );
}
