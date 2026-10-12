/** Pure helpers for what an agent was told on each turn: remediations and loop events. */

/** Map turn id -> rows for that turn. Rows with numeric ids are oldest first; others keep their order. */
export function byTurn(rows) {
  const grouped = new Map();
  for (const row of rows || []) {
    if (row.turn_id == null) continue;
    if (!grouped.has(row.turn_id)) grouped.set(row.turn_id, []);
    grouped.get(row.turn_id).push(row);
  }
  for (const list of grouped.values()) {
    if (list.every((r) => typeof r.id === 'number')) list.sort((a, b) => a.id - b.id);
  }
  return grouped;
}

/** One remediation as shown on its turn: the message and whether the agent has it yet. */
export function remediationView(r) {
  return {
    text: String(r.text || '').replace(/^Solo License:\s*/, ''),
    status: r.delivered_at
      ? { label: 'Delivered', tone: 'ok' }
      : { label: 'Waiting for the next prompt', tone: 'wait' },
  };
}

/** The badge for a turn's loop events, worst first, or null. */
export function loopBadge(events) {
  const list = events || [];
  if (!list.length) return null;
  const halt = list.find((e) => e.kind === 'halt');
  if (halt) return { label: 'Halted: looping', tone: 'bad', title: halt.reason || '' };
  const stop = list.find((e) => e.severity === 'stop');
  if (stop) return { label: 'Stopped: looping', tone: 'bad', title: stop.reason || '' };
  return {
    label: list.length === 1 ? 'Loop warning' : `${list.length} loop warnings`,
    tone: 'wait',
    title: list.map((e) => e.reason || '').join('\n'),
  };
}
