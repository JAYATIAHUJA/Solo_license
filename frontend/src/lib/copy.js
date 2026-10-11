/** Plain-language vocabulary for the app. Every screen describes the agent with
 *  these words, so a first-time user never has to learn internal terms like
 *  "L2", "quarantine" or "state_mismatch". Technical names stay available in
 *  `tech` for tooltips and the "details" disclosures only. */

/** What the agent may do on its own, per level. `{limit}` = the class's $ cap. */
export const LEVEL_COPY = [
  {
    id: 0,
    short: 'Suggests only',
    long: 'Suggests what to do. You do it.',
    tech: 'L0',
  },
  {
    id: 1,
    short: 'Needs your OK',
    long: 'Prepares each one. You approve with one click.',
    tech: 'L1',
  },
  {
    id: 2,
    short: 'Works alone up to {limit}',
    long: 'Handles anything up to {limit} by itself. Bigger ones wait for your OK.',
    tech: 'L2',
  },
  {
    id: 3,
    short: 'Works alone',
    long: 'Handles everything by itself. You can review afterwards.',
    tech: 'L3',
  },
];

export function levelCopy(level, limit) {
  const entry = LEVEL_COPY[Math.max(0, Math.min(3, Number(level) || 0))];
  const fill = (s) => s.replace('{limit}', limit);
  return { ...entry, short: fill(entry.short), long: fill(entry.long) };
}

/** Run outcomes, in the words a user would use. */
export const OUTCOME = {
  clean: { label: 'Done', tone: 'ok', sentence: 'done and double-checked' },
  demoted: { label: 'Problem caught', tone: 'bad', sentence: 'stopped - a problem was caught' },
  pending_approval: { label: 'Waiting for you', tone: 'wait', sentence: 'waiting for your OK' },
  suggested: { label: 'Suggestion', tone: 'wait', sentence: 'suggested for you to do' },
  approved: { label: 'Approved', tone: 'muted', sentence: 'approved by a person' },
};

export const outcome = (status) => OUTCOME[status] || { label: status, tone: 'muted', sentence: status };

/** What each safety check means, for people. */
export const PROBLEMS = {
  state_mismatch: {
    title: 'The tool said “done”, but nothing changed',
    explain: 'We re-checked the order after the agent acted and the money had not moved.',
  },
  policy_breach: {
    title: 'The agent went beyond its permission',
    explain: 'It tried to act on its own on something it was only allowed to prepare.',
  },
  missing_verification: {
    title: 'The result was never double-checked',
    explain: 'The agent acted but skipped re-reading the order to confirm it.',
  },
  duplicate_action: {
    title: 'The same action ran twice',
    explain: 'An identical request had already been carried out.',
  },
};

export const problem = (rule) => PROBLEMS[rule] || { title: String(rule || 'Problem caught').replaceAll('_', ' '), explain: '' };

/** Practice problems the user can trigger to see the safety net work. */
export const PRACTICE = [
  { id: 'none', title: 'No practice problem', explain: 'The next action runs normally.' },
  { id: 'quiet_failure', title: 'Tool says done, does nothing', explain: 'Shows how a silent failure gets caught.' },
  { id: 'policy_violation', title: 'Agent oversteps its permission', explain: 'Shows what happens if the agent acts without approval.' },
];

/** One-line explanation of the product, reused on empty states and help. */
export const ONE_LINER = 'Your AI agent starts by asking permission. Each time it does a job correctly it earns more freedom - and the moment something goes wrong it is paused until you check.';
