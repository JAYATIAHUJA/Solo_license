import { money } from '../../../../lib/format.js';
import { HandIcon } from '../../../../components/icons/HandIcon.jsx';
import { proofMetrics } from './derive.js';

/** "Verified, not trusted." Every figure is computed from the run table: a
 *  false success is an executed fault run that was NOT demoted. It should be 0. */
export function ProofStrip({ data }) {
  const m = proofMetrics(data);
  const perfect = m.falseSuccesses === 0;
  return (
    <section className="mc-proof" aria-label="Verification proof">
      <header className="mc-proof-head">
        <span className="app-kicker">Verified, not trusted</span>
        <span className="app-small muted">Every number below is read back from the database, not the tool’s reply.</span>
      </header>
      <dl className="mc-proof-grid">
        <div><dt className="app-kicker">Runs executed</dt><dd className="serif">{m.executed}</dd></div>
        <div><dt className="app-kicker">Faults injected</dt><dd className="serif">{m.faultsInjected}</dd></div>
        <div><dt className="app-kicker">Faults caught</dt><dd className="serif">{m.caught}<small> demotions</small></dd></div>
        <div className={`mc-proof-key ${perfect ? '' : 'is-alert'}`}>
          <dt className="app-kicker">False successes reached customer</dt>
          <dd className="serif">
            {m.falseSuccesses}
            {perfect && <span className="mc-proof-ok mono"><HandIcon name="check" size={12} /> none</span>}
          </dd>
        </div>
        <div><dt className="app-kicker">Paid out · verified</dt><dd className="serif">{money(m.paidOut)}</dd></div>
      </dl>
    </section>
  );
}
