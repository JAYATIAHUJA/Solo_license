import { when } from '../../../../lib/format.js';
import { levelCopy } from '../../../../lib/copy.js';
import { levelHistory, limitOf } from './derive.js';

/** One plain step line per job type: what the agent was allowed to do after
 *  each recorded change, oldest on the left. Red where it was paused. Labels
 *  are HTML so they stay readable at any width. */
function JobChart({ data, card }) {
  const points = levelHistory(data, card.key);
  const n = points.length;
  const y = (lvl) => (3 - lvl + 0.5) * 25;
  const x = (i) => (i / n) * 100;
  const segs = points.map((p, i) => ({ x0: x(i), x1: x(i + 1), y: y(p.level), paused: p.paused }));
  const labels = [3, 2, 1, 0].map((l) => levelCopy(l, limitOf(card.ceiling)).short);
  const changes = n - 1;

  return (
    <figure className="app-chart">
      <figcaption className="app-chart-head">
        <b>{card.name}</b>
        <span className="pl-small pl-muted">{changes === 0 ? 'No changes yet' : `${changes} change${changes === 1 ? '' : 's'}`}</span>
      </figcaption>
      <div className="app-chart-body">
        <ol className="app-chart-axis" aria-hidden="true">
          {labels.map((l) => <li key={l}>{l}</li>)}
        </ol>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${card.name}: ${points.map((p) => (p.paused ? 'paused' : levelCopy(p.level, limitOf(card.ceiling)).short)).join(', then ')}`}>
          {[0, 1, 2, 3].map((r) => (
            <line key={r} x1="0" x2="100" y1={(r + 0.5) * 25} y2={(r + 0.5) * 25} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          {segs.map((s, i) => (
            <g key={i}>
              {i > 0 && (
                <line x1={s.x0} x2={s.x0} y1={segs[i - 1].y} y2={s.y} stroke={s.paused ? 'var(--bad)' : 'var(--ink)'} strokeWidth="2" vectorEffect="non-scaling-stroke" />
              )}
              <line x1={s.x0} x2={s.x1} y1={s.y} y2={s.y} stroke={s.paused ? 'var(--bad)' : 'var(--ink)'} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
            </g>
          ))}
        </svg>
      </div>
    </figure>
  );
}

function eventSentence(data, e, cards) {
  const card = cards.find((c) => c.key === (e.task_class || 'refund'));
  const name = card?.name || 'This job type';
  const to = `“${levelCopy(e.to_level, limitOf(card?.ceiling ?? 0)).short}”`;
  if (e.kind === 'demote') return `${name} paused — a problem was caught`;
  if (e.kind === 'restore') return `A person resumed ${name.toLowerCase()} at ${to}`;
  if (e.kind === 'promote') return `${name} moved up to ${to} after correct jobs`;
  return `${name} changed to ${to}`;
}

export function PermissionChart({ data, cards }) {
  const recent = data.events.slice(0, 5);
  return (
    <div className="app-charts">
      <div className="pl-grid">
        {cards.map((c) => <JobChart key={c.key} data={data} card={c} />)}
      </div>
      {recent.length > 0 && (
        <ul className="pl-list">
          {recent.map((e) => (
            <li key={e.id} className="pl-row">
              <span className="pl-row-main"><b>{eventSentence(data, e, cards)}</b></span>
              <span className="pl-row-side pl-small pl-muted">{when(e.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
