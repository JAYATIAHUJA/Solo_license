const CURRENCY_WHOLE = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

/** $22,500 - for monthly savings, where cents are noise. */
export const moneyWhole = (n) => CURRENCY_WHOLE.format(Math.round(Number(n || 0)));

/** Server timestamps are naive UTC ("2026-10-10 22:21:11"). */
export function toDate(ts) {
  if (!ts) return null;
  const date = new Date(`${String(ts).replace(' ', 'T')}${/[zZ+]/.test(String(ts).slice(10)) ? '' : 'Z'}`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function when(ts) {
  const date = toDate(ts);
  if (!date) return '';
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
