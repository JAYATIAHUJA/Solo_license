import { motion } from 'motion/react';

/** Render rough.js paths. With `draw`, strokes animate in like a pen. */
export function Paths({ paths, draw = false, delay = 0, duration = 0.9, inView = true }) {
  return paths.map((p, i) => {
    const common = {
      d: p.d,
      stroke: p.stroke || 'currentColor',
      strokeWidth: p.strokeWidth,
      fill: p.fill || 'none',
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      vectorEffect: 'non-scaling-stroke',
    };
    if (!draw) return <path key={i} {...common} />;
    return (
      <motion.path
        key={i}
        {...common}
        initial={{ pathLength: 0, opacity: 0 }}
        {...(inView
          ? { whileInView: { pathLength: 1, opacity: 1 }, viewport: { once: true, margin: '-10% 0px' } }
          : { animate: { pathLength: 1, opacity: 1 } })}
        transition={{ duration, delay: delay + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
      />
    );
  });
}
