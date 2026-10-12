import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { capMeter, sessionStatus, sourceWords, totals, usd } from '../../../lib/budget-view.js';
import { when } from '../../../lib/format.js';
import './coding.css';

const POLL_MS = 5000;

function useBudget() {
  const [budget, setBudget] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      setBudget(await api.codingBudget());
      setError('');
    } catch (cause) {
      setError(cause.message);
    }
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);
  return { budget, setBudget, error };
}

function Meter({ spent, cap, warnAt }) {
  const m = capMeter(spent, cap, warnAt);
  return (
    <>
      <div className="app-evidence" role="img" aria-label={`${usd(spent)} of ${usd(cap)}: ${m.label}`}>
        <i style={{ width: `${m.share * 100}%`, background: m.tone === 'ok' ? undefined : `var(--${m.tone})` }} />
      </div>
      <p className="pl-small pl-muted">{usd(spent)} of {cap == null ? 'no cap' : usd(cap)} · <span className={`pl-status ${m.tone}`}>{m.label}</span></p>
    </>
  );
}

/** Budget: what the coding agents spent, against the caps, next to what earned autonomy saved. */
export function Budget() {
  const { budget, setBudget, error } = useBudget();
  const { setToast, load: loadHistory } = useStore();
  const [busy, setBusy] = useState(false);
  const t = totals(budget);

  async function resume(repo, sessionId) {
    setBusy(true);
    try {
      setBudget(await api.codingBudgetResume({ repo, ...(sessionId ? { session_id: sessionId } : {}) }));
      setToast({ kind: 'ok', text: 'Resumed. The agent may continue past the cap for this session and today.', at: Date.now() });
      loadHistory();
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setBusy(false);
    }
  }

  const repos = budget?.repos || [];
  const sessions = budget?.sessions || [];
  const anyCap = repos.some((r) => r.limits?.session_usd != null || r.limits?.day_usd != null);

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Budget</h1>
          <p>What your coding agents spent, against the caps in your policy. Past a cap only reading is allowed until you resume.</p>
        </div>
        <div className="pl-actions">
          <Link to="/app/settings" className="btn btn-ghost btn-sm">Policy</Link>
        </div>
      </header>

      {error && <div className="pl-alert" role="alert"><p>{error}</p></div>}
      {sessions.filter((s) => s.blocked).map((s) => (
        <div key={s.session_id} className="pl-alert app-alert-row" role="alert">
          <p><b>{s.agent} stopped in {s.repo}.</b> {usd(s.usd)} spent; {s.scope === 'day' ? "today's" : "this session's"} cap is reached, so only reading is allowed.</p>
          <button type="button" className="btn btn-ink btn-sm" disabled={busy} onClick={() => resume(s.repo, s.session_id)}>Resume</button>
        </div>
      ))}

      <div className="cd-savings" aria-label="Spend and savings today">
        <div><b>{usd(t.spentToday)}</b><span>spent by agents today</span></div>
        <div><b>{usd(t.saved)}</b><span>developer time saved by earned autonomy</span></div>
        <div><b>{usd(t.net)}</b><span>{t.net >= 0 ? 'ahead after model spend' : 'behind after model spend'}</span></div>
        <div><b>{t.stopped}</b><span>sessions stopped at a cap</span></div>
      </div>

      <section className="pl-section" aria-labelledby="h-caps">
        <h2 id="h-caps">Today, per repository</h2>
        {!repos.length ? (
          <div className="pl-empty">No repositories yet. Spend appears once an agent works in a repository with Solo License installed.</div>
        ) : (
          <div className="pl-grid">
            {repos.map((r) => (
              <div key={r.repo} className="pl-card">
                <h3>{r.repo}</h3>
                <Meter spent={r.day_usd} cap={r.limits?.day_usd} warnAt={r.limits?.warn_at} />
                <p className="pl-small pl-muted">
                  Per session: {r.limits?.session_usd == null ? 'no cap' : usd(r.limits.session_usd)}
                  {r.resumed_today ? ' · resumed by a person today' : ''}
                </p>
              </div>
            ))}
          </div>
        )}
        {repos.length > 0 && !anyCap && (
          <p className="pl-sub">No caps are set. Add <code>[budget]</code> with <code>session_usd</code> and <code>day_usd</code> to <code>.solo-license/policy.toml</code> (run <code>solo-license policy init</code> for a starter file).</p>
        )}
      </section>

      <section className="pl-section" aria-labelledby="h-sessions">
        <h2 id="h-sessions">Recent sessions</h2>
        {!sessions.length ? <div className="pl-empty">No spend recorded yet.</div> : (
          <ul className="pl-list">
            {sessions.map((s) => {
              const st = sessionStatus(s, repos.find((r) => r.repo === s.repo)?.limits?.session_usd);
              return (
                <li key={s.session_id} className="pl-row">
                  <span className="pl-row-main">
                    <b>{usd(s.usd)} · {s.agent}{s.model ? ` (${s.model})` : ''}</b>
                    <small>
                      {s.repo} · session <code>{String(s.session_id).slice(0, 12)}</code> · {when(s.updated_at)}
                      {' · '}{sourceWords(s.source)}{s.tokens ? ` · ${s.tokens.toLocaleString()} tokens` : ''}
                      {s.unpriced?.length ? ` · no price for ${s.unpriced.join(', ')}` : ''}
                    </small>
                  </span>
                  <span className="pl-row-side">
                    <span className={`pl-status ${st.tone}`}>{st.label}</span>
                    {s.blocked && (
                      <button type="button" className="btn btn-line btn-sm" disabled={busy} onClick={() => resume(s.repo, s.session_id)}>Resume</button>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {(budget?.agents || []).length > 0 && (
        <section className="pl-section" aria-labelledby="h-agents">
          <h2 id="h-agents">Where each agent's spend comes from</h2>
          <ul className="pl-list">
            {budget.agents.map((a) => (
              <li key={a.agent} className="pl-row">
                <span className="pl-row-main">
                  <b>{a.label}</b>
                  <small>{a.how} · {a.tool_calls} tool calls seen</small>
                </span>
                <span className="pl-row-side"><span className={`pl-status ${a.source === 'unknown' ? 'muted' : 'ok'}`}>{sourceWords(a.source)}</span></span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
