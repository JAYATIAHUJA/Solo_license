/** Build an API URL for either Vite's local proxy or a deployed API origin. */
export function apiUrl(path, apiOrigin = import.meta.env?.VITE_SOLO_API_URL || '') {
  return `${apiOrigin.replace(/\/$/, '')}${path}`;
}
