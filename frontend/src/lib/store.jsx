import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';
import { getSession } from './session.js';

const StoreContext = createContext(null);
const POLL_MS = 6000;

/** Holds the dashboard payload and runs mutations through one place, so every
 *  screen re-renders from the same server truth after any action. While the
 *  tab is visible it also polls, so runs made elsewhere (another tab, the
 *  evidence script, a teammate) show up live. */
export function StoreProvider({ children }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const [session, setSession] = useState(getSession);
  const busyRef = useRef(false);

  useEffect(() => {
    const sync = () => setSession(getSession());
    window.addEventListener('solo-session', sync);
    return () => window.removeEventListener('solo-session', sync);
  }, []);

  const load = useCallback(async () => {
    try {
      setData(await api.dashboard());
      setError('');
      setStatus(0);
    } catch (cause) {
      setError(cause.message);
      setStatus(cause.status || 0);
    }
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !busyRef.current) load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load, session]);

  const run = useCallback(async (fn, success) => {
    setBusy(true);
    busyRef.current = true;
    try {
      const result = await fn();
      if (result && result.settings) setData(result);
      const text = typeof success === 'function' ? success(result) : success;
      if (text) setToast({ kind: 'ok', text, at: Date.now() });
      return result;
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
      return null;
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  }, []);

  const value = useMemo(
    () => ({ data, error, status, busy, toast, setToast, load, run, session }),
    [data, error, status, busy, toast, load, run, session],
  );
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const store = useContext(StoreContext);
  if (!store) throw new Error('useStore must be used inside <StoreProvider>.');
  return store;
}
