import { useEffect, useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { FAULTS, classMeta } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { ClassPicker, Panel } from './Bits.jsx';

/** Arm a deterministic fault for one task class's next run, to prove the
 *  detections work. `taskClass` seeds the selection; pass `lockClass` to hide
 *  the class picker. */
export function FaultSwitch({ taskClass = 'refund', lockClass = false }) {
  const { data, run, busy } = useStore();
  const [cls, setCls] = useState(taskClass);
  useEffect(() => setCls(taskClass), [taskClass]);
  const meta = classMeta(data, cls);
  const armed = data.armed_faults?.[cls] ?? (cls === 'refund' ? data.armed_fault : 'none') ?? 'none';
  const license = data.licenses?.[cls];
  const classes = (data.task_classes || []).map((c) => ({ key: c.key, label: c.label }));

  return (
    <Panel
      title="Fault injector"
      icon="bolt"
      tone="raised"
      className={`mc-fault ${armed !== 'none' ? 'is-armed' : ''}`}
      aside={<span className="mono muted">{armed !== 'none' ? 'armed' : 'safe'}</span>}
    >
      <p className="app-small">
        Break the <b>next {meta.label.toLowerCase()} run</b> on purpose. A working verifier catches it, demotes to L0 and quarantines — no false success reaches the customer.
      </p>
      {!lockClass && classes.length > 1 && <ClassPicker classes={classes} value={cls} onChange={setCls} label="Class to break" />}
      {license?.quarantined && <p className="app-small muted mc-inline"><HandIcon name="warn" size={12} /> {meta.label} is already quarantined — runs only suggest until restored.</p>}
      <div className="mc-fault-grid">
        {FAULTS.map((f) => {
          const on = armed === f.id;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={on}
              className={`mc-fault-btn ${on ? 'is-on' : ''} ${f.id === 'none' ? 'is-none' : ''}`}
              disabled={busy}
              onClick={() => run(() => api.arm(f.id, cls), f.id === 'none' ? `${meta.label}: fault cleared.` : `${f.name} armed for the next ${meta.label.toLowerCase()} run.`)}
            >
              <span className="mc-fault-top">
                <i className={on ? 'pat-solid' : 'pat-none'} />
                <b>{f.name}</b>
              </span>
              <small>{f.note}</small>
              {f.catches && <code className="mono">→ {f.catches}</code>}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
