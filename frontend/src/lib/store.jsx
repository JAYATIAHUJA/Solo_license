import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';

const StoreContext = createContext(null);

/** Holds the dashboard payload and runs mutations through one place, so every
 *  screen re-renders from the same server truth after any action. */
export function StoreProvider({ children }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const load = useCallback(async (runId) => {
    try {
      setData(await api.dashboard(runId));
      setError('');
    } catch (cause) {
      setError(cause.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = useCallback(async (fn, success) => {
    setBusy(true);
    try {
      const result = await fn();
      if (result && result.license) setData(result);
      const text = typeof success === 'function' ? success(result) : success;
      if (text) setToast({ kind: 'ok', text, at: Date.now() });
      return result;
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const value = useMemo(() => ({ data, error, busy, toast, setToast, load, run }), [data, error, busy, toast, load, run]);
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const store = useContext(StoreContext);
  if (!store) throw new Error('useStore must be used inside <StoreProvider>.');
  return store;
}
