import { useMemo } from 'react';
import { Paths } from '../sketch/Paths.jsx';
import { roughPath } from '../sketch/rough.js';

/* Hand-drawn icon set. Each glyph is authored as straight-edged strokes on a
   48-unit grid, then passed through rough.js so it reads as pen on paper.
   Seeds are fixed per icon, so every icon is drawn the same way each time. */
const GLYPHS = {
  'arrow-right': ['M8 24 L40 24', 'M30 14 L40 24 L30 34'],
  'arrow-up-right': ['M12 36 L36 12', 'M18 12 L36 12 L36 30'],
  'arrow-left': ['M40 24 L8 24', 'M18 14 L8 24 L18 34'],
  check: ['M9 25 L19 35 L39 13'],
  cross: ['M12 12 L36 36', 'M36 12 L12 36'],
  plus: ['M24 9 L24 39', 'M9 24 L39 24'],
  minus: ['M9 24 L39 24'],
  shield: ['M24 6 L39 12 L39 25 C39 34 32 40 24 43 C16 40 9 34 9 25 L9 12 Z', 'M17 24 L22 29 L31 19'],
  bolt: ['M27 5 L11 27 L23 27 L20 43 L37 20 L25 20 Z'],
  ledger: ['M10 7 L36 7 L36 41 L10 41 Z', 'M16 7 L16 41', 'M21 16 L31 16', 'M21 23 L31 23', 'M21 30 L28 30'],
  eye: ['M4 24 C12 12 36 12 44 24 C36 36 12 36 4 24 Z', 'M24 18 L30 24 L24 30 L18 24 Z'],
  dial: ['M8 32 A16 16 0 0 1 40 32', 'M24 32 L33 19', 'M6 38 L42 38'],
  user: ['M16 16 L24 8 L32 16 L24 24 Z', 'M9 41 L13 30 L35 30 L39 41'],
  settings: ['M18 7 L30 7 L41 18 L41 30 L30 41 L18 41 L7 30 L7 18 Z', 'M24 18 L30 24 L24 30 L18 24 Z'],
  trash: ['M8 12 L40 12', 'M19 12 L19 7 L29 7 L29 12', 'M12 12 L15 41 L33 41 L36 12', 'M21 19 L21 34', 'M27 19 L27 34'],
  play: ['M14 8 L38 24 L14 40 Z'],
  inbox: ['M6 26 L12 8 L36 8 L42 26 L42 40 L6 40 Z', 'M6 26 L17 26 L20 31 L28 31 L31 26 L42 26'],
  receipt: ['M11 5 L37 5 L37 43 L32 39 L27 43 L22 39 L17 43 L11 39 Z', 'M17 15 L31 15', 'M17 22 L31 22', 'M17 29 L25 29'],
  commit: ['M4 24 L16 24', 'M32 24 L44 24', 'M16 24 L24 16 L32 24 L24 32 Z'],
  refresh: ['M38 18 C34 9 20 6 12 14 C6 20 7 30 12 35', 'M30 18 L38 18 L38 10', 'M12 35 C18 41 30 42 36 34'],
  key: ['M6 20 L14 12 L22 20 L14 28 Z', 'M20 22 L42 22 L42 30', 'M34 22 L34 29'],
  layers: ['M24 6 L43 16 L24 26 L5 16 Z', 'M5 24 L24 34 L43 24', 'M5 32 L24 42 L43 32'],
  flag: ['M11 43 L11 6', 'M11 8 L38 8 L31 17 L38 26 L11 26'],
  search: ['M8 8 L28 8 L28 28 L8 28 Z', 'M28 28 L41 41'],
  spark: ['M24 4 L24 44', 'M4 24 L44 24', 'M10 10 L38 38', 'M38 10 L10 38'],
  sun: ['M17 17 L31 17 L31 31 L17 31 Z', 'M24 4 L24 10', 'M24 38 L24 44', 'M4 24 L10 24', 'M38 24 L44 24'],
  menu: ['M6 13 L42 13', 'M6 24 L42 24', 'M6 35 L42 35'],
  home: ['M6 22 L24 7 L42 22', 'M11 18 L11 41 L37 41 L37 18', 'M20 41 L20 29 L28 29 L28 41'],
  message: ['M6 8 L42 8 L42 32 L22 32 L12 41 L12 32 L6 32 Z', 'M14 17 L34 17', 'M14 24 L28 24'],
  pause: ['M15 9 L15 39', 'M33 9 L33 39'],
  warn: ['M24 5 L44 41 L4 41 Z', 'M24 18 L24 29', 'M24 34 L24 36'],
  logout: ['M20 7 L7 7 L7 41 L20 41', 'M18 24 L42 24', 'M33 15 L42 24 L33 33'],
  copy: ['M15 15 L41 15 L41 41 L15 41 Z', 'M7 33 L7 7 L33 7'],
  external: ['M28 7 L41 7 L41 20', 'M41 7 L22 26', 'M34 28 L34 41 L7 41 L7 14 L20 14'],
};

const SEEDS = Object.fromEntries(Object.keys(GLYPHS).map((name, i) => [name, 17 + i * 7]));

export function HandIcon({ name, size = 18, strokeWidth = 1.6, roughness = 0.75, className = '', title }) {
  const paths = useMemo(() => {
    const glyph = GLYPHS[name] || GLYPHS.spark;
    return glyph.flatMap((d, i) => roughPath(d, { seed: SEEDS[name] + i, roughness, strokeWidth, bowing: 0.8 }));
  }, [name, roughness, strokeWidth]);
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      style={{ overflow: 'visible', flex: 'none' }}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      <Paths paths={paths} />
    </svg>
  );
}

export const ICON_NAMES = Object.keys(GLYPHS);
