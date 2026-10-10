import { useEffect, useId } from 'react';
import { Link } from 'react-router-dom';
import { motion, useSpring, useTransform } from 'motion/react';
import { FAULTS, LEVELS, money } from '../../../../lib/format.js';
import { HandIcon } from '../../../../components/icons/HandIcon.jsx';
import { Stamp } from '../../../../components/fx/Stamp.jsx';
import { safeId } from './useCountUp.js';

const CX = 130;
const CY = 138;
const R_OUT = 108;
const R_IN = 76;
const NEEDLE = 68;
const GAP = 1.6; // degrees between rungs

const rad = (deg) => (deg * Math.PI) / 180;
const pt = (r, deg) => [CX + r * Math.cos(rad(deg)), CY - r * Math.sin(rad(deg))];
/** Level i (0..3) sweeps from 180-45i to 180-45(i+1) degrees. */
const angleFor = (level) => 180 - (level + 0.5) * 45;

function segment(i) {
  const a0 = 180 - i * 45 - GAP / 2;
  const a1 = 180 - (i + 1) * 45 + GAP / 2;
  const [x0, y0] = pt(R_OUT, a0);
  const [x1, y1] = pt(R_OUT, a1);
  const [x2, y2] = pt(R_IN, a1);
  const [x3, y3] = pt(R_IN, a0);
  return `M${x0} ${y0} A${R_OUT} ${R_OUT} 0 0 1 ${x1} ${y1} L${x2} ${y2} A${R_IN} ${R_IN} 0 0 0 ${x3} ${y3} Z`;
}

/** A semicircular autonomy gauge for one task class. Four rungs, a needle on a
 *  spring (so a demotion visibly swings it back to L0), clean-run ticks toward
 *  the next rung, and a red hatched quarantine state with a stamp. */
