import { useMemo } from 'react';
import { Paths } from '../sketch/Paths.jsx';
import { roughPath } from '../sketch/rough.js';

/** Mark: four stacked rungs, the top one inked — a license being earned. */
export function Logo({ size = 22 }) {
  const paths = useMemo(() => [
    ...roughPath('M4 40 L44 40', { seed: 3, roughness: 0.6, strokeWidth: 2 }),
    ...roughPath('M10 30 L38 30', { seed: 4, roughness: 0.6, strokeWidth: 2 }),
    ...roughPath('M16 20 L32 20', { seed: 5, roughness: 0.6, strokeWidth: 2 }),
    ...roughPath('M20 6 L28 6 L28 12 L20 12 Z', { seed: 6, roughness: 0.5, strokeWidth: 2, fill: 'currentColor', fillStyle: 'solid' }),
  ], []);
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ overflow: 'visible' }}>
      <Paths paths={paths} />
    </svg>
  );
}
