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

/** GET a text body (CSV exports) with the session token. */
export async function requestText(path) {
  const token = getToken();
  const response = await fetch(apiUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new ApiError(`Download failed (${response.status}).`, response.status);
  return response.text();
}

/** Save text as a file in the browser. */
export function saveText(text, filename, type = 'text/csv') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  codingAgents: () => request('/api/coding/agents', { auth: false }),
  codingInstall: (agent) => request(`/api/coding/install?agent=${encodeURIComponent(agent)}`, { auth: false }),
  testJev: () => request('/api/coding/jev/test', { method: 'POST' }),
  coding: (repo) => request(`/api/coding${repo ? `?repo=${encodeURIComponent(repo)}` : ''}`),
  codingRestore: (body) => request('/api/coding/licenses/restore', { method: 'POST', body }),
  codingRewind: (turnId) => request(`/api/coding/turns/${turnId}/rewind`, { method: 'POST' }),
  codingTestCommand: (repo, testCommand) => request('/api/coding/test-command', { method: 'POST', body: { repo, test_command: testCommand } }),
  session: () => request('/api/session', { auth: false }),
  demoSession: (name) => request('/api/session/demo', { method: 'POST', body: { name }, auth: false }),
  me: () => request('/api/session/me'),
  dashboard: (runId) => request(`/api/dashboard${runId ? `?run_id=${runId}` : ''}`),
  /** Run one action: { order_id, amount?, reason, task_class }. */
  runAction: (body) => request('/api/runs', { method: 'POST', body }),
  refund: (body) => request('/api/runs', { method: 'POST', body }),
  intake: (message, sender) => request('/api/intake', { method: 'POST', body: { message, sender: sender || null, run: true } }),
  handleTicket: (id) => request(`/api/tickets/${id}/handle`, { method: 'POST' }),
  handleNewTickets: () => request('/api/tickets/handle-new', { method: 'POST' }),
  inboxSecret: () => request('/api/inbox/secret'),
  approve: (runId) => request(`/api/runs/${runId}/approve`, { method: 'POST' }),
  reject: (runId) => request(`/api/runs/${runId}/reject`, { method: 'POST' }),
  importOrders: (csv) => request('/api/orders/import', { method: 'POST', body: { csv } }),
  exportOrders: () => requestText('/api/orders/export'),
  exportRuns: () => requestText('/api/runs/export'),
  testStripe: (values) => request('/api/connectors/stripe/test', { method: 'POST', body: { values } }),
  syncStripe: () => request('/api/connectors/stripe/sync', { method: 'POST' }),
  stripeSample: () => request('/api/connectors/stripe/sample', { method: 'POST', body: { confirm_test_mode: true } }),
  arm: (mode, taskClass = 'refund') => request('/api/faults', { method: 'POST', body: { mode, task_class: taskClass } }),
  restore: (level, reason, taskClass = 'refund') => request('/api/restore', { method: 'POST', body: { level, reason, task_class: taskClass } }),
  addOrder: (order) => request('/api/orders', { method: 'POST', body: order }),
  deleteOrder: (id) => request(`/api/orders/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: { values } }),
  listPolicies: () => request('/api/policies'),
  previewPolicy: (body) => request('/api/policies/preview', { method: 'POST', body }),
  activatePolicy: (body) => request('/api/policies', { method: 'POST', body }),
  listPolicyImpacts: () => request('/api/policy-impacts'),
  testLlm: (values) => request('/api/settings/test-llm', { method: 'POST', body: { values } }),
  testNeatlogs: (values) => request('/api/settings/test-neatlogs', { method: 'POST', body: { values } }),
  testAlert: (values) => request('/api/settings/test-alert', { method: 'POST', body: { values } }),
  onboard: (body) => request('/api/onboarding/complete', { method: 'POST', body }),
  reseed: () => request('/api/reseed', { method: 'POST' }),
  topUp: (taskClass = 'refund', count = 4) => request('/api/demo/top-up', { method: 'POST', body: { task_class: taskClass, count } }),
};
