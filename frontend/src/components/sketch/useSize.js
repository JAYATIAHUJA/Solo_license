import { useLayoutEffect, useState } from 'react';

/** Track an element's rendered size so sketches can be drawn to fit it. */
export function useSize(ref) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const update = () => {
      const { width, height } = node.getBoundingClientRect();
      setSize((prev) => (Math.round(prev.width) === Math.round(width) && Math.round(prev.height) === Math.round(height)
        ? prev
        : { width, height }));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}
