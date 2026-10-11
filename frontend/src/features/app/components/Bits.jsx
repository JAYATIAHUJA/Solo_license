import { outcome } from '../../../lib/copy.js';

/** Page title block: optional small line above, a plain title, a short sentence, actions on the right. */
export function PageHeader({ eyebrow, title, children, actions }) {
  return (
    <header className="pl-head">
      <div>
        {eyebrow && <p className="pl-small pl-muted app-eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions && <div className="pl-actions">{actions}</div>}
    </header>
  );
}

/** A titled section. `tone="raised"` puts the content on a card. */
export function Panel({ title, count, aside, tone = 'plain', className = '', children }) {
  return (
    <section className={`app-panel is-${tone} ${className}`}>
      {title && (
        <div className="app-panel-head">
          <h2 className="app-panel-title">
            {title}
            {count != null && <span className="app-count">{count}</span>}
          </h2>
          {aside}
        </div>
      )}
      <div className="app-panel-body">{children}</div>
    </section>
  );
}

/** Run outcome in words, with a small coloured dot. */
export function OutcomePill({ status }) {
  const o = outcome(status);
  return <span className={`pl-status ${o.tone}`}>{o.label}</span>;
}

/** Kept for existing callers: same as OutcomePill. */
export const StatusMark = OutcomePill;

export function Empty({ title, children, action }) {
  return (
    <div className="pl-empty app-empty">
      {title && <b>{title}</b>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** Job-type label as quiet text. */
export function ClassTag({ label, className = '' }) {
  return <span className={`app-tag ${className}`}>{label}</span>;
}

/** Server warnings (misconfigured keys, unreachable services) as one notice. */
export function WarningBanner({ warnings }) {
  if (!warnings?.length) return null;
  return (
    <div className="pl-help" role="status">
      <ul className="app-warn-list">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
    </div>
  );
}

/** Segmented picker over the workspace's job types. */
export function ClassPicker({ classes, value, onChange, label = 'Job type', allowAll = false }) {
  const options = allowAll ? [{ key: 'all', label: 'All' }, ...classes] : classes;
  return (
    <div className="app-filters" role="radiogroup" aria-label={label}>
      {options.map((c) => (
        <button key={c.key} type="button" role="radio" aria-checked={value === c.key} className={value === c.key ? 'is-on' : ''} onClick={() => onChange(c.key)}>
          {c.label}
        </button>
      ))}
    </div>
  );
}
