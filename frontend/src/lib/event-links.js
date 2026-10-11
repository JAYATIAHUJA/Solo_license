/** Where a permission change's story is told: its neatlogs trace and the
 *  coding agent's Entire checkpoint (ids are 12 hex characters). */
export function eventLinks(event) {
  const url = String(event?.neatlogs_link || '');
  const trace = /^https?:\/\//i.test(url) ? url : null;
  const raw = String(event?.entire_checkpoint || '');
  const id = /^[\w-]+$/.test(raw) ? raw.slice(0, 12) : '';
  return {
    trace,
    checkpoint: id ? { id, explain: `entire checkpoint explain ${id}` } : null,
  };
}
