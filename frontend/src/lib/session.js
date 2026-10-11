/** Browser-side session: a bearer token plus who signed in. Kept in
 *  sessionStorage so closing the tab signs out; storage failures (private
 *  mode, blocked storage) degrade to an in-memory session. */
const KEY = 'solo-license.session';
let memory = null;

function read() {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : memory;
  } catch {
    return memory;
  }
}

export function getSession() {
  return read();
}

export function getToken() {
  return read()?.token || null;
}

export function saveSession(session) {
  memory = session;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    /* in-memory only */
  }
  window.dispatchEvent(new Event('solo-session'));
}

export function clearSession() {
  memory = null;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event('solo-session'));
}
