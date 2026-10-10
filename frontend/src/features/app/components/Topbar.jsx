import { Link, useLocation } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { FAULTS, classMeta } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { api } from '../../../lib/api.js';

const TITLES = {
  '': 'Mission control',
  agent: 'Agent desk',
  orders: 'Orders',
  runs: 'Runs & evidence',
  ledger: 'Ledger',
  license: 'Licenses',
  settings: 'Settings',
  autopilot: 'Autopilot',
};

export function Topbar({ onMenu }) {
  const { data, run, busy } = useStore();
  const { pathname } = useLocation();
  const [, , section = '', sub] = pathname.split('/');
  const title = TITLES[section] || section.replace(/-/g, ' ') || 'Mission control';
  const armed = Object.entries(data.armed_faults || { refund: data.armed_fault || 'none' }).filter(([, mode]) => mode && mode !== 'none');
  const llm = data.observability?.llm;
  const mode = llm?.enabled ? `${llm.label} · ${llm.model}` : 'built-in parser';

  return (
    <header className="app-top">
      <button className="app-menu" onClick={onMenu} aria-label="Open menu"><HandIcon name="menu" size={20} /></button>
      <nav className="app-crumbs" aria-label="Breadcrumb">
        <span className="muted">{data.settings.business_name || 'Workspace'}</span>
        <span className="muted">/</span>
        {sub ? (
          <>
            <Link className="muted" to={`/app/${section}`}>{title}</Link>
            <span className="muted">/</span>
            <b>{section === 'runs' ? `Run #${sub}` : sub}</b>
          </>
        ) : <b>{title}</b>}
      </nav>
      <div className="app-top-actions">
        {armed.map(([cls, m]) => (
          <span key={cls} className="app-fault-chip" title={`Armed for the next ${classMeta(data, cls).label.toLowerCase()} run`}>
            <HandIcon name="bolt" size={14} /> <span className="app-fault-chip-text">{FAULTS.find((f) => f.id === m)?.name || m} · {classMeta(data, cls).label}</span>
            <button onClick={() => run(() => api.arm('none', cls), `${classMeta(data, cls).label}: fault cleared.`)} disabled={busy} aria-label={`Clear ${classMeta(data, cls).label} fault`}><HandIcon name="cross" size={12} /></button>
          </span>
        ))}
        <span className="app-mode mono" title="Intake model">{mode}</span>
        <Link to="/app/agent" className="btn btn-ink btn-sm" aria-label="New action"><HandIcon name="plus" size={14} /> <span className="app-top-new">New action</span></Link>
      </div>
    </header>
  );
}
