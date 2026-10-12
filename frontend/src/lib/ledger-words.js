/** Wording for the permission history. */

/** "human:jayati" -> "Jayati"; the gate itself -> "Solo License". */
export function personName(actorId) {
  if (!actorId) return '';
  const id = String(actorId);
  if (id.startsWith('system')) return 'Solo License';
  const raw = id.includes(':') ? id.split(':').slice(1).join(':') : id;
  const name = raw.replace(/[-_.]+/g, ' ').trim();
  return name ? name.replace(/\b\w/g, (c) => c.toUpperCase()) : 'Someone';
}

/** Why a person flagged it. The gate stores "<actor_id>: <reason>". */
export function flagReason(e) {
  const reason = String(e.reason ?? '');
  const prefix = `${e.actor_id}: `;
  return (e.actor_id && reason.startsWith(prefix) ? reason.slice(prefix.length) : reason).trim();
}

/** "Jayati flagged file-edit in shop as wrong — back to L0". */
export function flagSentence(e) {
  const [cls, repo] = String(e.task_class || '').split('@');
  const who = personName(e.actor_id) || 'Someone';
  return `${who} flagged ${cls}${repo ? ` in ${repo}` : ''} as wrong — back to L${e.to_level ?? 0}`;
}
