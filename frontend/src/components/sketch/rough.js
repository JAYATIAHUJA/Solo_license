import rough from 'roughjs';

/* One shared rough.js generator. Shapes are generated with a fixed seed so a
   hand-drawn line looks the same on every render instead of re-jittering. */
const generator = rough.generator();

export const INK = '#0e0e0d';

const BASE = {
  stroke: 'currentColor',
  strokeWidth: 1.3,
  roughness: 0.9,
  bowing: 0.6,
  disableMultiStroke: false,
  preserveVertices: true,
};

export function toPaths(drawable) {
  return generator.toPaths(drawable).map((p) => ({ d: p.d, stroke: p.stroke, strokeWidth: p.strokeWidth, fill: p.fill }));
}

export function roughRect(x, y, w, h, opts = {}) {
  return toPaths(generator.rectangle(x, y, w, h, { ...BASE, ...opts }));
}

export function roughLine(x1, y1, x2, y2, opts = {}) {
  return toPaths(generator.line(x1, y1, x2, y2, { ...BASE, ...opts }));
}

export function roughPath(d, opts = {}) {
  return toPaths(generator.path(d, { ...BASE, ...opts }));
}

export function roughEllipse(cx, cy, w, h, opts = {}) {
  return toPaths(generator.ellipse(cx, cy, w, h, { ...BASE, ...opts }));
}

export function roughCircle(cx, cy, d, opts = {}) {
  return toPaths(generator.circle(cx, cy, d, { ...BASE, ...opts }));
}
