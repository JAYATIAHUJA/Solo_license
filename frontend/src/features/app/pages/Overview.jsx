import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { when } from '../../../lib/format.js';
import { outcome } from '../../../lib/copy.js';
import { ApproveBar } from '../components/ApproveBar.jsx';
import { WarningBanner } from '../components/Bits.jsx';
import {
  classCards, jobIs, pausingRun, problemFor, progressText, runSentence, waitingRuns,
} from '../components/mission/derive.js';
import { openDemo } from '../autopilot/Autopilot.jsx';

const lcFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);
const HELP_KEY = 'solo-license.home-help-dismissed';

function readDismissed() {
  try {
    return window.localStorage.getItem(HELP_KEY) === '1';
  } catch {
    return false;
  }
}

function HowItWorks() {
  const [hidden, setHidden] = useState(readDismissed);
  if (hidden) return null;
  const dismiss = () => {
    setHidden(true);
    try {
      window.localStorage.setItem(HELP_KEY, '1');
    } catch {
      /* the box just comes back next visit */
    }
  };
  return (
    <div className="pl-help app-howto">
      <div>
        <b>How it works</b>
        <ol>
          <li>Your agent starts by asking you before it does anything.</li>
          <li>After a few correct jobs it earns more freedom for that kind of job.</li>
          <li>The moment something goes wrong it is paused. You decide when it can carry on.</li>
        </ol>
      </div>
      <button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>Got it</button>
    </div>
  );
}

export function Overview() {
  const { data, session } = useStore();
  const { runs, settings } = data;
  const threshold = data.config.promotion_clean_runs;
  const cards = classCards(data);
  const paused = cards.filter((c) => c.paused);
  const waiting = waitingRuns(data);
  const recent = runs.slice(0, 5);
  const first = session?.name ? session.name.split(/\s+/)[0] : '';

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>{first ? `Hi ${first}` : 'Welcome back'}</h1>
          <p>{settings.business_name ? `${settings.business_name} · ` : ''}Here is what your agent is doing.</p>
        </div>
        <div className="pl-actions">
          <button type="button" className="btn btn-line btn-sm" onClick={openDemo}>Watch a 1-minute demo</button>
          <Link to="/app/agent" className="btn btn-ink btn-sm">Try the agent</Link>
        </div>
      </header>

      {paused.map((c) => {
        const r = pausingRun(data, c.key);
        return (
          <div key={c.key} className="pl-alert app-alert-row" role="alert">
            <p>
              <b>{jobIs(c.name)} paused.</b>{' '}
              {r ? <>A problem was caught on {r.order_id} — {lcFirst(problemFor(data, r).title)}. </> : 'A problem was caught. '}
              Nothing will run on its own until you review it.
            </p>
            <Link to={r ? `/app/runs/${r.id}` : '/app/runs'} className="btn btn-ink btn-sm">Review and resume</Link>
          </div>
        );
      })}

      <HowItWorks />
      <WarningBanner warnings={data.warnings} />

      <section className="pl-section" aria-labelledby="h-allowed">
        <h2 id="h-allowed">What your agent is allowed to do</h2>
        <div className="pl-grid">
          {cards.map((c) => (
            <article key={c.key} className="pl-card">
              <div className="app-card-top">
                <h3>{c.name}</h3>
                <span className={`pl-status ${c.paused ? 'bad' : c.level >= 2 ? 'ok' : 'wait'}`}>{c.paused ? 'Paused' : c.copy.short}</span>
              </div>
              <p>{c.paused ? 'For now it only suggests what to do. You do it.' : c.copy.long}</p>
              <p className="pl-small pl-muted">{progressText(c, threshold)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="pl-section" aria-labelledby="h-waiting">
        <h2 id="h-waiting">Waiting for you</h2>
        {waiting.length === 0 ? (
          <div className="pl-empty">Nothing is waiting for you.</div>
        ) : (
          <ul className="pl-list">
            {waiting.slice(0, 8).map((r) => (
              <li key={r.id} className="pl-row">
                <span className="pl-row-main">
                  <b><Link to={`/app/runs/${r.id}`}>{runSentence(data, r)}</Link></b>
                  <small>{r.status === 'suggested' ? 'Suggested by the agent' : 'Needs your OK'} · {when(r.created_at)}</small>
                </span>
                <span className="pl-row-side"><ApproveBar run={r} compact /></span>
              </li>
            ))}
          </ul>
        )}
        {waiting.length > 8 && <Link className="app-link" to="/app/runs">See all {waiting.length} waiting</Link>}
      </section>

      <section className="pl-section" aria-labelledby="h-recent">
        <h2 id="h-recent">What happened recently</h2>
        {recent.length === 0 ? (
          <div className="pl-empty">
            Nothing yet. <Link className="app-link" to="/app/agent">Give the agent a customer message</Link> to see it work.
          </div>
        ) : (
          <ul className="pl-list">
            {recent.map((r) => {
              const o = outcome(r.status);
              return (
                <li key={r.id}>
                  <Link to={`/app/runs/${r.id}`} className="pl-row">
                    <span className="pl-row-main">
                      <b>{runSentence(data, r)}</b>
                      <small>{when(r.created_at)}</small>
                    </span>
                    <span className="pl-row-side"><span className={`pl-status ${o.tone}`}>{o.label}</span></span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {recent.length > 0 && <Link className="app-link" to="/app/runs">See all activity</Link>}
      </section>
    </div>
  );
}
