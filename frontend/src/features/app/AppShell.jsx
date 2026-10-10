import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { useStore } from '../../lib/store.jsx';
import { Sidebar } from './components/Sidebar.jsx';
import { Topbar } from './components/Topbar.jsx';
import { Toast } from './components/Toast.jsx';
import { HandIcon } from '../../components/icons/HandIcon.jsx';
import { Autopilot } from './autopilot/Autopilot.jsx';
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
          <div className="app-boot-error">
            <HandIcon name="warn" size={28} />
            <h1 className="serif">Can’t reach the agent.</h1>
            <p>{error}</p>
            <pre className="mono">make run-api</pre>
            <button className="btn btn-ink" onClick={() => load()}>Try again</button>
          </div>
        ) : (
          <p className="mono">Opening Solo License…</p>
        )}
      </div>
    );
  }
  if (!data.settings.onboarded) return <Navigate to="/onboarding" replace />;

  return (
    <div className={`app ${navOpen ? 'nav-open' : ''}`}>
      <Sidebar onClose={() => setNavOpen(false)} />
      <div className="app-main">
        <Topbar onMenu={() => setNavOpen(true)} />
        <AnimatePresence mode="wait">
          <motion.main
            key={location.pathname.split('/').slice(0, 3).join('/')}
            className="app-page"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            <Outlet />
          </motion.main>
        </AnimatePresence>
      </div>
      <Toast />
      <Autopilot />
    </div>
  );
}
