/** Plain helpers for the Budget page (kept out of the component so they are tested). */

const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** $1.20, or "-" when there is no figure (no cap set). */
export const usd = (n) => (n == null || Number.isNaN(Number(n)) ? '-' : USD.format(Number(n)));

/** How far along a cap the spend is: { share 0..1, tone } - tone follows the policy's warn line. */
export function capMeter(spent, cap, warnAt = 0.8) {
  if (cap == null || !(cap > 0)) return { share: 0, tone: 'muted', label: 'No cap' };
  const ratio = Math.max(0, Number(spent || 0)) / cap;
  const tone = ratio >= 1 ? 'bad' : ratio >= warnAt ? 'wait' : 'ok';
  const label = ratio >= 1 ? 'Cap reached' : ratio >= warnAt ? 'Near the cap' : 'Under the cap';
  return { share: Math.min(1, ratio), tone, label };
}

/** The status chip for one session row; ``sessionCap`` tells a resumed session from one under its cap. */
export function sessionStatus(s, sessionCap = null) {
  if (s?.blocked) return { tone: 'bad', label: s.scope === 'day' ? "Stopped: today's cap" : 'Stopped: session cap' };
  if (s?.state === 'cap' || (sessionCap != null && Number(s?.usd || 0) >= sessionCap)) {
    return { tone: 'ok', label: 'Resumed by a person' };
  }
  if (s?.state === 'warn') return { tone: 'wait', label: 'Near the cap' };
  return { tone: 'ok', label: 'Under the cap' };
}

/** Where a figure comes from, in words. */
export function sourceWords(source) {
  if (source === 'reported') return "the agent's own figure";
  if (source === 'estimate') return 'estimated from tokens at list price';
  return 'not reported';
}

/** Totals across repositories for today, next to what earned autonomy saved. */
export function totals(budget) {
  const spentToday = (budget?.repos || []).reduce((sum, r) => sum + Number(r.day_usd || 0), 0);
  const saved = Number(budget?.savings?.usd_saved || 0);
  const stopped = (budget?.sessions || []).filter((s) => s.blocked).length;
  return { spentToday, saved, stopped, net: saved - spentToday };
}
