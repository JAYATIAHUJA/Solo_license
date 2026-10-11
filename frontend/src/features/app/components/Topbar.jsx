import { Link, useLocation } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { api } from '../../../lib/api.js';
import { classMeta } from '../../../lib/format.js';
import { jobName } from './mission/derive.js';

const TITLES = {
  '': 'Home',
  inbox: 'Inbox',
  agent: 'Try the agent',
  orders: 'Orders',
  runs: 'Activity',
  reports: 'Reports',
  ledger: 'History',
  settings: 'Settings',
};

export function Topbar({ onMenu }) {
  const { data, run, busy } = useStore();
  const { pathname } = useLocation();
  const [, , section = ''] = pathname.split('/');
  const title = TITLES[section] ?? 'Home';
  const armed = Object.entries(data.armed_faults || { refund: data.armed_fault || 'none' }).filter(([, mode]) => mode && mode !== 'none');

  return (
    <header className="app-top">
      <button className="app-menu btn btn-ghost btn-sm" onClick={onMenu} aria-label="Open menu">Menu</button>
      <p className="app-top-title">{title}</p>
      <div className="app-top-actions">
        {armed.map(([cls]) => {
          const name = jobName(classMeta(data, cls));
          return (
            <span key={cls} className="app-practice-chip">
              <span className="app-chip-long">Practice problem armed for {name}</span>
              <span className="app-chip-short">Practice: {name}</span> ·{' '}
              <button type="button" onClick={() => run(() => api.arm('none', cls), `Practice problem cleared for ${name}.`)} disabled={busy}>clear</button>
            </span>
          );
        })}
        {section !== 'agent' && <Link to="/app/agent" className="btn btn-ink btn-sm">Try the agent</Link>}
      </div>
    </header>
  );
}
