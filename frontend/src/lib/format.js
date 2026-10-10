export const LEVELS = [
  { id: 0, code: 'L0', name: 'Suggest only', who: 'Human does everything' },
  { id: 1, code: 'L1', name: 'Draft + approve', who: 'Agent drafts, human clicks' },
  { id: 2, code: 'L2', name: 'Auto under ceiling', who: 'Agent acts, human spot-checks' },
  { id: 3, code: 'L3', name: 'Full auto, audited', who: 'Agent acts, audit samples' },
];

export const FAULTS = [
  { id: 'none', name: 'No fault', note: 'Run normally.' },
  { id: 'quiet_failure', name: 'Quiet failure', note: 'Tool says “done” but writes nothing.' },
  { id: 'policy_violation', name: 'Policy breach', note: 'Agent acts beyond its license.' },
];

export const STATUS = {
  clean: { label: 'Clean', pattern: 'pat-solid' },
  demoted: { label: 'Demoted', pattern: 'pat-hatch', alert: true },
  pending_approval: { label: 'Awaiting approval', pattern: 'pat-dots' },
  approved: { label: 'Approved', pattern: 'pat-none' },
  suggested: { label: 'Suggested', pattern: 'pat-none' },
};

export const money = (n) => `$${Number(n || 0).toFixed(2)}`;

export function when(ts) {
  if (!ts) return '';
  const date = new Date(`${ts.replace(' ', 'T')}Z`);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
