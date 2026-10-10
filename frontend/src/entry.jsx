import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { StoreProvider, useStore } from './lib/store.jsx';
import { Access } from './features/access/Access.jsx';
import { LandingPage } from './features/landing/LandingPage.jsx';
import { Onboarding } from './features/onboarding/Onboarding.jsx';
import { AppShell } from './features/app/AppShell.jsx';
import { Overview } from './features/app/pages/Overview.jsx';
import { AgentDesk } from './features/app/pages/AgentDesk.jsx';
import { Orders } from './features/app/pages/Orders.jsx';
import { Runs } from './features/app/pages/Runs.jsx';
import { Ledger } from './features/app/pages/Ledger.jsx';
import { Settings } from './features/app/pages/Settings.jsx';
import { SketchDefs } from './components/sketch/SketchDefs.jsx';
import './styles/tokens.css';
import './styles/base.css';

/** Signed-out visitors go to /access and come back to where they were. */
function RequireSession({ children }) {
  const { session } = useStore();
  const location = useLocation();
  if (!session) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/access?next=${next}`} replace />;
  }
  return children;
}

const guarded = (element) => (
  <StoreProvider><RequireSession>{element}</RequireSession></StoreProvider>
);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <SketchDefs />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/landing" element={<Navigate to="/" replace />} />
        <Route path="/access" element={<Access />} />
        <Route path="/onboarding" element={guarded(<Onboarding />)} />
        <Route path="/app" element={guarded(<AppShell />)}>
          <Route index element={<Overview />} />
          <Route path="agent" element={<AgentDesk />} />
          <Route path="orders" element={<Orders />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/:runId" element={<Runs />} />
          <Route path="ledger" element={<Ledger />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
