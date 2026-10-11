import { Link, useLocation } from 'react-router-dom';

const TITLES = { '': 'Coding agent', ledger: 'Permission history', settings: 'Settings' };

export function Topbar({ onMenu }) {
  const { pathname } = useLocation();
  const [, , section = ''] = pathname.split('/');

  return (
    <header className="app-top">
      <button className="app-menu btn btn-ghost btn-sm" onClick={onMenu} aria-label="Open menu">Menu</button>
      <p className="app-top-title">{TITLES[section] ?? 'Coding agent'}</p>
      <div className="app-top-actions">
        {section !== '' && <Link to="/app" className="btn btn-ink btn-sm">Coding agent</Link>}
      </div>
    </header>
  );
}
