import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useStore } from '../../lib/store.jsx';
import { Sidebar } from './components/Sidebar.jsx';
import { Topbar } from './components/Topbar.jsx';
import { Toast } from './components/Toast.jsx';
import './app.css';

export function AppShell() {
  const { data, error, status, load } = useStore();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => setNavOpen(false), [location.pathname]);

  if (!data && status === 401) return <Navigate to="/access?next=%2Fapp" replace />;
  if (!data) {
    return (
      <div className="app-boot">
        {error ? (
          <div className="pl-card app-boot-error">
            <h1>We can’t reach your agent right now</h1>
            <p>{error}</p>
            <p className="pl-small pl-muted">If you run Solo License yourself, start the server with <code>make run-api</code>, then try again.</p>
            <button className="btn btn-ink" onClick={() => load()}>Try again</button>
          </div>
        ) : (
          <p className="pl-muted">Opening Solo License…</p>
        )}
      </div>
    );
  }
  return (
    <div className={`app ${navOpen ? 'nav-open' : ''}`}>
      <Sidebar onClose={() => setNavOpen(false)} />
      {navOpen && <button className="app-scrim" aria-label="Close menu" onClick={() => setNavOpen(false)} />}
      <div className="app-main">
        <Topbar onMenu={() => setNavOpen(true)} />
        <main className="app-page">
          <Outlet />
        </main>
      </div>
      <Toast />
    </div>
  );
}
