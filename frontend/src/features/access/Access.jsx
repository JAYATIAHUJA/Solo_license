import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { clearSession, saveSession } from '../../lib/session.js';
import { Logo } from '../../components/brand/Logo.jsx';
import { PaperGrain } from '../../components/shader/PaperBackdrop.jsx';
import { HandIcon } from '../../components/icons/HandIcon.jsx';
import { DitherField } from '../../components/shader/PaperBackdrop.jsx';
import './access.css';

/** Sign-in. The access token is the front door: `solo-license onboard` opens
 *  this page already signed in, `solo-license token` prints it for pasting.
 *  A local demo session stays available (only when the API runs with
 *  SOLO_DEMO_MODE=1), tucked away. */
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
      <PaperGrain opacity={0.3} />
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
        <h1 className="axo-title serif">Paste your <i>access token.</i></h1>

        <form className="ax-card" onSubmit={useToken}>
          <label className="field">
            <span>Access token</span>
            <input
              className="input axo-big-input"
              type="password"
              autoComplete="off"
              autoFocus
              placeholder="Paste access token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <button className="btn btn-ink" disabled={busy || token.trim().length < 8}>
            {busy ? 'Opening…' : 'Open dashboard'} <HandIcon name="arrow-right" size={16} />
          </button>
          <p className="ax-note">
            Get it in your terminal: <code>solo-license token</code>. Running <code>solo-license onboard</code> opens
            this page already signed in.
          </p>
        </form>

        {info?.demo_enabled && (
          <details className="ax-demo">
            <summary>No token? Use the local demo instead</summary>
            <form onSubmit={startDemo} className="ax-token-form">
              <input
                className="input"
                maxLength={40}
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <button className="btn btn-line" disabled={busy || name.trim().length < 2}>Enter the demo</button>
            </form>
          </details>
        )}

        {error && <p className="axo-error"><HandIcon name="warn" size={16} /> {error}</p>}
      </main>
    </div>
  );
}
