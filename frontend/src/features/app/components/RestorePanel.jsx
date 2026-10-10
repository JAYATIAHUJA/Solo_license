import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { LEVELS } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Panel } from './Bits.jsx';

/** Human restore after reviewing evidence. Reason is written to the ledger. */
export function RestorePanel() {
  const { data, run, busy } = useStore();
  const [level, setLevel] = useState(1);
  const [reason, setReason] = useState('');
  if (!data.license.quarantined) return null;
  const fell = data.license.demoted_from;

  return (
    <Panel title="Restore the license" icon="refresh" tone="raised" className="app-restore">
      <p>The refund class fell from <b>L{fell ?? '?'}</b> and is quarantined. Read the evidence, then choose how much trust to give back.</p>
      <div className="app-seg" role="radiogroup" aria-label="Restore level">
        {LEVELS.map((l) => (
          <button key={l.id} role="radio" aria-checked={level === l.id} className={level === l.id ? 'is-on' : ''} onClick={() => setLevel(l.id)}>
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
        onClick={() => run(() => api.restore(level, reason.trim()), `Restored to L${level}. Committed to the ledger.`).then((ok) => ok && setReason(''))}
      >
        <HandIcon name="check" size={16} /> Restore to L{level}
      </button>
    </Panel>
  );
}
