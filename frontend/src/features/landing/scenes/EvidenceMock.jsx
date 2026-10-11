import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { motion, useMotionValueEvent, useScroll, useTransform } from 'motion/react';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { roughPath } from '../../../components/sketch/rough.js';
import { AppMock } from './AppMock.jsx';

/* Hand-written notes that point at real elements inside the mockup
   (data-anchor). Both the note positions and the arrows are measured from the
   live layout, so they land on target at every screen size; a note that has
   no free space to sit in is simply not shown. */
const NOTES = [
  { id: 'verified', text: 'the diff said no' },
  { id: 'tool', text: 'the agent said done' },
  { id: 'restore', text: 'you choose how much trust comes back' },
];

function arrow(from, to, seed) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const bow = Math.min(36, len * 0.25);
  const cx = (from.x + to.x) / 2 - (dy / len) * bow;
  const cy = (from.y + to.y) / 2 + (dx / len) * bow;
  const shaft = roughPath(`M${from.x} ${from.y} Q${cx} ${cy} ${to.x} ${to.y}`, { seed, roughness: 0.8, strokeWidth: 1.6, bowing: 0.4 });
  const a = Math.atan2(to.y - cy, to.x - cx);
  const h = 10;
  const p1 = [to.x - h * Math.cos(a - 0.5), to.y - h * Math.sin(a - 0.5)];
  const p2 = [to.x - h * Math.cos(a + 0.5), to.y - h * Math.sin(a + 0.5)];
  const head = roughPath(`M${p1[0]} ${p1[1]} L${to.x} ${to.y} L${p2[0]} ${p2[1]}`, { seed: seed + 1, roughness: 0.5, strokeWidth: 1.6 });
  return [...shaft, ...head].map((x) => x.d);
}

export function EvidenceMock() {
  const ref = useRef(null);
  const stageRef = useRef(null);
  const noteRefs = useRef({});
  const [layout, setLayout] = useState({});
  const { scrollYProgress: p } = useScroll({ target: ref, offset: ['start end', 'center center'] });
  const rotateX = useTransform(p, [0, 1], [38, 0]);
  const scale = useTransform(p, [0, 1], [0.78, 1]);
  const y = useTransform(p, [0, 1], [120, 0]);
  const notes = useTransform(p, [0.86, 1], [0, 1]);

  const measure = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const base = stage.getBoundingClientRect();
    const rect = (el) => {
      const r = el.getBoundingClientRect();
      return { l: r.left - base.left, t: r.top - base.top, r: r.right - base.left, b: r.bottom - base.top, w: r.width, h: r.height };
    };
    const q = (id) => stage.querySelector(`[data-anchor="${id}"]`);
    const packet = q('packet');
    if (!packet) return;
    const pk = rect(packet);
    const next = {};
    // notes may only sit to the right of the longest trace line
    const textEnd = Math.max(0, ...[...stage.querySelectorAll('.am-trace li span')].map((el) => rect(el).r));

    // "the tool said yes": inside the packet, right of the tool.result text
    const tool = q('tool');
    const toolNote = noteRefs.current.tool;
    if (tool && toolNote) {
      const tr = rect(tool);
      const w = toolNote.offsetWidth;
      const h = toolNote.offsetHeight;
      const x = pk.r - w - 18;
      if (x - textEnd > 60) {
        const top = tr.t + tr.h / 2 - h / 2 + 30;
        next.tool = { left: x, top, d: arrow({ x: x - 6, y: top + h / 2 }, { x: tr.r + 8, y: tr.t + tr.h / 2 }, 151) };
      }
    }

    // "the database said no": under the $0.00, pointing up at it
    const ver = q('verified');
    const verNote = noteRefs.current.verified;
    if (ver && verNote) {
      const vr = rect(ver);
      const w = verNote.offsetWidth;
      const h = verNote.offsetHeight;
      const left = Math.min(pk.r - w - 18, vr.l + 24);
      const top = vr.b + 18;
      const toolTop = next.tool ? next.tool.top : Infinity;
      if (left - textEnd > 24 && top + h + 10 < toolTop) {
        next.verified = { left, top, d: arrow({ x: left + w * 0.3, y: top - 4 }, { x: vr.l + 30, y: vr.b - 10 }, 163) };
      }
    }

    // "you choose…": below the frame, pointing up at the restore controls
    const res = q('restore');
    const resNote = noteRefs.current.restore;
    if (res && resNote) {
      const rr = rect(res);
      const w = resNote.offsetWidth;
      const left = Math.max(0, Math.min(base.width - w, rr.l + rr.w * 0.35));
      const top = Math.max(pk.b, rr.b) + 46;
      next.restore = { left, top, d: arrow({ x: left + w * 0.25, y: top - 4 }, { x: rr.l + rr.w * 0.18, y: rr.b + 6 }, 175) };
    }
    setLayout(next);
  }, []);

  useLayoutEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    if (stageRef.current) ro.observe(stageRef.current);
    document.fonts?.ready.then(measure);
    return () => ro.disconnect();
  }, [measure]);
  // the frame un-tilts as you scroll; re-measure while the notes fade in
  useMotionValueEvent(p, 'change', (v) => { if (v > 0.84) measure(); });

  return (
    <section id="evidence" className="lp-section sc-evidence" ref={ref}>
      <div className="sc-evidence-head">
        <div className="sc-head"><span className="mono muted">(008)</span><ScrambleText className="mono" text="The evidence packet" /></div>
        <h2 className="sc-title serif">Recovery is a <em className="italic">judgement,</em> not a retry.</h2>
      </div>
      <div className="sc-evidence-stage" ref={stageRef} style={{ perspective: 1600 }}>
        <motion.div className="sc-evidence-frame" style={{ rotateX, scale, y, transformOrigin: '50% 100%' }}>
          <AppMock />
        </motion.div>
        {NOTES.map((n) => {
          const pos = layout[n.id];
          return (
            <motion.span
              key={n.id}
              ref={(el) => { noteRefs.current[n.id] = el; }}
              className="sc-ev-note hand"
              style={{ opacity: notes, left: pos?.left ?? 0, top: pos?.top ?? 0, visibility: pos ? 'visible' : 'hidden' }}
            >
              {n.text}
            </motion.span>
          );
        })}
        <motion.svg className="sc-ev-arrows" style={{ opacity: notes }} aria-hidden="true">
          {Object.entries(layout).flatMap(([id, l]) => l.d.map((d, i) => <path key={`${id}-${i}`} d={d} />))}
        </motion.svg>
      </div>
    </section>
  );
}
