/** Thin fetch wrapper for the FastAPI adapter (proxied at /api by Vite).
 *  Every request carries the session's bearer token; the token lives only in
 *  sessionStorage (never in source, never in VITE_* variables). */
import { clearSession, getToken } from './session.js';
import { apiUrl } from './api-base.js';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('The API is not reachable. Start it with `make run-api`.', 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && auth) clearSession();
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ') : data.detail;
    throw new ApiError(detail || `Request failed (${response.status}).`, response.status);
  }
  return data;
}

export const api = {
  codingAgents: () => request('/api/coding/agents', { auth: false }),
  codingInstall: (agent) => request(`/api/coding/install?agent=${encodeURIComponent(agent)}`, { auth: false }),
  testJev: () => request('/api/coding/jev/test', { method: 'POST' }),
  codingPolicy: (repo) => request(`/api/coding/policy?repo=${encodeURIComponent(repo)}`),
  saveCodingPolicy: (body) => request('/api/coding/policy', { method: 'PUT', body }),
  codingFreeze: (repo, enabled) => request('/api/coding/freeze', { method: 'POST', body: { repo, enabled } }),
  coding: (repo) => request(`/api/coding${repo ? `?repo=${encodeURIComponent(repo)}` : ''}`),
  codingRestore: (body) => request('/api/coding/licenses/restore', { method: 'POST', body }),
  codingRewind: (turnId) => request(`/api/coding/turns/${turnId}/rewind`, { method: 'POST' }),
  codingTestCommand: (repo, testCommand) => request('/api/coding/test-command', { method: 'POST', body: { repo, test_command: testCommand } }),
  session: () => request('/api/session', { auth: false }),
  demoSession: (name) => request('/api/session/demo', { method: 'POST', body: { name }, auth: false }),
  me: () => request('/api/session/me'),
  dashboard: () => request('/api/dashboard'),
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: { values } }),
  testNeatlogs: (values) => request('/api/settings/test-neatlogs', { method: 'POST', body: { values } }),
};
