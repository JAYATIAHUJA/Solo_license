import { useEffect, useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { classMeta } from '../../../lib/format.js';
import { PRACTICE } from '../../../lib/copy.js';
import { jobIs, jobName } from './mission/derive.js';

/** Practice mode: arm a deliberate problem for one job type's next action, so
 *  the owner can watch the safety net catch it. `taskClass` seeds the choice;
 *  `lockClass` hides the job-type picker. */
export function FaultSwitch({ taskClass = 'refund', lockClass = false }) {
  const { data, run, busy } = useStore();
  const [cls, setCls] = useState(taskClass);
  useEffect(() => setCls(taskClass), [taskClass]);
  const name = jobName(classMeta(data, cls));
  const armed = data.armed_faults?.[cls] ?? (cls === 'refund' ? data.armed_fault : 'none') ?? 'none';
  const paused = !!data.licenses?.[cls]?.quarantined;
  const classes = data.task_classes || [];

  return (
    <div className="app-practice">
      <p className="pl-muted pl-small">Arm a practice problem for the next action to see the safety net catch it. Practice runs are labelled as practice in your history.</p>
      {!lockClass && classes.length > 1 && (
        <label className="field">
          <span>Job type</span>
          <select className="input" value={cls} onChange={(e) => setCls(e.target.value)}>
            {classes.map((c) => <option key={c.key} value={c.key}>{jobName(c)}</option>)}
          </select>
        </label>
      )}
      {paused && <p className="pl-small">{jobIs(name)} already paused, so the next action will only be suggested.</p>}
      <div className="app-practice-options" role="radiogroup" aria-label={`Practice problem for ${name}`}>
        {PRACTICE.map((p) => {
          const on = armed === p.id;
          return (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={on}
              className={`app-option ${on ? 'is-on' : ''}`}
              disabled={busy}
              onClick={() => run(() => api.arm(p.id, cls), p.id === 'none' ? `Practice problem cleared for ${name}.` : `Practice problem armed for the next ${name.toLowerCase()} action.`)}
            >
              <b>{p.title}</b>
              <small>{p.explain}</small>
            </button>
          );
        })}
      </div>
    </div>
  );
}
