import { STATUS } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

/** Page title block: small kicker, one serif line, actions on the baseline. */
export function PageHeader({ eyebrow, title, children, actions }) {
  return (
    <header className="app-head">
      <div className="app-head-text">
        {eyebrow && <p className="app-kicker">{eyebrow}</p>}
        <h1 className="serif">{title}</h1>
        {children && <p className="app-head-sub">{children}</p>}
      </div>
      {actions && <div className="app-head-actions">{actions}</div>}
    </header>
  );
}

/** Editorial section: a ruled heading row (label · count · aside) over content.
 *  `tone="raised"` gives it a paper sheet for focal content. */
export function Panel({ title, icon, count, aside, tone = 'plain', className = '', children }) {
  return (
    <section className={`app-panel is-${tone} ${className}`}>
      {title && (
        <div className="app-panel-head">
          <span className="app-panel-title">
            {icon && <HandIcon name={icon} size={15} />}
            {title}
            {count != null && <em className="app-count">{count}</em>}
          </span>
          {aside}
        </div>
      )}
      <div className="app-panel-body">{children}</div>
    </section>
  );
}

/** Status shown as a patterned square + label (no colour coding). */
export function StatusMark({ status }) {
  const s = STATUS[status] || { label: status, pattern: 'pat-none' };
  return (
    <span className={`app-status ${s.alert ? 'is-alert' : ''}`}>
      <i className={s.pattern} />
      {s.label}
    </span>
  );
}

export function Empty({ icon = 'inbox', title, children, action }) {
  return (
    <div className="app-empty">
      <HandIcon name={icon} size={32} strokeWidth={1.3} />
      <b className="serif">{title}</b>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
