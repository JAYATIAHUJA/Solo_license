import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'motion/react';

/** Tween a number toward `value`; reports the direction of the last change
 *  (`'up' | 'down' | null`) so callers can flash a drop. */
export function useCountUp(value, { duration = 1.1 } = {}) {
  const target = Number(value || 0);
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(target);
  const [delta, setDelta] = useState({ dir: null, by: 0, at: 0 });
  const prev = useRef(target);

  useEffect(() => {
    const from = prev.current;
    prev.current = target;
    if (from === target) return undefined;
    setDelta({ dir: target < from ? 'down' : 'up', by: target - from, at: Date.now() });
    if (reduce) {
      setShown(target);
      return undefined;
    }
    const controls = animate(from, target, { duration, ease: [0.22, 1, 0.36, 1], onUpdate: setShown });
    return () => controls.stop();
  }, [target, duration, reduce]);

  useEffect(() => {
    if (!delta.dir) return undefined;
    const t = window.setTimeout(() => setDelta((d) => ({ ...d, dir: null })), 4000);
    return () => window.clearTimeout(t);
  }, [delta.at, delta.dir]);

  return { shown, delta };
}

/** A DOM-safe id for SVG <pattern>/<clipPath> references. */
export const safeId = (id) => String(id).replace(/[^a-zA-Z0-9_-]/g, '');
