import { useRef } from 'react';
import { useInView } from 'motion/react';
import { Dithering, PaperTexture } from '@paper-design/shaders-react';

/* Black-and-white shader surfaces from Paper. Dithering gives a moving,
   ink-only field; PaperTexture lays fibre and crumple over the page so it
   reads as printed matter rather than a screen.

   Performance: every field renders at 1x pixel ratio with a pixel budget
   (dithering is pixel art, so this costs nothing visually) and stops
   animating while it is off screen. */

const fill = { position: 'absolute', inset: 0, width: '100%', height: '100%' };
const BUDGET = 1280 * 800;

export function DitherField({ shape = 'warp', speed = 0.35, size = 2.2, scale = 1, className = '', style }) {
  const ref = useRef(null);
  const visible = useInView(ref, { margin: '10% 0px' });
  return (
    <div ref={ref} className={className} style={{ position: 'relative', overflow: 'hidden', ...style }} aria-hidden="true">
      <Dithering
        style={fill}
        colorBack="#f3f1ec"
        colorFront="#0e0e0d"
        shape={shape}
        type="4x4"
        size={size}
        speed={visible ? speed : 0}
        scale={scale}
        minPixelRatio={1}
        maxPixelCount={BUDGET}
      />
    </div>
  );
}

/** Static paper fibre over the whole page. Rendered once (speed 0). */
export function PaperGrain({ opacity = 0.55 }) {
  return (
    <div style={{ ...fill, position: 'fixed', pointerEvents: 'none', zIndex: 60, mixBlendMode: 'multiply', opacity }} aria-hidden="true">
      <PaperTexture
        style={fill}
        colorBack="#ffffff"
        colorPaper="#ffffff"
        colorShadow="#8f8a7f"
        fiber={0.35}
        fiberSize={0.2}
        crumples={0.25}
        folds={0.4}
        drops={0.1}
        roughness={0.35}
        seed={4}
        scale={0.8}
        speed={0}
        minPixelRatio={1}
        maxPixelCount={BUDGET}
      />
    </div>
  );
}
