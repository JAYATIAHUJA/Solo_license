import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { clearSession, saveSession } from '../../lib/session.js';
import { Logo } from '../../components/brand/Logo.jsx';
import { HandIcon } from '../../components/icons/HandIcon.jsx';
import { DitherField } from '../../components/shader/PaperBackdrop.jsx';
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

  // `solo-license onboard` opens /access#token=<this machine's admin token>:
  // sign in with it once and drop it from the address bar. The hash never
  // reaches a server.
  useEffect(() => {
    const handed = new URLSearchParams(window.location.hash.slice(1)).get('token');
    if (!handed) return;
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
    enter(async () => {
      saveSession({ token: handed, kind: 'token' });
      const actor = await api.me();
      saveSession({ token: handed, actor, name: actor.id, kind: 'token' });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div className="axo ax">
      <aside className="axo-aside">
        <DitherField className="axo-shader" shape="simplex" speed={0.2} size={2.4} />
        <div className="axo-aside-card">
          <Link to="/" className="axo-logo"><Logo /> Solo License</Link>
          <p className="axo-aside-note hand">
            An agent that earns the right to act alone - and loses it the instant a detection fires.
          </p>
          <ul className="ax-points">
            <li><HandIcon name="dial" size={16} /> Per-task autonomy, L0 → L3</li>
            <li><HandIcon name="eye" size={16} /> Every side effect read back, never trusted</li>
            <li><HandIcon name="commit" size={16} /> Every license change is a git commit</li>
          </ul>
        </div>
      </aside>

      <main className="axo-main">
        <p className="mono muted">Sign in</p>
        <h1 className="axo-title serif">Open your <i>workspace.</i></h1>
        <p className="axo-sub">
          Your name is written into the audit trail of every run and every license change you make.
        </p>

        {info === null && !error && <p className="mono muted">Checking the API…</p>}

        {info?.demo_enabled && (
          <form className="ax-card" onSubmit={startDemo}>
            <div className="ax-card-head">
              <HandIcon name="play" size={18} />
              <div>
                <b>Try the demo</b>
                <small>Local demo session · admin role · no token needed</small>
              </div>
            </div>
            <label className="field">
              <span>Your name</span>
              <input
                className="input axo-big-input"
                autoFocus
                maxLength={40}
                placeholder="e.g. Jayati"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="btn btn-ink" disabled={busy || name.trim().length < 2}>
              {busy ? 'Opening…' : 'Enter the demo'} <HandIcon name="arrow-right" size={16} />
            </button>
          </form>
        )}

        {info && !info.demo_enabled && (
          <div className="ax-card">
            <div className="ax-card-head">
              <HandIcon name="key" size={18} />
              <div>
                <b>Open this dashboard from your terminal</b>
                <small>No token to copy: the command signs you in as this machine's admin.</small>
              </div>
            </div>
            <p className="ax-note"><code>solo-license onboard</code></p>
          </div>
        )}

        {info && (
          <details className="ax-card ax-token">
            <summary>
              <HandIcon name="key" size={18} />
              <div>
                <b>Deployed workspace? Use an access token</b>
                <small>Only for a shared deployment (issued by whoever set it up)</small>
              </div>
            </summary>
            <form onSubmit={useToken} className="ax-token-form">
              <input
                className="input"
                type="password"
                autoComplete="off"
                placeholder="Paste access token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="btn btn-line" disabled={busy || token.trim().length < 8}>Connect</button>
            </form>
          </details>
        )}

        {error && <p className="axo-error"><HandIcon name="warn" size={16} /> {error}</p>}
      </main>
    </div>
  );
}
