import { Link, NavLink } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { LEVELS } from '../../../lib/format.js';
import { Logo } from '../../../components/brand/Logo.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const GROUPS = [
  {
    label: 'Operate',
    items: [
      { to: '/app', end: true, icon: 'home', label: 'Overview' },
      { to: '/app/agent', icon: 'message', label: 'Agent desk' },
      { to: '/app/runs', icon: 'eye', label: 'Runs & evidence', badge: 'pending' },
    ],
  },
  {
    label: 'Records',
    items: [
      { to: '/app/orders', icon: 'receipt', label: 'Orders', badge: 'orders' },
      { to: '/app/ledger', icon: 'ledger', label: 'Ledger' },
    ],
  },
];

export function Sidebar({ onClose }) {
  const { data } = useStore();
  const { license, stats, settings, orders } = data;
  const level = LEVELS[license.effective_level];
  const badges = { pending: stats.pending_approval, orders: orders.length };

  return (
    <aside className="app-side">
      <div className="app-side-top">
        <Link to="/" className="app-brand"><Logo size={18} /> Solo License</Link>
        <button className="app-side-close" onClick={onClose} aria-label="Close menu"><HandIcon name="cross" size={18} /></button>
      </div>

      <div className="app-workspace">
        <span className="app-workspace-mark serif">{(settings.business_name || 'W').slice(0, 1).toUpperCase()}</span>
        <span className="app-workspace-text">
          <b>{settings.business_name || 'Workspace'}</b>
          <small>Task class · refund</small>
        </span>
      </div>

      {GROUPS.map((g) => (
        <nav key={g.label} className="app-nav" aria-label={g.label}>
          <span className="app-nav-label">{g.label}</span>
          {g.items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `app-nav-link ${isActive ? 'is-active' : ''}`}>
              <HandIcon name={item.icon} size={17} />
              <span>{item.label}</span>
              {item.badge && badges[item.badge] > 0 && (
                <em className={`app-badge ${item.badge === 'pending' ? 'is-strong' : ''}`}>{badges[item.badge]}</em>
              )}
            </NavLink>
          ))}
        </nav>
      ))}

      <Link to="/app" className={`app-side-dial ${license.quarantined ? 'is-q' : ''}`} title="Current autonomy level">
        <span className="app-nav-label">Autonomy</span>
        <span className="app-side-dial-row">
          <b className="serif">{level.code}</b>
          <span className="app-mini-rungs" aria-hidden="true">
            {[0, 1, 2, 3].map((r) => <i key={r} className={r <= license.effective_level && !license.quarantined ? 'on' : ''} />)}
          </span>
        </span>
        <small>{license.quarantined ? 'Quarantined — review needed' : level.name}</small>
      </Link>

      <nav className="app-nav app-nav-foot" aria-label="Account">
        <NavLink to="/app/settings" className={({ isActive }) => `app-nav-link ${isActive ? 'is-active' : ''}`}>
          <HandIcon name="settings" size={17} /><span>Settings</span>
        </NavLink>
        <Link to="/" className="app-nav-link"><HandIcon name="logout" size={17} /><span>Back to site</span></Link>
      </nav>
    </aside>
  );
}
