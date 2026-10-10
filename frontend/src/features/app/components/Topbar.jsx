import { Link, useLocation } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { FAULTS } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { api } from '../../../lib/api.js';

const TITLES = { '': 'Overview', agent: 'Agent desk', orders: 'Orders', runs: 'Runs & evidence', ledger: 'Ledger', settings: 'Settings' };

export function Topbar({ onMenu }) {
  const { data, run, busy } = useStore();
  const { pathname } = useLocation();
  const section = pathname.split('/')[2] || '';
  const fault = FAULTS.find((f) => f.id === data.armed_fault);

  return (
    <header className="app-top">
      <button className="app-menu" onClick={onMenu} aria-label="Open menu"><HandIcon name="menu" size={20} /></button>
      <div className="app-crumbs">
        <span className="muted">{data.settings.business_name || 'Workspace'}</span>
        <span className="muted">/</span>
        <span className="muted">refund</span>
        <span className="muted">/</span>
        <b>{TITLES[section] || 'Overview'}</b>
      </div>
      <div className="app-top-actions">
        {data.armed_fault !== 'none' && (
          <span className="app-fault-chip">
            <HandIcon name="bolt" size={14} /> {fault?.name} armed
            <button onClick={() => run(() => api.arm('none'), 'Fault cleared.')} disabled={busy} aria-label="Clear fault"><HandIcon name="cross" size={12} /></button>
          </span>
        )}
        <span className="app-mode mono">{data.settings.llm_enabled ? `model · ${data.settings.llm_provider}` : 'built-in parser'}</span>
        <Link to="/app/agent" className="btn btn-ink btn-sm"><HandIcon name="plus" size={14} /> New refund</Link>
      </div>
    </header>
  );
}
