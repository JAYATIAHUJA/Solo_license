import { useRef } from 'react';
import { motion, useMotionValue, useSpring } from 'motion/react';

/** Pulls its child toward the cursor while hovered (reactbits' Magnet idea). */
export function Magnetic({ children, strength = 0.28, className = '' }) {
  const ref = useRef(null);
  const x = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 });
  const y = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 });

  function move(e) {
    const r = ref.current.getBoundingClientRect();
    x.set((e.clientX - (r.left + r.width / 2)) * strength);
    y.set((e.clientY - (r.top + r.height / 2)) * strength);
  }
  function leave() { x.set(0); y.set(0); }

  return (
    <motion.span ref={ref} className={className} style={{ x, y, display: 'inline-flex' }} onMouseMove={move} onMouseLeave={leave}>
      {children}
    </motion.span>
  );
}
