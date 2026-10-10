import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { moneyWhole } from '../../../lib/format.js';
import { LicenseCard } from '../components/mission/LicenseCard.jsx';
import { PermissionChart } from '../components/mission/PermissionChart.jsx';
import { classCards, limitOf, safetyNumbers } from '../components/mission/derive.js';
import './reports.css';

const list = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`);

/** Why the savings number is what it is, in one sentence. */
function savingsReason(cards, saved) {
  const free = cards.filter((c) => !c.paused && c.level >= 2);
  if (!free.length) {
    return saved > 0
      ? 'The agent prepares each job and you approve it with one click, so reviews take less time. Savings grow as it earns more freedom.'
      : 'Right now a person reviews every job, so there is little to save yet. Savings grow as the agent earns freedom.';
  }
  const parts = free.map((c) => `${c.name} ${c.level >= 3 ? 'works alone' : `works alone up to ${limitOf(c.ceiling)}`}`);
  const verb = free.length === 1 && free[0].level < 3 ? 'people only review bigger or unusual cases' : 'people only review the cases the agent passes to them';
  return `Because ${list(parts)}, ${verb}.`;
}

export function Reports() {
  const { data } = useStore();
  const { hash } = useLocation();
  const cards = classCards(data);
  const threshold = data.config.promotion_clean_runs;
  const safety = safetyNumbers(data);
  const econ = data.economics || {};
  const assumptions = econ.assumptions || {};

  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' });
  }, [hash]);

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Reports</h1>
          <p>How safe your agent has been, what it saves you, and how its permissions changed.</p>
        </div>
      </header>

      <section className="pl-section" aria-labelledby="h-numbers">
        <h2 id="h-numbers">The numbers</h2>
        <div className="pl-grid">
          <article className="pl-card">
            <p className="pl-muted pl-small">Problems caught before reaching a customer</p>
            <p className="pl-big">{safety.caught}</p>
            <p>
              {safety.caught === 0 && safety.reached === 0
                ? 'Nothing has gone wrong yet. If something does, the agent is paused before it reaches a customer.'
                : safety.reached === 0
                ? 'None reached a customer. Every time something went wrong, the agent was stopped and paused first.'
                : `${safety.reached} reached a customer before it was caught. Review them in Activity.`}
            </p>
            <p className="pl-small pl-muted">Reached customers: {safety.reached}. Practice problems you set up: {safety.practice}.</p>
          </article>

          <article className="pl-card">
            <p className="pl-muted pl-small">Estimated review time saved</p>
            <p className="pl-big">{moneyWhole(econ.supervision_saved_month)}<span className="app-per"> / month</span></p>
            <p>{savingsReason(cards, econ.supervision_saved_month || 0)}</p>
            <details className="pl-more">
              <summary>How we work this out</summary>
              <dl className="pl-kv app-kv-top">
                <dt>Review time saved</dt><dd>{moneyWhole(econ.supervision_saved_month)} a month</dd>
                <dt>Expected cost of mistakes</dt><dd>{moneyWhole(econ.risk_cost_month)} a month</dd>
                <dt>Saved after mistakes</dt><dd>{moneyWhole(econ.net_saved_month)} a month</dd>
                {assumptions.hourly_cost != null && <><dt>Cost of a person’s hour</dt><dd>{moneyWhole(assumptions.hourly_cost)}</dd></>}
                {assumptions.monthly_volume_per_class != null && <><dt>Jobs a month, per job type</dt><dd>{Number(assumptions.monthly_volume_per_class).toLocaleString('en-US')}</dd></>}
                {assumptions.incident_cost != null && <><dt>Cost of one mistake</dt><dd>{moneyWhole(assumptions.incident_cost)}</dd></>}
              </dl>
              <p className="pl-small pl-muted">Based on your settings. Change them in <Link className="app-link" to="/app/settings">Settings → Advanced</Link>.</p>
            </details>
          </article>
        </div>
      </section>

      <section className="pl-section" aria-labelledby="h-over-time">
        <h2 id="h-over-time">Permission over time</h2>
        <p className="pl-sub">Each line shows what the agent was allowed to do after every change. Red means it was paused.</p>
        <PermissionChart data={data} cards={cards} />
        <Link className="app-link" to="/app/ledger">See full history</Link>
      </section>

      <section className="pl-section" id="licenses" aria-labelledby="h-licenses">
        <h2 id="h-licenses">Agent licenses</h2>
        <p className="pl-sub">One license per job type. Download one as an image or copy a short post to share.</p>
        <div className="app-lic-grid">
          {cards.map((card) => <LicenseCard key={card.key} data={data} card={card} threshold={threshold} />)}
        </div>
      </section>
    </div>
  );
}
