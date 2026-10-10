import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { clearSession, saveSession } from '../../lib/session.js';
import { Logo } from '../../components/brand/Logo.jsx';
import { ONE_LINER } from '../../lib/copy.js';
import '../app/components/plain-form.css';
import '../onboarding/onboarding.css';
import './access.css';

/** Sign-in. Two honest paths: a local demo session (only when the API runs
 *  with SOLO_DEMO_MODE=1) and a deployment-issued access token. The name a
 *  demo user types is recorded as the actor on every run and license change. */
export function Access() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next') || '/app';
  const [info, setInfo] = useState(null);
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.session().then(setInfo).catch((cause) => setError(cause.message));
  }, []);

  async function enter(fn) {
    setBusy(true); setError('');
    try {
      await fn();
      navigate(next, { replace: true });
    } catch (cause) {
      clearSession();
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  const startDemo = (event) => {
    event.preventDefault();
    enter(async () => {
      const session = await api.demoSession(name.trim());
      saveSession({ token: session.token, actor: session.actor, name: name.trim(), kind: 'demo' });
    });
  };

  const useToken = (event) => {
    event.preventDefault();
    enter(async () => {
      saveSession({ token: token.trim(), kind: 'token' });
      const actor = await api.me();
      saveSession({ token: token.trim(), actor, name: actor.id, kind: 'token' });
    });
  };

  return (
    <div className="ob ax">
      <aside className="ob-aside">
        <div className="ob-aside-card">
          <Link to="/" className="ob-brand"><Logo /> Solo License</Link>
          <p className="ob-aside-note">{ONE_LINER}</p>
          <ul className="ax-points">
            <li>Starts by asking permission</li>
            <li>Double-checks every order after it acts</li>
            <li>Every permission change is recorded</li>
          </ul>
        </div>
      </aside>

      <main className="ob-main pl-form">
        <h1 className="ob-title">Sign in</h1>
        <p className="ob-sub">
          Your name is recorded next to everything you approve or change, so you can always see who did what.
        </p>

        {info === null && !error && <p className="pl-muted">Connecting…</p>}

        {info?.demo_enabled && (
          <form className="ax-card" onSubmit={startDemo}>
            <div className="ax-card-head">
              <div>
                <b>Try the demo</b>
                <small>No account needed. Uses sample data.</small>
              </div>
            </div>
            <label className="field">
              <span>Your name</span>
              <input
                className="input ob-big-input"
                autoFocus
                maxLength={40}
                placeholder="e.g. Jayati"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="btn btn-ink" disabled={busy || name.trim().length < 2}>
              {busy ? 'Opening…' : 'Start the demo →'}
            </button>
          </form>
        )}

        {info && (
          <details className="ax-card ax-token" open={!info.demo_enabled}>
            <summary>
              <div>
                <b>Sign in with an access code</b>
                <small>Given to you by whoever set up this workspace</small>
              </div>
            </summary>
            <form onSubmit={useToken} className="ax-token-form">
              <input
                className="input"
                type="password"
                autoComplete="off"
                placeholder="Paste your access code"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="btn btn-line" disabled={busy || token.trim().length < 8}>Sign in</button>
            </form>
            {!info.token_auth && !info.demo_enabled && (
              <p className="ax-note">
                Sign-in isn't set up on this server yet. Whoever runs it can turn on the demo
                (<code>SOLO_DEMO_MODE=1</code>) or create access codes (<code>SOLO_API_TOKENS</code>).
              </p>
            )}
          </details>
        )}

        {error && <p className="ob-error">{error}</p>}
      </main>
    </div>
  );
}
