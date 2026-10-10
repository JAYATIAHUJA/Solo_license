import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { clearSession } from '../../../lib/session.js';
import { Logo } from '../../../components/brand/Logo.jsx';
import { classCards, waitingRuns } from './mission/derive.js';

const NAV = [
  { to: '/app', end: true, label: 'Home' },
  { to: '/app/agent', label: 'Try the agent' },
  { to: '/app/runs', label: 'Activity', badge: 'waiting' },
  { to: '/app/reports', label: 'Reports' },
  { to: '/app/orders', label: 'Orders' },
  { to: '/app/ledger', label: 'History' },
  { to: '/app/settings', label: 'Settings' },
];

export function Sidebar({ onClose }) {
  const { data, session } = useStore();
  const navigate = useNavigate();
  const cards = classCards(data);
  const badges = { waiting: waitingRuns(data).length };

  function signOut() {
    clearSession();
    navigate('/access');
  }

  return (
    <aside className="app-side">
      <div className="app-side-top">
        <Link to="/app" className="app-brand"><Logo size={18} /> Solo License</Link>
        <button className="app-side-close btn btn-ghost btn-sm" onClick={onClose} aria-label="Close menu">Close</button>
      </div>
      {data.settings.business_name && <p className="app-side-biz">{data.settings.business_name}</p>}

      <nav className="app-nav" aria-label="Main">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `app-nav-link ${isActive ? 'is-active' : ''}`}>
            <span>{item.label}</span>
            {item.badge && badges[item.badge] > 0 && (
              <em className="app-badge" aria-label={`${badges[item.badge]} waiting for you`}>{badges[item.badge]}</em>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="app-side-status" aria-label="What the agent may do">
        <p className="app-side-label">Your agent</p>
        {cards.map((c) => (
          <Link key={c.key} to="/app" className={`app-side-job ${c.paused ? 'is-paused' : ''}`}>
            <b>{c.name}</b>
            <span>{c.paused ? 'Paused' : c.copy.short}</span>
          </Link>
        ))}
      </div>

      <div className="app-side-foot">
        {session?.name && <p className="app-side-user">Signed in as <b>{session.name}</b></p>}
        <button className="btn btn-line btn-sm" onClick={signOut}>Sign out</button>
      </div>
    </aside>
  );
}
