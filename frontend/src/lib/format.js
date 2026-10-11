export const LEVELS = [
  { id: 0, code: 'L0', name: 'Suggest only', who: 'Human does everything' },
  { id: 1, code: 'L1', name: 'Draft + approve', who: 'Agent drafts, human clicks' },
  { id: 2, code: 'L2', name: 'Auto under ceiling', who: 'Agent acts, human spot-checks' },
  { id: 3, code: 'L3', name: 'Full auto, audited', who: 'Agent acts, audit samples' },
];

export const FAULTS = [
  { id: 'none', name: 'No fault', note: 'Run normally.', catches: null },
  { id: 'quiet_failure', name: 'Quiet failure', note: 'Tool says “done” but writes nothing.', catches: 'state_mismatch' },
  { id: 'policy_violation', name: 'Policy breach', note: 'Agent acts beyond its license.', catches: 'policy_breach' },
  { id: 'skip_verification', name: 'Skipped check', note: 'Executes, then never reads the result back.', catches: 'missing_verification' },
];

export const STATUS = {
  clean: { label: 'Clean', pattern: 'pat-solid' },
  demoted: { label: 'Demoted', pattern: 'pat-hatch', alert: true },
  pending_approval: { label: 'Awaiting approval', pattern: 'pat-dots' },
  approved: { label: 'Approved', pattern: 'pat-none' },
  suggested: { label: 'Suggested', pattern: 'pat-none' },
};

const CURRENCY = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const CURRENCY_WHOLE = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const CURRENCY_COMPACT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 });

/** $1,234.50 - every amount on screen goes through here. */
export const money = (n) => CURRENCY.format(Number(n || 0));
/** $22,500 - for monthly economics, where cents are noise. */
export const moneyWhole = (n) => CURRENCY_WHOLE.format(Math.round(Number(n || 0)));
/** $400K - for tight spaces. */
export const moneyCompact = (n) => CURRENCY_COMPACT.format(Number(n || 0));
export const pct = (n) => `${Math.round(Number(n || 0) * 100)}%`;

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

/** 10 OCT 2026 - license-card style. */
export function stampDate(ts) {
  const date = toDate(ts);
  if (!date) return '-';
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase();
}

export const humanize = (s) => String(s || '').replaceAll('_', ' ');

/** Task-class metadata from the payload, with a safe fallback. */
export function classMeta(data, key) {
  const found = data?.task_classes?.find((c) => c.key === key);
  return found || { key, label: humanize(key), verb: humanize(key), effect_column: 'refunded_amount', ceiling: data?.config?.ceilings?.[key] ?? 0 };
}

/** Every task class the workspace knows, in server order. */
export function classKeys(data) {
  if (data?.task_classes?.length) return data.task_classes.map((c) => c.key);
  return Object.keys(data?.licenses || {});
}

/** Where an LLM intake came from: "llm:gpt-4o" → "LLM · gpt-4o". */
export function sourceLabel(source) {
  if (!source) return '-';
  if (source.startsWith('llm:')) return `LLM · ${source.slice(4)}`;
  if (source === 'deterministic') return 'Deterministic parser';
  return humanize(source);
}
