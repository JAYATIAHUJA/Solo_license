export async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    throw new Error((await response.json()).detail || 'Request failed.');
  }
  return response.json();
}
