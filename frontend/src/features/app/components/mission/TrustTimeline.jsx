import { useId, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { LEVELS, classMeta, humanize, money, when } from '../../../../lib/format.js';
import { useSize } from '../../../../components/sketch/useSize.js';
import { safeId } from './useCountUp.js';
import { trustSeries } from './derive.js';

const DASH = ['', '7 4', '1.5 4', '12 4 2 4'];
const PAD = { l: 34, r: 16, t: 16, b: 28 };
const H = 230;

function Mark({ status, x, y }) {
  if (status === 'demoted') {
    return (
      <g stroke="var(--signal)" strokeWidth="2.4">
        <line x1={x - 5} y1={y - 5} x2={x + 5} y2={y + 5} />
        <line x1={x + 5} y1={y - 5} x2={x - 5} y2={y + 5} />
      </g>
    );
  }
  if (status === 'clean') return <rect x={x - 4} y={y - 4} width="8" height="8" fill="var(--ink)" />;
  return <rect x={x - 3.5} y={y - 3.5} width="7" height="7" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.2" />;
}

/** License level over time for every class, as step lines on one ordinal axis,
 *  with each run dotted on its line (clean = solid, demoted = red ✕) and the
 *  quarantine stretch hatched. Hover a mark for the record; click a run to open it. */
export function TrustTimeline({ data }) {
  const ref = useRef(null);
  const { width } = useSize(ref);
  const navigate = useNavigate();
  const uid = safeId(useId());
  const [tip, setTip] = useState(null);
  const narrow = width > 0 && width < 560;
  const series = useMemo(() => trustSeries(data, narrow ? 18 : 48), [data, narrow]);
  const { keys, steps, initial, now } = series;

  const W = Math.max(280, width || 0);
  const plotW = W - PAD.l - PAD.r;
  const rowH = (H - PAD.t - PAD.b) / 3;
  const y = (lvl) => PAD.t + (3 - lvl) * rowH;
  const x = (i) => PAD.l + ((i + 1) * plotW) / (steps.length + 1);
  const dy = (k) => (k - (keys.length - 1) / 2) * 5;

  const lines = useMemo(() => keys.map((key, k) => {
    const segs = [];
    const verts = [];
    let cur = initial[key] || { level: 0, q: false };
    let x0 = PAD.l;
    steps.forEach((s, i) => {
      if (s.type !== 'event' || s.key !== key) return;
      const nx = x(i);
      segs.push({ x0, x1: nx, level: cur.level, q: cur.q });
      verts.push({ x: nx, from: cur.level, to: s.snap[key].level, kind: s.item.kind, ev: s.item });
      cur = s.snap[key];
      x0 = nx;
    });
    const end = now[key] || cur;
    if (end.level !== cur.level || end.q !== cur.q) {
      const nx = PAD.l + plotW - 4;
      segs.push({ x0, x1: nx, level: cur.level, q: cur.q });
      verts.push({ x: nx, from: cur.level, to: end.level, kind: 'sync' });
      cur = end;
      x0 = nx;
    }
    segs.push({ x0, x1: PAD.l + plotW, level: cur.level, q: cur.q });
    return { key, k, segs, verts };
  }), [keys, steps, initial, now, plotW]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasData = steps.length > 0;
  const show = (e, lines2) => {
    const box = ref.current?.getBoundingClientRect();
    const target = e.currentTarget.getBoundingClientRect();
    if (!box) return;
    setTip({ left: target.left - box.left + target.width / 2, top: target.top - box.top, lines: lines2 });
  };

  return (
    <div className="mc-tl">
      <ul className="mc-tl-legend" aria-label="Legend">
        {keys.map((key, k) => (
          <li key={key}>
            <svg width="34" height="10" aria-hidden="true"><line x1="0" y1="5" x2="34" y2="5" stroke="var(--ink)" strokeWidth="2.2" strokeDasharray={DASH[k % DASH.length]} /></svg>
            {classMeta(data, key).label}
          </li>
        ))}
        <li><svg width="10" height="10" aria-hidden="true"><rect x="1" y="1" width="8" height="8" fill="var(--ink)" /></svg>clean run</li>
        <li><svg width="12" height="12" aria-hidden="true"><g stroke="var(--signal)" strokeWidth="2"><line x1="1" y1="1" x2="11" y2="11" /><line x1="11" y1="1" x2="1" y2="11" /></g></svg>caught &amp; demoted</li>
        <li><svg width="10" height="10" aria-hidden="true"><rect x="1" y="1" width="8" height="8" fill="none" stroke="var(--ink)" /></svg>held / suggested</li>
        <li><i className="mc-swatch-risk" aria-hidden="true" />quarantined</li>
      </ul>

      <div className="mc-tl-plot" ref={ref} onMouseLeave={() => setTip(null)}>
        {!hasData ? (
          <p className="mc-tl-empty app-small muted">No runs yet. Each run lands on this chart as it happens — promotions step up, a caught fault drops the line to L0.</p>
        ) : (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="License level over time per task class">
            <defs>
              <pattern id={`${uid}-q`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="1.6" height="6" fill="var(--signal)" />
              </pattern>
            </defs>

            {LEVELS.map((l) => (
              <g key={l.id}>
                <line x1={PAD.l} x2={PAD.l + plotW} y1={y(l.id)} y2={y(l.id)} stroke="var(--hair)" strokeDasharray={l.id === 0 ? '' : '2 4'} />
                <text x={0} y={y(l.id) + 4} className="mc-tl-axis">{l.code}</text>
              </g>
            ))}

            {lines.map(({ key, k, segs }) => segs.filter((s) => s.q).map((s, i) => (
              <rect key={`${key}-q${i}`} x={s.x0} y={y(s.level) + dy(k) - 7} width={Math.max(0, s.x1 - s.x0)} height="14" fill={`url(#${uid}-q)`} opacity="0.55" />
            )))}

            {lines.map(({ key, k, segs, verts }) => (
              <g key={key} fill="none" strokeDasharray={DASH[k % DASH.length]} strokeWidth="2.2">
                {segs.map((s, i) => (
                  <motion.line
                    key={`h${i}`}
                    x1={s.x0} x2={s.x1} y1={y(s.level) + dy(k)} y2={y(s.level) + dy(k)}
                    stroke={s.q ? 'var(--signal)' : 'var(--ink)'}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: i * 0.03 }}
                  />
                ))}
                {verts.map((v, i) => (
                  <line key={`v${i}`} x1={v.x} x2={v.x} y1={y(v.from) + dy(k)} y2={y(v.to) + dy(k)} stroke={v.kind === 'demote' ? 'var(--signal)' : 'var(--ink)'} />
                ))}
              </g>
            ))}

            {lines.map(({ key, k, verts }) => verts.filter((v) => v.ev).map((v) => (
              <g
                key={`${key}-e${v.ev.id}`}
                className="mc-tl-hit"
                tabIndex={0}
                onMouseEnter={(e) => show(e, [
                  `${classMeta(data, key).label} · ${v.kind} L${v.from} → L${v.to}`,
                  v.ev.reason,
                  `${v.ev.git_sha ? `commit ${v.ev.git_sha.slice(0, 7)} · ` : ''}${when(v.ev.created_at)}`,
                ])}
                onFocus={(e) => show(e, [`${classMeta(data, key).label} · ${v.kind} L${v.from} → L${v.to}`, v.ev.reason])}
                onBlur={() => setTip(null)}
              >
                <rect x={v.x - 8} y={y(v.to) + dy(k) - 8} width="16" height="16" fill="transparent" />
                <rect x={v.x - 4} y={y(v.to) + dy(k) - 4} width="8" height="8" transform={`rotate(45 ${v.x} ${y(v.to) + dy(k)})`} fill={v.kind === 'demote' ? 'var(--signal)' : 'var(--paper)'} stroke={v.kind === 'demote' ? 'var(--signal)' : 'var(--ink)'} strokeWidth="1.4" strokeDasharray="" />
              </g>
            )))}

            {steps.map((s, i) => {
              if (s.type !== 'run') return null;
              const k = Math.max(0, keys.indexOf(s.key));
              const r = s.item;
              const cy = y(r.level_at_run ?? 0) + dy(k);
              const tipLines = [
                `Run #${r.id} · ${classMeta(data, s.key).label} · L${r.level_at_run}`,
                `${r.order_id} · ${money(r.requested_amount)} · ${humanize(r.status)}`,
                `${r.fault_mode && r.fault_mode !== 'none' ? `fault: ${humanize(r.fault_mode)} · ` : ''}${when(r.created_at)}`,
              ];
              return (
                <g
                  key={`r${r.id}`}
                  className="mc-tl-hit"
                  tabIndex={0}
                  role="link"
                  aria-label={tipLines.join(', ')}
                  onMouseEnter={(e) => show(e, tipLines)}
                  onFocus={(e) => show(e, tipLines)}
                  onBlur={() => setTip(null)}
                  onClick={() => navigate(`/app/runs/${r.id}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/app/runs/${r.id}`); }}
                >
                  <rect x={x(i) - 9} y={cy - 9} width="18" height="18" fill="transparent" />
                  <Mark status={r.status} x={x(i)} y={cy} />
                </g>
              );
            })}

            <text x={PAD.l} y={H - 8} className="mc-tl-axis">{series.truncated ? `… ${when(steps[0]?.item.created_at)}` : steps[0] ? when(steps[0].item.created_at) : ''}</text>
            <text x={PAD.l + plotW} y={H - 8} textAnchor="end" className="mc-tl-axis">now</text>
          </svg>
        )}
        {tip && (
          <div className="mc-tip" style={{ left: Math.min(Math.max(tip.left, 110), W - 110), top: tip.top }} role="tooltip">
            {tip.lines.filter(Boolean).map((l, i) => <span key={i} className={i === 0 ? 'mc-tip-h' : ''}>{l}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}
