import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { clearSession } from '../../../lib/session.js';
import { Logo } from '../../../components/brand/Logo.jsx';

const NAV = [
  { to: '/app', end: true, label: 'Coding agent' },
  { to: '/app/ledger', label: 'Permission history' },
  { to: '/app/settings', label: 'Settings' },
];

export function Sidebar({ onClose }) {
  const { session } = useStore();
  const navigate = useNavigate();

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

      <nav className="app-nav" aria-label="Main">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `app-nav-link ${isActive ? 'is-active' : ''}`}>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="app-side-foot">
        {session?.name && <p className="app-side-user">Signed in as <b>{session.name}</b></p>}
        <button className="btn btn-line btn-sm" onClick={signOut}>Sign out</button>
      </div>
    </aside>
  );
}
