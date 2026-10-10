import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { LEVELS, classMeta } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Panel } from './Bits.jsx';

/** Human restore of one quarantined task class after reviewing the evidence.
 *  The reason is written to the git ledger. */
export function RestorePanel({ taskClass = 'refund', evidenceRunId }) {
  const { data, run, busy } = useStore();
  const [level, setLevel] = useState(1);
  const [reason, setReason] = useState('');
  const license = data.licenses?.[taskClass];
  if (!license?.quarantined) return null;
  const meta = classMeta(data, taskClass);
  const fell = license.demoted_from;
  const evidence = evidenceRunId ?? data.runs.find((r) => r.task_class === taskClass && r.status === 'demoted')?.id;

  return (
    <Panel title={`Restore · ${meta.label}`} icon="refresh" tone="raised" className="app-restore" aside={evidence ? <Link className="app-link" to={`/app/runs/${evidence}`}>Evidence #{evidence} →</Link> : null}>
      <p>The <b>{meta.label.toLowerCase()}</b> class fell from <b>L{fell ?? '?'}</b> and is quarantined. Read the evidence, then choose how much trust to give back.</p>
      <div className="app-seg" role="radiogroup" aria-label="Restore level">
        {LEVELS.map((l) => (
          <button key={l.id} type="button" role="radio" aria-checked={level === l.id} className={level === l.id ? 'is-on' : ''} onClick={() => setLevel(l.id)}>
            <b>{l.code}</b><span>{l.name}</span>
          </button>
        ))}
      </div>
      <label className="field">
        <span>Reason (goes in the git ledger)</span>
        <input className="input" placeholder="e.g. Tool bug fixed in v1.4; verified on staging" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
      </label>
      <button
        className="btn btn-ink"
        disabled={busy || reason.trim().length < 4}
        onClick={() => run(() => api.restore(level, reason.trim(), taskClass), `${meta.label} restored to L${level}. Committed to the ledger.`).then((ok) => ok && setReason(''))}
      >
        <HandIcon name="check" size={16} /> Restore {meta.label.toLowerCase()} to L{level}
      </button>
    </Panel>
  );
}

/** Every quarantined class's restore panel, side by side. */
export function RestorePanels() {
  const { data } = useStore();
  const keys = Object.entries(data.licenses || {}).filter(([, l]) => l.quarantined).map(([k]) => k);
  if (!keys.length) return null;
  return (
    <div className="mc-restores">
      {keys.map((k) => <RestorePanel key={k} taskClass={k} />)}
    </div>
  );
}
