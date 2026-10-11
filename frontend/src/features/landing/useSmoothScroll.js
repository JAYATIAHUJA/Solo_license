import { useEffect } from 'react';
import Lenis from 'lenis';

/** Lenis smooth scrolling for the marketing page only (the app scrolls
 *  natively). Anchor links glide instead of jumping. */
export function useSmoothScroll() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const lenis = new Lenis({ autoRaf: true, anchors: { offset: 0 }, lerp: 0.11 });
    window.__lenis = lenis;
    return () => { lenis.destroy(); delete window.__lenis; };
  }, []);
}
