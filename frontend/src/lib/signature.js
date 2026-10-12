/* The visitor's signature from the intro gate, kept in localStorage so the
   license card further down the page can carry it. Stored as an SVG path in
   a 600×200 box. */
const KEY = 'sl-signature';

export const SIG_BOX = { w: 600, h: 200 };

/** A pre-drawn cursive signature for "Sign for me". */
export const AUTO_SIGNATURE = 'M40 140 C 60 60, 90 40, 100 90 C 108 130, 80 160, 70 130 C 62 104, 120 70, 150 110 C 168 134, 180 120, 192 96 C 200 80, 210 120, 226 112 C 244 102, 250 70, 262 92 C 272 112, 280 130, 300 104 C 318 80, 330 72, 334 100 C 338 130, 360 126, 372 98 C 384 72, 400 90, 404 112 C 408 132, 432 120, 446 96 C 470 60, 520 70, 560 82 M120 160 C 220 150, 380 150, 540 140';

export function pointsToPath(strokes) {
  return strokes.map((pts) => {
    if (pts.length < 2) return '';
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i += 1) {
      const [x, y] = pts[i];
      const [nx, ny] = pts[i + 1];
      d += ` Q${x.toFixed(1)} ${y.toFixed(1)} ${((x + nx) / 2).toFixed(1)} ${((y + ny) / 2).toFixed(1)}`;
    }
    const last = pts[pts.length - 1];
    return `${d} L${last[0].toFixed(1)} ${last[1].toFixed(1)}`;
  }).join(' ');
}

let current = null;
const listeners = new Set();

export function saveSignature(d) {
  current = d;
  try { localStorage.setItem(KEY, d); } catch { /* storage unavailable */ }
  listeners.forEach((fn) => fn());
}

/** For useSyncExternalStore: the license cards mount behind the intro, so they
 *  must pick up the signature signed there instead of the one read at mount. */
export function subscribeSignature(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function loadSignature() {
  if (current) return current;
  try { return localStorage.getItem(KEY) || AUTO_SIGNATURE; } catch { return AUTO_SIGNATURE; }
}

/* The intro plays once per page load (every reload), but not again when the
   visitor navigates back to the landing from inside the app. */
let introPlayed = false;
export const introPending = () => !introPlayed;
export function markIntroPlayed() { introPlayed = true; }
