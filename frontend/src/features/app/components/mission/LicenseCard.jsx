import { useRef, useState } from 'react';
import { stampDate } from '../../../../lib/format.js';
import { levelCopy } from '../../../../lib/copy.js';
import { licenseFacts, limitOf, progressOf } from './derive.js';

/* The card is ONE self-contained SVG (literal colours, inline attributes, no
   CSS variables or classes) so it serialises straight to a PNG. Colours mirror
   styles/tokens.css and styles/plain.css. */
const INK = '#0e0e0d';
const INK_2 = '#3a3a37';
const WHITE = '#ffffff';
const PAPER = '#fbfaf7';
const LINE = '#dcd9d2';
const MUTED = '#76746e';
const RED = '#d8341f';
const RED_BG = '#fbe7e3';
const SANS = "'Inter Tight', 'Helvetica Neue', Arial, sans-serif";
const MONO = "'Geist Mono', ui-monospace, 'Courier New', monospace";
const W = 640;
const H = 400;
const X = 28;

const clip = (s, n) => (String(s || '').length > n ? `${String(s).slice(0, n - 1)}…` : String(s || ''));

function hash(s) {
  let h = 2166136261;
  for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

/** Deterministic barcode bars from the history record id (decorative, but stable). */
function bars(seed, width) {
  const out = [];
  let x = 0;
  let h = hash(seed);
  while (x < width) {
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    const w = 1 + (h % 3);
    const gap = 1 + ((h >>> 4) % 3);
    if (x + w > width) break;
    out.push([x, w]);
    x += w + gap;
  }
  return out;
}

function Label({ x, y, children }) {
  return <text x={x} y={y} fontFamily={MONO} fontSize="9.5" letterSpacing="1.2" fill={MUTED}>{children}</text>;
}

function Value({ x, y, size = 13, color = INK, weight = 500, children }) {
  return <text x={x} y={y} fontFamily={SANS} fontSize={size} fontWeight={weight} fill={color}>{children}</text>;
}

export function shareText({ business, card }) {
  const { name, license, ceiling } = card;
  const who = business ? `${business}'s` : 'Our';
  if (license.quarantined) {
    return `${who} AI agent was paused on ${name.toLowerCase()} the moment it hit a problem. Nothing wrong reached a customer, and a person decides when it can carry on. Freedom is earned, not assumed. #neatHack`;
  }
  const now = levelCopy(license.effective_level, limitOf(ceiling)).short;
  const p = progressOf(card);
  const next = license.effective_level >= 3 ? 'It has reached the highest level.'
    : `It has ${license.successes} double-checked jobs on record and needs ${p.needed ?? 'more'} more before it gets more freedom - earned from evidence, priced by what a mistake costs.`;
  return `${who} AI agent holds a license for ${name.toLowerCase()}: “${now}”. ${next} Every result is double-checked and every change is on record. #neatHack`;
}

/** The agent's license for one job type, plus download and share buttons below it. */
export function LicenseCard({ data, card }) {
  const svgRef = useRef(null);
  const [note, setNote] = useState('');
  const { key, name, license, ceiling } = card;
  const facts = licenseFacts(data, key);
  const paused = !!license.quarantined;
  const level = license.effective_level ?? 0;
  const copy = levelCopy(level, limitOf(ceiling));
  const business = data.settings?.business_name || 'Your business';
  const number = `SL-${key.replace(/[^a-z]/gi, '').slice(0, 3).toUpperCase()}-${String(hash(`${business}:${key}`) % 100000).padStart(5, '0')}`;
  const allowed = paused ? 'Paused - suggests only until reviewed' : copy.short;
  const progress = paused
    ? 'On hold'
    : level >= 3 ? 'Highest level' : `${license.successes} verified · ${progressOf(card).needed ?? '-'} more to go`;
  const incident = facts.lastIncident
    ? `${stampDate(facts.lastIncident.created_at)} · ${facts.incidentProblem?.title || 'Problem caught'}`
    : 'None on record';
  const code = bars(facts.sha || number, 120);

  async function download() {
    const svg = svgRef.current;
    if (!svg) return;
    try {
      const xml = new XMLSerializer().serializeToString(svg);
      const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
      const img = new Image();
      await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = url; });
      const scale = 2;
      const canvas = document.createElement('canvas');
      canvas.width = W * scale;
      canvas.height = H * scale;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = WHITE;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `solo-license-${key}-${paused ? 'paused' : `level-${level}`}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      setNote('Image saved.');
    } catch {
      setNote('This browser could not create the image.');
    }
  }

  async function copyText() {
    const text = shareText({ business: data.settings?.business_name, card });
    try {
      await navigator.clipboard.writeText(text);
      setNote('Post text copied.');
    } catch {
      setNote(text);
    }
  }

  return (
    <figure className="app-lic" id={key}>
      <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${name} license: ${paused ? 'paused' : copy.short}`}>
        {/* card */}
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} rx="14" fill={WHITE} stroke={LINE} />

        {/* header */}
        <path d={`M0.5 52 L0.5 14.5 Q0.5 0.5 14.5 0.5 L${W - 14.5} 0.5 Q${W - 0.5} 0.5 ${W - 0.5} 14.5 L${W - 0.5} 52 Z`} fill={INK} />
        <text x={X} y="32" fontFamily={SANS} fontSize="15" fontWeight="700" fill={WHITE}>Solo License</text>
        <text x={X + 108} y="32" fontFamily={SANS} fontSize="13" fill="#bdbab3">Agent license</text>
        <text x={W - X} y="32" textAnchor="end" fontFamily={MONO} fontSize="11" letterSpacing="1" fill="#bdbab3">No. {number}</text>

        {/* job type + paused badge */}
        <Label x={X} y={86}>JOB TYPE</Label>
        <Value x={X} y={120} size={30} weight={700}>{clip(name, 22)}</Value>
        {paused && (
          <g>
            <rect x={W - X - 96} y="72" width="96" height="28" rx="14" fill={RED_BG} stroke={RED} />
            <circle cx={W - X - 78} cy="86" r="4" fill={RED} />
            <text x={W - X - 66} y="90.5" fontFamily={SANS} fontSize="12.5" fontWeight="700" letterSpacing="0.8" fill={RED}>PAUSED</text>
          </g>
        )}

        <Label x={X} y={150}>BUSINESS</Label>
        <Value x={X} y={170} size={15} color={INK_2}>{clip(business, 48)}</Value>

        {/* what it may do, with the level as a small chip */}
        <Label x={X} y={202}>ALLOWED TO</Label>
        <rect x={X + 84} y="191" width="54" height="15" rx="7.5" fill={PAPER} stroke={LINE} />
        <text x={X + 111} y="202" textAnchor="middle" fontFamily={MONO} fontSize="9" fill={MUTED}>LEVEL {level}</text>
        <Value x={X} y={230} size={20} weight={600} color={paused ? RED : INK}>{clip(allowed, 44)}</Value>

        <line x1={X} y1="250" x2={W - X} y2="250" stroke={LINE} />

        {/* facts */}
        <Label x={X} y={274}>PROGRESS</Label>
        <Value x={X} y={293}>{progress}</Value>
        <Label x={232} y={274}>ISSUED</Label>
        <Value x={232} y={293}>{stampDate(facts.issued)}</Value>
        <Label x={432} y={274}>LAST CHANGE</Label>
        <Value x={432} y={293}>{stampDate(facts.lastChange)}</Value>

        <Label x={X} y={322}>LAST PROBLEM</Label>
        <Value x={X} y={341} color={facts.lastIncident ? RED : INK}>{clip(incident, 58)}</Value>
        <Label x={432} y={322}>RECORD</Label>
        <Value x={432} y={341}>{facts.sha ? `Saved · ${facts.sha.slice(0, 7)}` : 'Not saved yet'}</Value>

        {/* footer */}
        <line x1={X} y1="358" x2={W - X} y2="358" stroke={LINE} />
        <text x={X} y="377" fontFamily={SANS} fontSize="10.5" fill={MUTED}>Freedom earned from double-checked results. Paused the moment a problem is caught.</text>
        <text x={X} y="391" fontFamily={SANS} fontSize="10.5" fill={MUTED}>Every change is saved in history.</text>
        <g fill={INK}>{code.map(([bx, bw]) => <rect key={bx} x={W - X - 120 + bx} y="366" width={bw} height="24" />)}</g>
      </svg>
      <figcaption className="app-lic-actions">
        <button type="button" className="btn btn-line btn-sm" onClick={download}>Download image</button>
        <button type="button" className="btn btn-line btn-sm" onClick={copyText}>Copy post text</button>
        {note && <span className="pl-small pl-muted app-lic-note" role="status">{note}</span>}
      </figcaption>
    </figure>
  );
}
