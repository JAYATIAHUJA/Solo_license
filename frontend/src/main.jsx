import React, { useEffect, useState } from 'react';
import { request } from './api.js';
import { Inspector } from './components/Inspector.jsx';
import { RunsDock } from './components/RunsDock.jsx';
import { Sidebar } from './components/Sidebar.jsx';
import { WorkCanvas } from './components/WorkCanvas.jsx';
import './styles.css';

function App() {
  const [data, setData] = useState(null);
  const [theme, setTheme] = useState('light');
  const [orderId, setOrderId] = useState('');
  const [fault, setFault] = useState('none');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [activeSection, setActiveSection] = useState('control');

  async function load(runId) {
    const result = await request(`/api/dashboard${runId ? `?run_id=${runId}` : ''}`);
    setData(result); setOrderId((current) => current || result.orders[0]?.order_id || ''); setFault(result.armed_fault || 'none');
  }
  useEffect(() => { load().catch((cause) => setError(cause.message)); }, []);
  async function act(path, body) {
    setBusy(true); setError('');
    try { const result = await request(path, { method: 'POST', body: JSON.stringify(body) }); setData(result); setFault(result.armed_fault || 'none'); }
    catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }
  if (!data) return <div className="app-loading">Opening Solo License {error && <small>{error}</small>}</div>;
  const sectionTitle = activeSection === 'evidence' ? 'Evidence packet' : activeSection === 'runs' ? 'Recent runs' : 'Refund control room';
  return <div className="product-app" data-theme={theme}>
    <Sidebar activeSection={activeSection} onSectionChange={setActiveSection} busy={busy} theme={theme} onReseed={() => act('/api/reseed', {})} onThemeChange={() => setTheme(theme === 'light' ? 'dark' : 'light')} />
    <section className="workspace-shell">
      <header className="topbar"><div className="crumbs"><i /> Solo License <b>/</b> Refund class <b>/</b> <strong>{sectionTitle}</strong></div><div className="top-actions"><button className="quiet-button" disabled={busy || fault === 'none'} onClick={() => act('/api/faults', { mode: 'none' })}>Clear fault</button></div></header>
      <div className="workspace-title"><h1>{sectionTitle}</h1><span className={data.license.quarantined ? 'state-badge is-alert' : 'state-badge'}><i /> {data.license.quarantined ? 'Quarantined' : 'Live state'}</span></div>
      {error && <div className="error-note">{error}</div>}
      <div className={`work-grid view-${activeSection}`}>
        {activeSection === 'runs'
          ? <RunsDock runs={data.runs} onSelect={(runId) => { setActiveSection('evidence'); load(runId); }} />
          : <WorkCanvas data={data} packet={data.packet} orderId={orderId} fault={fault} busy={busy} condensed={activeSection === 'evidence'} onOrderChange={setOrderId} onFaultChange={(mode) => act('/api/faults', { mode })} onRun={() => act('/api/refunds', { order_id: orderId })} />}
        <Inspector data={data} packet={data.packet} busy={busy} onRestore={(level) => act('/api/restore', { level })} />
      </div>
    </section>
  </div>;
}

export default App;
