import { useRef, useState } from 'react';
import { motion } from 'motion/react';
import { AUTO_SIGNATURE, SIG_BOX, pointsToPath } from '../../../lib/signature.js';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

/** Draw-to-sign pad. Strokes are smoothed into an ink path. "Sign for me"
 *  pens a signature for you. Calls onSigned(pathD) when issued. */
export function SignaturePad({ onSigned }) {
  const svgRef = useRef(null);
  const [strokes, setStrokes] = useState([]);
  const [auto, setAuto] = useState(false);
  const drawing = useRef(false);

  const toLocal = (e) => {
    const r = svgRef.current.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * SIG_BOX.w, ((e.clientY - r.top) / r.height) * SIG_BOX.h];
  };
  function down(e) {
    if (auto) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    setStrokes((s) => [...s, [toLocal(e)]]);
  }
  function move(e) {
    if (!drawing.current) return;
    const p = toLocal(e);
    setStrokes((s) => {
      const last = s[s.length - 1];
      const prev = last[last.length - 1];
      if (Math.hypot(p[0] - prev[0], p[1] - prev[1]) < 3) return s;
      return [...s.slice(0, -1), [...last, p]];
    });
  }
  function up() { drawing.current = false; }

  const d = auto ? AUTO_SIGNATURE : pointsToPath(strokes);
  const ink = strokes.reduce((n, s) => n + s.length, 0);
  const ready = auto || ink > 12;

  return (
    <div className="sig">
      <SketchBox className="sig-pad" seed={808}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${SIG_BOX.w} ${SIG_BOX.h}`}
          className="sig-svg"
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerLeave={up}
          role="img"
          aria-label="Signature pad: draw with your mouse or finger"
        >
          <line x1="40" y1="160" x2="560" y2="160" className="sig-base" />
          <text x="34" y="154" className="sig-x">×</text>
          {auto ? (
            <motion.path d={d} className="sig-ink" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 2.2, ease: 'easeInOut' }} />
          ) : (
            <path d={d} className="sig-ink" />
          )}
        </svg>
        {!ink && !auto && <span className="sig-hint hand">sign here — mouse or finger</span>}
      </SketchBox>
      <div className="sig-actions">
        <button className="btn btn-ghost btn-sm" onClick={() => { setStrokes([]); setAuto(false); }} disabled={!ink && !auto}>Clear</button>
        <button className="btn btn-line btn-sm" onClick={() => { setStrokes([]); setAuto(true); }}><HandIcon name="spark" size={14} /> Sign for me</button>
        <button className="btn btn-ink" disabled={!ready} onClick={() => onSigned(d)}>Issue license L0 <HandIcon name="arrow-right" size={16} /></button>
      </div>
    </div>
  );
}
