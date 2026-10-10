import { useId, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { LEVELS, humanize, money, stampDate } from '../../../../lib/format.js';
import { HandIcon } from '../../../../components/icons/HandIcon.jsx';
import { licenseFacts } from './derive.js';
import { safeId } from './useCountUp.js';

/* The card is ONE self-contained SVG (literal colours, inline attributes, no
   CSS variables or classes) so it serialises straight to a PNG. These mirror
   styles/tokens.css. */
const INK = '#0e0e0d';
const PAPER = '#fbfaf7';
const PAPER_2 = '#ebe8e1';
const MUTED = '#76746e';
const SIGNAL = '#d8341f';
const SERIF = "'Instrument Serif', Georgia, 'Times New Roman', serif";
const MONO = "'Geist Mono', ui-monospace, 'Courier New', monospace";
const SANS = "'Inter Tight', 'Helvetica Neue', Arial, sans-serif";
const W = 640;
const H = 404;

const clip = (s, n) => (String(s || '').length > n ? `${String(s).slice(0, n - 1)}…` : String(s || ''));

function hash(s) {
  let h = 2166136261;
  for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

/** Deterministic barcode bars from the ledger sha (decorative, but stable). */
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

function Field({ x, y, label, value, size = 15, font = SANS, color = INK, weight = 500 }) {
  return (
    <g>
      <text x={x} y={y} fontFamily={MONO} fontSize="8.5" letterSpacing="1.2" fill={MUTED}>{label}</text>
      <text x={x} y={y + size + 4} fontFamily={font} fontSize={size} fontWeight={weight} fill={color}>{value}</text>
    </g>
  );
}

export function shareText({ business, card, facts, threshold }) {
  const { meta, license } = card;
  const lvl = LEVELS[license.effective_level] || LEVELS[0];
  if (license.quarantined) {
    const rule = facts.incidentFault ? humanize(facts.incidentFault) : 'fault';
    return `Our ops agent just lost its ${meta.label} license. A ${rule} was caught by read-back and it fell from L${license.demoted_from ?? '?'} to L0 in a single run — zero false successes reached a customer. A human restores it from the evidence packet, and the whole thing is a git commit${facts.sha ? ` (${facts.sha.slice(0, 7)})` : ''}. Trust is earned per task, not configured. #neatHack`;
  }
  const streak = license.effective_level >= 3 ? 'top rung, every run audited' : `${license.clean_runs}/${threshold} verified-clean runs toward L${license.effective_level + 1}`;
  return `${business ? `${business}'s` : 'Our'} ops agent holds an ${lvl.code} license for ${meta.label}: ${lvl.name}. ${streak}. Every result verified by read-back, every promotion a git commit${facts.sha ? ` (${facts.sha.slice(0, 7)})` : ''}. Trust is earned, not configured. #neatHack`;
}

/** The "Agent Driving License" for one task class. */
export function LicenseCard({ data, card, threshold = 3 }) {
  const svgRef = useRef(null);
  const uid = safeId(useId());
  const [note, setNote] = useState('');
  const { key, meta, license, ceiling } = card;
  const facts = licenseFacts(data, key);
  const q = !!license.quarantined;
  const level = license.effective_level ?? 0;
  const info = LEVELS[level] || LEVELS[0];
  const business = data.settings?.business_name || 'Your workspace';
  const number = `SL-${key.replace(/[^a-z]/gi, '').slice(0, 3).toUpperCase()}-${String(hash(`${business}:${key}`) % 100000).padStart(5, '0')}`;
  const authorised = level === 0 ? 'Suggest only' : level === 1 ? 'Draft + human approve' : level === 2 ? `Auto up to ${money(ceiling)}` : 'Full auto, audited';
  const streak = q ? '0 · quarantined' : level >= 3 ? 'Top rung' : `${Math.min(license.clean_runs, threshold)}/${threshold} → L${level + 1}`;
  const incident = facts.lastIncident ? `${stampDate(facts.lastIncident.created_at)} · ${humanize(facts.incidentFault || 'detection')}` : 'None on record';
  const code = bars(facts.sha || number, 150);

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
      ctx.fillStyle = '#f3f1ec';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `solo-license-${key}-${q ? 'quarantined' : info.code.toLowerCase()}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      setNote('PNG saved.');
    } catch {
      setNote('Could not render the PNG in this browser.');
    }
  }

  async function copy() {
    const text = shareText({ business: data.settings?.business_name, card, facts, threshold });
    try {
      await navigator.clipboard.writeText(text);
      setNote('Share text copied.');
    } catch {
      setNote(text);
    }
  }

  return (
    <motion.figure className={`mc-lic ${q ? 'is-q' : ''}`} id={key} initial={{ opacity: 0, y: 12, rotate: -0.6 }} animate={{ opacity: 1, y: 0, rotate: 0 }}>
      <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${meta.label} license: ${q ? 'quarantined' : info.code}`}>
        <defs>
          <pattern id={`${uid}-h`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="7" height="7" fill={PAPER} />
            <rect width="2.2" height="7" fill={SIGNAL} />
          </pattern>
          <pattern id={`${uid}-g`} width="14" height="14" patternUnits="userSpaceOnUse">
            <path d="M0 7 L14 7 M7 0 L7 14" stroke={PAPER_2} strokeWidth="0.8" />
          </pattern>
        </defs>

        {/* sheet */}
        <rect x="1" y="1" width={W - 2} height={H - 2} fill={PAPER} stroke={INK} strokeWidth="2" />
        <rect x="190" y="58" width={W - 210} height="250" fill={`url(#${uid}-g)`} />
        <rect x="9" y="9" width={W - 18} height={H - 18} fill="none" stroke={INK} strokeWidth="0.6" />

        {/* header band */}
        <rect x="9" y="9" width={W - 18} height="38" fill={INK} />
        <g fill={PAPER}>
          <rect x="22" y="31" width="16" height="2.4" /><rect x="25" y="25" width="10" height="2.4" /><rect x="27" y="17" width="6" height="5" />
        </g>
        <text x="46" y="33" fontFamily={MONO} fontSize="12" fontWeight="700" letterSpacing="2.4" fill={PAPER}>SOLO LICENSE</text>
        <text x={W - 22} y="33" textAnchor="end" fontFamily={MONO} fontSize="10" letterSpacing="1.6" fill={PAPER}>AGENT DRIVING LICENSE · № {number}</text>

        {/* portrait = the level */}
        <rect x="26" y="64" width="148" height="182" fill={q ? `url(#${uid}-h)` : INK} stroke={q ? SIGNAL : INK} strokeWidth="2" />
        <text x="100" y="170" textAnchor="middle" fontFamily={SERIF} fontSize="104" fill={q ? SIGNAL : PAPER}>{q ? 'L0' : info.code}</text>
        {[0, 1, 2, 3].map((r) => (
          <rect key={r} x={58 + r * 22} y={222 - r * 6} width="14" height={10 + r * 6} fill={!q && r <= level ? PAPER : 'none'} stroke={q ? SIGNAL : PAPER} strokeWidth="1.4" />
        ))}
        <text x="100" y="268" textAnchor="middle" fontFamily={MONO} fontSize="9" letterSpacing="1.4" fill={MUTED}>CLASS {meta.key.toUpperCase()}</text>

        {/* fields */}
        <Field x={200} y={78} label="1 · HOLDER" value={clip(business, 30)} size={22} font={SERIF} weight={400} />
        <Field x={200} y={126} label="2 · TASK CLASS" value={clip(meta.label, 22)} size={34} font={SERIF} weight={400} />
        <Field x={200} y={184} label="3 · AUTHORISED TO" value={q ? 'Suggest only — quarantined' : `${authorised}`} size={15} color={q ? SIGNAL : INK} />
        <Field x={200} y={226} label="4 · STREAK" value={streak} size={13} font={MONO} />
        <Field x={340} y={226} label="5 · ISSUED" value={stampDate(facts.issued)} size={13} font={MONO} />
        <Field x={480} y={226} label="6 · LAST CHANGE" value={stampDate(facts.lastChange)} size={13} font={MONO} />
        <Field x={200} y={268} label="7 · LAST INCIDENT" value={clip(incident, 32)} size={13} font={MONO} color={facts.lastIncident ? SIGNAL : INK} />
        <Field x={480} y={268} label="8 · LEDGER" value={facts.sha ? `git ${facts.sha.slice(0, 7)}` : 'no commit yet'} size={13} font={MONO} />

        {/* footer: barcode + small print */}
        <line x1="22" y1="318" x2={W - 22} y2="318" stroke={INK} strokeWidth="0.8" />
        <g fill={INK}>{code.map(([bx, bw]) => <rect key={bx} x={26 + bx} y="330" width={bw} height="34" />)}</g>
        <text x="26" y="378" fontFamily={MONO} fontSize="8" letterSpacing="1.2" fill={MUTED}>{(facts.sha || number).toUpperCase()}</text>
        <text x="200" y="338" fontFamily={SANS} fontSize="10" fill={MUTED}>Promoted after {threshold} verified-clean runs.</text>
        <text x="200" y="351" fontFamily={SANS} fontSize="10" fill={MUTED}>Any detection demotes to L0 at once.</text>
        <text x="200" y="364" fontFamily={SANS} fontSize="10" fill={MUTED}>Every change is a git commit.</text>
        <text x="200" y="378" fontFamily={MONO} fontSize="8" letterSpacing="1.2" fill={MUTED}>{facts.runs} RUNS ON RECORD · NEATHACK</text>

        {/* stamp: verified by read-back */}
        <g transform={`rotate(-8 ${W - 92} 346)`} opacity={q ? 0.35 : 0.92}>
          <rect x={W - 168} y="320" width="152" height="52" fill="none" stroke={INK} strokeWidth="2.6" />
          <rect x={W - 164} y="324" width="144" height="44" fill="none" stroke={INK} strokeWidth="0.9" />
          <text x={W - 92} y="343" textAnchor="middle" fontFamily={MONO} fontSize="12.5" fontWeight="700" letterSpacing="2" fill={INK}>VERIFIED</text>
          <text x={W - 92} y="360" textAnchor="middle" fontFamily={MONO} fontSize="9" fontWeight="600" letterSpacing="1.6" fill={INK}>BY READ-BACK</text>
        </g>

        {q && (
          <g transform={`rotate(-14 ${W / 2} ${H / 2})`}>
            <rect x={W / 2 - 220} y={H / 2 - 40} width="440" height="80" fill={PAPER} fillOpacity="0.82" stroke={SIGNAL} strokeWidth="5" />
            <rect x={W / 2 - 212} y={H / 2 - 32} width="424" height="64" fill="none" stroke={SIGNAL} strokeWidth="1.5" />
            <text x={W / 2} y={H / 2 + 6} textAnchor="middle" fontFamily={MONO} fontSize="38" fontWeight="700" letterSpacing="6" fill={SIGNAL}>QUARANTINED</text>
            <text x={W / 2} y={H / 2 + 26} textAnchor="middle" fontFamily={MONO} fontSize="10" letterSpacing="2" fill={SIGNAL}>FELL FROM L{license.demoted_from ?? '?'} · HUMAN RESTORE REQUIRED</text>
          </g>
        )}
      </svg>
      <figcaption className="mc-lic-actions">
        <button className="btn btn-ink btn-sm" onClick={download}><HandIcon name="arrow-right" size={13} /> Download PNG</button>
        <button className="btn btn-line btn-sm" onClick={copy}><HandIcon name="copy" size={13} /> Copy share text</button>
        {note && <span className="app-small muted mc-lic-note" role="status">{note}</span>}
      </figcaption>
    </motion.figure>
  );
}
