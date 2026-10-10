import { HandIcon } from '../../../../components/icons/HandIcon.jsx';

/** What is wired up, at a glance: neatlogs, the model, the git ledger, alerts.
 *  On = solid square, off = outline (pattern, not colour). */
export function StatusChips({ observability, compact = false }) {
  if (!observability) return null;
  const { neatlogs = {}, llm = {}, ledger = {}, alerts = {} } = observability;
  const model = llm.enabled && llm.model && llm.model !== 'deterministic' ? `${llm.label} · ${llm.model}` : llm.label || 'Built-in rules';
  const chips = [
    {
      id: 'neatlogs',
      on: !!neatlogs.enabled,
      label: 'neatlogs',
      value: neatlogs.enabled ? 'connected' : 'local only',
      href: neatlogs.enabled && neatlogs.app_url ? neatlogs.app_url : null,
      title: neatlogs.enabled ? `Streaming traces to project ${neatlogs.project || ''}` : 'Traces stay in the local database. Add a neatlogs key in Settings to stream them.',
    },
    { id: 'llm', on: !!llm.enabled, label: 'model', value: model, title: llm.enabled ? 'Intake + plans by this model' : 'Deterministic parser — no API key needed' },
    { id: 'ledger', on: (ledger.commits ?? 0) > 0, label: 'ledger', value: `${ledger.commits ?? 0} commit${ledger.commits === 1 ? '' : 's'}`, title: ledger.repo ? `git repo: ${ledger.repo}` : 'Git ledger' },
    { id: 'alerts', on: !!alerts.enabled, label: 'alerts', value: alerts.enabled ? 'on' : 'off', title: alerts.enabled ? 'Demotions post to your webhook' : 'No alert webhook configured' },
  ];

  return (
    <ul className={`mc-chips ${compact ? 'is-compact' : ''}`} aria-label="Integrations">
      {chips.map((c) => {
        const body = (
          <>
            <i className={c.on ? 'pat-solid' : 'pat-none'} aria-hidden="true" />
            <span className="mc-chip-k">{c.label}</span>
            <span className="mc-chip-v">{c.value}</span>
            {c.href && <HandIcon name="external" size={11} />}
          </>
        );
        return (
          <li key={c.id} title={c.title}>
            {c.href ? <a className="mc-chip is-link" href={c.href} target="_blank" rel="noreferrer">{body}</a> : <span className="mc-chip">{body}</span>}
          </li>
        );
      })}
    </ul>
  );
}
