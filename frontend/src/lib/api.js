/** Thin fetch wrapper for the FastAPI adapter (proxied at /api by Vite). */
export async function request(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('The API is not reachable. Start it with `make run-api`.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ') : data.detail;
    throw new Error(detail || `Request failed (${response.status}).`);
  }
  return data;
}

export const api = {
  dashboard: (runId) => request(`/api/dashboard${runId ? `?run_id=${runId}` : ''}`),
  refund: (body) => request('/api/refunds', { method: 'POST', body }),
  intake: (message) => request('/api/intake', { method: 'POST', body: { message, run: true } }),
  approve: (runId) => request(`/api/runs/${runId}/approve`, { method: 'POST' }),
  arm: (mode) => request('/api/faults', { method: 'POST', body: { mode } }),
  restore: (level, reason) => request('/api/restore', { method: 'POST', body: { level, reason } }),
  addOrder: (order) => request('/api/orders', { method: 'POST', body: order }),
  deleteOrder: (id) => request(`/api/orders/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: { values } }),
  testLlm: (values) => request('/api/settings/test-llm', { method: 'POST', body: { values } }),
  onboard: (body) => request('/api/onboarding/complete', { method: 'POST', body }),
  reseed: () => request('/api/reseed', { method: 'POST' }),
};
