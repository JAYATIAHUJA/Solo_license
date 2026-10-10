import { useMemo, useRef } from 'react';
import { Paths } from './Paths.jsx';
import { roughEllipse, roughLine, roughPath, roughRect } from './rough.js';
import { useSize } from './useSize.js';

const overlay = { position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', overflow: 'visible', color: 'var(--ink)' };

/** A box whose border is drawn by hand. Straight edges, square corners. */
export function SketchBox({ as: Tag = 'div', seed = 1, roughness = 0.7, fill, hachure, draw = false, className = '', style, children, ...rest }) {
  const ref = useRef(null);
  const { width, height } = useSize(ref);
  const paths = useMemo(() => {
    if (!width || !height) return [];
    const opts = { seed, roughness, bowing: 0.3 };
    if (fill) Object.assign(opts, { fill: 'currentColor', fillStyle: fill, hachureGap: hachure ?? 6, fillWeight: 0.8 });
    return roughRect(1.5, 1.5, width - 3, height - 3, opts);
  }, [width, height, seed, roughness, fill, hachure]);
  return (
    <Tag ref={ref} className={className} style={{ position: 'relative', ...style }} {...rest}>
      <svg style={overlay} aria-hidden="true"><Paths paths={paths} draw={draw} /></svg>
      {children}
    </Tag>
  );
}

/** A horizontal hand-drawn rule that spans its container. */
export function SketchRule({ seed = 2, draw = true, className = '', height = 8 }) {
  const ref = useRef(null);
  const { width } = useSize(ref);
  const paths = useMemo(() => (width ? roughLine(0, height / 2, width, height / 2, { seed, roughness: 0.8, bowing: 0.4 }) : []), [width, seed, height]);
  return (
    <div ref={ref} className={className} style={{ position: 'relative', height }} aria-hidden="true">
      <svg style={overlay}><Paths paths={paths} draw={draw} duration={1.4} /></svg>
    </div>
  );
}

/** Loose oval drawn around inline content, like a pen circling a word. */
export function SketchCircle({ children, seed = 5, draw = true, delay = 0.4, pad = 14 }) {
  const ref = useRef(null);
  const { width, height } = useSize(ref);
  const paths = useMemo(() => (width
    ? roughEllipse(width / 2, height / 2, width + pad * 2, height + pad, { seed, roughness: 1.4, strokeWidth: 1.6 })
    : []), [width, height, seed, pad]);
  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <svg style={overlay} aria-hidden="true"><Paths paths={paths} draw={draw} delay={delay} duration={1.1} inView={false} /></svg>
      {children}
    </span>
  );
}

/** Scribbled underline under inline content. */
export function SketchUnderline({ children, seed = 8, draw = true, delay = 0.6 }) {
  const ref = useRef(null);
  const { width, height } = useSize(ref);
  const paths = useMemo(() => (width
    ? roughPath(`M2 ${height + 2} C ${width * 0.3} ${height - 1}, ${width * 0.7} ${height + 6}, ${width - 2} ${height + 1}`, { seed, roughness: 1.2, strokeWidth: 2 })
    : []), [width, height, seed]);
  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <svg style={overlay} aria-hidden="true"><Paths paths={paths} draw={draw} delay={delay} inView={false} /></svg>
      {children}
    </span>
  );
}

/** Freehand arrow. `d` is the shaft in a 0..w, 0..h box; the head follows the last segment. */
export function SketchArrow({ width = 120, height = 60, d, head = [[-10, -6], [-10, 6]], end, seed = 11, draw = true, delay = 0, className = '' }) {
  const paths = useMemo(() => {
    const shaft = roughPath(d, { seed, roughness: 1.1, strokeWidth: 1.5 });
    const [ex, ey, angle = 0] = end;
    const rot = ([x, y]) => [ex + x * Math.cos(angle) - y * Math.sin(angle), ey + x * Math.sin(angle) + y * Math.cos(angle)];
    const [a, b] = head.map(rot);
    const tip = roughPath(`M${a[0]} ${a[1]} L${ex} ${ey} L${b[0]} ${b[1]}`, { seed: seed + 1, roughness: 0.9, strokeWidth: 1.5 });
    return [...shaft, ...tip];
  }, [d, end, head, seed]);
  return (
    <svg className={className} width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible', color: 'var(--ink)' }} aria-hidden="true">
      <Paths paths={paths} draw={draw} delay={delay} />
    </svg>
  );
}
