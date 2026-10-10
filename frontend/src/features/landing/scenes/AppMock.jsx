import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Logo } from '../../../components/brand/Logo.jsx';

/* A faithful, static miniature of the app's "Runs & evidence" screen,
   built from the same visual language, for the landing mockup. */
const RUNS = [
  ['#48', 'ORD-1002', '$40.00', 'Demoted', 'pat-hatch', true],
  ['#47', 'ORD-1005', '$45.00', 'Clean', 'pat-solid'],
  ['#46', 'ORD-1003', '$15.00', 'Clean', 'pat-solid'],
  ['#45', 'ORD-1004', '$120.00', 'Awaiting', 'pat-dots'],
  ['#44', 'ORD-1001', '$25.00', 'Clean', 'pat-solid'],
];
const TRACE = [
  ['key', 'license.check', 'level L3 · fault quiet_failure'],
  ['message', 'plan', 'execute under full autonomy'],
  ['play', 'tool.execute_refund', '$40.00 → ORD-1002'],
  ['inbox', 'tool.result', '“Refund processed.” · trusted=false'],
  ['eye', 'verify.readback', '$0.00 → $0.00 · matched=false'],
  ['bolt', 'detection.state_mismatch', 'Intended $40.00 but SQLite moved $0.00', true],
];

export function AppMock() {
  return (
    <div className="am">
      <div className="am-chrome">
        <i /><i /><i />
        <span className="mono">localhost/app/runs/48</span>
      </div>
      <div className="am-body">
        <aside className="am-side">
          <span className="am-logo"><Logo size={14} /> Solo License</span>
          {[['home', 'Overview'], ['message', 'Agent desk'], ['receipt', 'Orders'], ['eye', 'Runs & evidence', true], ['ledger', 'Ledger']].map(([icon, label, on]) => (
            <span key={label} className={`am-nav ${on ? 'is-on' : ''}`}><HandIcon name={icon} size={12} /> {label}</span>
          ))}
          <div className="am-dial"><span className="mono">Autonomy now</span><b className="serif">L0</b><span className="am-alert">Quarantined</span></div>
        </aside>
        <main className="am-main">
          <div className="am-head"><span className="mono">Runs & evidence</span><b className="serif">Every run, <em className="italic">on the record.</em></b></div>
          <div className="am-cols">
            <div className="am-list">
              {RUNS.map(([id, order, amt, status, pat, alert]) => (
                <div key={id} className={`am-row ${id === '#48' ? 'is-on' : ''}`}>
                  <span className="mono">{id}</span><b>{order}</b><span>{amt}</span>
                  <span className={`am-status ${alert ? 'is-alert' : ''}`}><i className={pat} />{status}</span>
                </div>
              ))}
            </div>
            <div className="am-packet" data-anchor="packet">
              <div className="am-nums">
                <div><span className="mono">Level</span><b className="serif">L3</b></div>
                <div><span className="mono">Intended Δ</span><b className="serif">$40.00</b></div>
                <div className="is-alert" data-anchor="verified"><span className="mono">Verified Δ</span><b className="serif">$0.00</b></div>
              </div>
              <ol className="am-trace">
                {TRACE.map(([icon, name, attr, alert]) => (
                  <li key={name} className={alert ? 'is-alert' : ''}><HandIcon name={icon} size={11} /><code>{name}</code><span data-anchor={name === 'tool.result' ? 'tool' : undefined}>{attr}</span></li>
                ))}
              </ol>
              <div className="am-restore" data-anchor="restore">
                <span className="mono">Restore to</span>
                {['L0', 'L1', 'L2', 'L3'].map((l) => <span key={l} className={l === 'L1' ? 'is-on' : ''}>{l}</span>)}
                <span className="am-btn">Restore to L1</span>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