export function AutonomyDial({ card, threshold = 3, compact = false }) {
  const { key, meta, license, ceiling, fault } = card;
  const q = !!license.quarantined;
  const level = license.effective_level ?? 0;
  const info = LEVELS[level] || LEVELS[0];
  const uid = safeId(useId());
  const armed = FAULTS.find((f) => f.id === fault && f.id !== 'none');

  const spring = useSpring(level, { stiffness: 90, damping: 11, mass: 0.9 });
  useEffect(() => { spring.set(level); }, [level, spring]);
  const x2 = useTransform(spring, (v) => pt(NEEDLE, angleFor(v))[0]);
  const y2 = useTransform(spring, (v) => pt(NEEDLE, angleFor(v))[1]);

  const next = level + 1;
  const clean = Math.min(license.clean_runs ?? 0, threshold);

  return (
    <article className={`mc-dial ${q ? 'is-q' : ''} ${compact ? 'is-compact' : ''}`} aria-label={`${meta.label} autonomy ${q ? 'quarantined' : info.code}`}>
      <header className="mc-dial-head">
        <span className="mc-dial-class">{meta.label}</span>
        <span className={`ov-pill ${q ? 'is-alert' : ''}`}><i /> {q ? 'Quarantined' : 'Live'}</span>
      </header>

      <div className="mc-dial-gauge">
        <svg viewBox="0 0 260 150" role="img" aria-hidden="true">
          <defs>
            <pattern id={`${uid}-hq`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="var(--sheet)" />
              <rect width="2" height="6" fill="var(--signal)" />
            </pattern>
            <pattern id={`${uid}-dots`} width="5" height="5" patternUnits="userSpaceOnUse">
              <rect width="5" height="5" fill="var(--sheet)" />
              <circle cx="2.5" cy="2.5" r="1" fill="var(--ink)" />
            </pattern>
          </defs>

          {/* minor ticks */}
          {Array.from({ length: 25 }, (_, i) => {
            const a = 180 - i * 7.5;
            const [ax, ay] = pt(R_OUT + 4, a);
            const [bx, by] = pt(R_OUT + (i % 6 === 0 ? 11 : 7), a);
            return <line key={i} x1={ax} y1={ay} x2={bx} y2={by} stroke="var(--ink)" strokeWidth={i % 6 === 0 ? 1.4 : 0.8} opacity={q ? 0.35 : 0.6} />;
          })}

          {LEVELS.map((l) => {
            let fill = 'var(--sheet)';
            if (q) fill = `url(#${uid}-hq)`;
            else if (l.id <= level) fill = 'var(--ink)';
            else if (l.id === next) fill = `url(#${uid}-dots)`;
            return (
              <motion.path
                key={l.id}
                d={segment(l.id)}
                fill={fill}
                stroke={q ? 'var(--signal)' : 'var(--ink)'}
                strokeWidth={l.id === level && !q ? 2 : 1.2}
                initial={false}
                animate={{ opacity: !q && l.id > next ? 0.55 : 1 }}
              />
            );
          })}

          {LEVELS.map((l) => {
            const [lx, ly] = pt(R_OUT + 22, angleFor(l.id));
            return (
              <text key={l.id} x={lx} y={ly + 4} textAnchor="middle" className="mc-dial-label" fill={q && l.id === license.demoted_from ? 'var(--signal)' : l.id === level ? 'var(--ink)' : 'var(--muted)'} fontWeight={l.id === level ? 700 : 500}>
                {l.code}
              </text>
            );
          })}

          {q && license.demoted_from != null && (() => {
            const [fx, fy] = pt((R_OUT + R_IN) / 2, angleFor(license.demoted_from));
            return (
              <g>
                <rect x={fx - 8} y={fy - 8} width="16" height="16" fill="var(--signal)" />
                <path d={`M${fx - 4} ${fy - 4} L${fx + 4} ${fy + 4} M${fx + 4} ${fy - 4} L${fx - 4} ${fy + 4}`} stroke="var(--paper)" strokeWidth="2" />
              </g>
            );
          })()}

          <motion.line x1={CX} y1={CY} x2={x2} y2={y2} stroke={q ? 'var(--signal)' : 'var(--ink)'} strokeWidth="3" strokeLinecap="square" />
          <rect x={CX - 7} y={CY - 7} width="14" height="14" fill={q ? 'var(--signal)' : 'var(--ink)'} />
          <rect x={CX - 2.5} y={CY - 2.5} width="5" height="5" fill="var(--paper)" />
        </svg>
        {q && <div className="mc-dial-stamp"><Stamp text="Quarantined" sub={`fell from L${license.demoted_from ?? '?'}`} tone="signal" size="sm" angle={-7} /></div>}
      </div>

      <div className="mc-dial-read">
        <b className="serif mc-dial-code">{q ? 'L0' : info.code}</b>
        <div>
          <p className="mc-dial-name">{q ? 'Suggest only — human restore needed' : info.name}</p>
          {q ? (
            <p className="mc-dial-sub is-alert">A detection fired. Review the evidence, then restore.</p>
          ) : level >= 3 ? (
            <p className="mc-dial-sub">Top rung · every run audited</p>
          ) : (
            <p className="mc-dial-sub mc-ticks-row">
              <span className="mc-ticks" aria-label={`${clean} of ${threshold} clean runs`}>
                {Array.from({ length: threshold }, (_, i) => <i key={i} className={i < clean ? 'on' : ''} />)}
              </span>
              clean {clean}/{threshold} → L{next}
            </p>
          )}
        </div>
      </div>

      {!compact && (
        <footer className="mc-dial-foot">
          <span className="mono">auto ≤ {money(ceiling)}</span>
          {armed ? (
            <span className="mc-armed mono"><HandIcon name="bolt" size={12} /> {armed.name} armed</span>
          ) : (
            <span className="mono muted">{card.stats.total_runs ?? 0} runs · {card.stats.demotions ?? 0} caught</span>
          )}
          <Link to={`/app/license#${key}`} className="app-link">License →</Link>
        </footer>
      )}
    </article>
  );
}
