/** Pure helpers for the live coding page: level changes between polls and
 *  the "This was wrong" flag request. */

export const licenseKey = (lic) => `${lic.repo}:${lic.principal || 'main'}:${lic.action_class}`;

/** { "repo:class": level } for one poll's licenses. */
export function levelsOf(licenses) {
  const out = {};
  for (const lic of licenses || []) out[licenseKey(lic)] = lic.level;
  return out;
}

/** { "repo:class": "up" | "down" } for every level that moved since the last
 *  poll. Nothing on the first poll, and nothing for a class seen for the first time. */
export function levelChanges(before, after) {
  const changes = {};
  if (!before) return changes;
  for (const [key, level] of Object.entries(after || {})) {
    const was = before[key];
    if (was == null || was === level) continue;
    changes[key] = level > was ? 'up' : 'down';
  }
  return changes;
}

/** The body for POST /api/coding/flags: one decision or one turn, and why. */
export function flagRequest(target, reason) {
  const hasDecision = target?.decision_id != null;
  const hasTurn = target?.turn_id != null;
  if (hasDecision === hasTurn) throw new Error('Flag a decision or a turn.');
  const why = String(reason ?? '').trim();
  if (!why) throw new Error('Say what was wrong.');
  return hasDecision ? { decision_id: target.decision_id, reason: why } : { turn_id: target.turn_id, reason: why };
}

/** Which decisions and turns a person has already flagged. */
export function flaggedTargets(flags) {
  const decisions = new Set();
  const turns = new Set();
  for (const f of flags || []) {
    if (f.decision_id != null) decisions.add(f.decision_id);
    else if (f.turn_id != null) turns.add(f.turn_id);
  }
  return { decisions, turns };
}
