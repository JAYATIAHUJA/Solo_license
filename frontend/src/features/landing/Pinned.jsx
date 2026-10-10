import { useRef } from 'react';
import { useScroll } from 'motion/react';

/** A scroll-pinned stage (Moto-card style). The section is `length` screens
 *  tall; its stage sticks to the viewport while you scroll through it, and
 *  `children(progress)` receives a 0→1 MotionValue to drive the scene. */
export function Pinned({ id, length = 3, className = '', children }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  return (
    <section id={id} ref={ref} className={`pin ${className}`} style={{ height: `${length * 100}svh` }} data-scene={id}>
      <div className="pin-stage">{children(scrollYProgress)}</div>
    </section>
  );
}
