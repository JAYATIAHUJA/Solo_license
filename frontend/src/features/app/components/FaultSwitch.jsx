import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { FAULTS } from '../../../lib/format.js';
import { Panel } from './Bits.jsx';

/** Arm a deterministic fault for the next run, to prove the detections work. */
export function FaultSwitch() {
  const { data, run, busy } = useStore();
  return (
    <Panel title="Test a failure" icon="bolt">
      <p className="muted app-small">Arms a fault for the <b>next run only</b>. A working system should catch it and demote.</p>
      <div className="app-fault-list">
        {FAULTS.map((f) => (
          <button
            key={f.id}
            className={`app-fault ${data.armed_fault === f.id ? 'is-on' : ''}`}
            disabled={busy}
            onClick={() => run(() => api.arm(f.id), f.id === 'none' ? 'Fault cleared.' : `${f.name} armed for the next run.`)}
          >
            <i className={data.armed_fault === f.id ? 'pat-solid' : 'pat-none'} />
            <span><b>{f.name}</b><small>{f.note}</small></span>
          </button>
        ))}
      </div>
    </Panel>
  );
}
