import { useSyncExternalStore } from 'react';

const QUERY = '(max-width: 760px)';

function subscribe(onChange) {
  const mq = window.matchMedia(QUERY);
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

/** True on phone-sized screens, where the landing page stays simple. */
export function usePhone() {
  return useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => false);
}
