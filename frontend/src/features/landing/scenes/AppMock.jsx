import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Logo } from '../../../components/brand/Logo.jsx';

/* A faithful, static miniature of the app's coding-agent screen,
   built from the same visual language, for the landing mockup. */
const RUNS = [
  ['#48', 'fix off-by-one', '3 files', 'Paused', 'pat-hatch', true],
  ['#47', 'add qty to total', '1 file', 'Verified', 'pat-solid'],
  ['#46', 'rename helper', '2 files', 'Verified', 'pat-solid'],
  ['#45', 'deploy preview', '-', 'Asked you', 'pat-dots'],
  ['#44', 'fix flaky test', '1 file', 'Verified', 'pat-solid'],
];
const TRACE = [
  ['key', 'gate.allow', 'file-edit · L2 · runs on its own'],
  ['message', 'turn.start', '“fix the off-by-one in cart.js”'],
  ['play', 'tool.Edit', 'cart.js · format.js · utils.js'],
  ['inbox', 'agent.reply', '“Fixed it. All done!”'],
  ['eye', 'turn.check', '210 lines · scope 1/5 · 2 tests fail'],
  ['bolt', 'detection.over_editing', 'asked for 1 line · changed 210', true],
];

export function AppMock() {
  return (
    <div className="am">
      <div className="am-chrome">
        <i /><i /><i />
        <span className="mono">localhost/app · shop-api</span>
      </div>
      <div className="am-body">
        <aside className="am-side">
          <span className="am-logo"><Logo size={14} /> Solo License</span>
          {[['home', 'Coding agent', true], ['ledger', 'Permission history'], ['settings', 'Settings']].map(([icon, label, on]) => (
            <span key={label} className={`am-nav ${on ? 'is-on' : ''}`}><HandIcon name={icon} size={12} /> {label}</span>
          ))}
          <div className="am-dial"><span className="mono">file-edit now</span><b className="serif">L0</b><span className="am-alert">Paused</span></div>
        </aside>
        <main className="am-main">
          <div className="am-head"><span className="mono">Turns, checked at the end</span><b className="serif">Every turn, <em className="italic">on the record.</em></b></div>
          <div className="am-cols">
            <div className="am-list">
              {RUNS.map(([id, task, size, status, pat, alert]) => (
                <div key={id} className={`am-row ${id === '#48' ? 'is-on' : ''}`}>
                  <span className="mono">{id}</span><b>{task}</b><span>{size}</span>
                  <span className={`am-status ${alert ? 'is-alert' : ''}`}><i className={pat} />{status}</span>
                </div>
              ))}
            </div>
            <div className="am-packet" data-anchor="packet">
              <div className="am-nums">
                <div><span className="mono">Level</span><b className="serif">L2</b></div>
                <div><span className="mono">Asked for</span><b className="serif">1 line</b></div>
                <div className="is-alert" data-anchor="verified"><span className="mono">Changed</span><b className="serif">210</b></div>
              </div>
              <ol className="am-trace">
                {TRACE.map(([icon, name, attr, alert]) => (
                  <li key={name} className={alert ? 'is-alert' : ''}><HandIcon name={icon} size={11} /><code>{name}</code><span data-anchor={name === 'agent.reply' ? 'tool' : undefined}>{attr}</span></li>
                ))}
              </ol>
              <div className="am-restore" data-anchor="restore">
                <span className="mono">Resume at</span>
                {['L0', 'L1', 'L2'].map((l) => <span key={l} className={l === 'L1' ? 'is-on' : ''}>{l}</span>)}
                <span className="am-btn">Rewind turn</span>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
