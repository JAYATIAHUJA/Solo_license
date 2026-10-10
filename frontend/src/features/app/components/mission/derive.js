/* Pure selectors over the dashboard payload. Every screen reads server truth
   through these, so pages stay presentational and use the same words. */
import { FAULTS, classKeys, classMeta, money, moneyWhole, toDate } from '../../../../lib/format.js';
import { levelCopy, problem } from '../../../../lib/copy.js';

/** "$50" for whole limits, "$49.50" otherwise. */
export const limitOf = (n) => (Number.isInteger(Number(n)) ? moneyWhole(n) : money(n));

const at = (ts) => toDate(ts)?.getTime() ?? 0;

/** "Refunds", "Store credit" — the name of a job type as a person says it. */
export function jobName(meta) {
  if (!meta) return 'Jobs';
  if (meta.key === 'refund') return 'Refunds';
  return meta.label;
}

/** "Refunds are" / "Store credit is". */
export const jobIs = (name) => `${name} ${/s$/i.test(name) ? 'are' : 'is'}`;

/** One entry per job type with its license, stats, economics and armed practice problem. */
export function classCards(data) {
  return classKeys(data).map((key) => {
    const meta = classMeta(data, key);
    const ceiling = data.config?.ceilings?.[key] ?? meta.ceiling;
    const license = data.licenses?.[key] || { level: 0, effective_level: 0, clean_runs: 0, quarantined: false, demoted_from: null };
    return {
      key,
      meta,
      name: jobName(meta),
      license,
      paused: !!license.quarantined,
      level: license.effective_level ?? 0,
      copy: levelCopy(license.effective_level ?? 0, limitOf(ceiling)),
      stats: data.stats?.by_class?.[key] || {},
      econ: data.economics?.classes?.find((c) => c.task_class === key) || null,
      fault: data.armed_faults?.[key] || 'none',
      ceiling,
    };
  });
}

/** Progress toward the next level, as a sentence. */
export function progressText(card, threshold) {
  if (card.paused) return 'Review what happened to resume it.';
  if (card.level >= 3) return 'Highest level reached.';
  const left = Math.max(1, threshold - (card.license.clean_runs || 0));
  const next = levelCopy(card.level + 1, limitOf(card.ceiling)).short;
  return `${left} more correct job${left === 1 ? '' : 's'} until it moves up to “${next}”.`;
}

/** The run that paused a job type (most recent caught problem). */
export function pausingRun(data, key) {
  return data.runs.find((r) => r.task_class === key && r.status === 'demoted') || null;
}

/** Plain problem copy for a caught run. */
export function problemFor(data, run) {
  if (!run) return problem(null);
  const fromRun = run.problems?.[0] || null;
  const fromPacket = data.packet?.run?.id === run.id ? data.packet?.detections?.[0]?.rule : null;
  const fromFault = FAULTS.find((f) => f.id === run.fault_mode)?.catches;
  return problem(fromRun || fromPacket || fromFault || null);
}

/** Customer name for an order id. */
export function customerOf(data, orderId) {
  return data.orders.find((o) => o.order_id === orderId)?.customer || null;
}

/** "Refund $45.00 for Linus Torvalds (ORD-1005)". */
export function runSentence(data, run) {
  const meta = classMeta(data, run.task_class);
  const who = customerOf(data, run.order_id);
  return `${meta.label} ${money(run.requested_amount)} for ${who ? `${who} (${run.order_id})` : run.order_id}`;
}

/** Runs a person needs to act on: held for approval, plus suggestions on job types that are not paused. */
export function waitingRuns(data) {
  return data.runs.filter((r) => r.status === 'pending_approval'
    || (r.status === 'suggested' && !data.licenses?.[r.task_class]?.quarantined));
}

/** Problems caught before reaching a customer vs. ones that got through. */
export function safetyNumbers(data) {
  const executedFaults = data.runs.filter((r) => r.executed && r.fault_mode && r.fault_mode !== 'none');
  return {
    caught: data.stats.demotions ?? data.runs.filter((r) => r.status === 'demoted').length,
    reached: executedFaults.filter((r) => r.status !== 'demoted').length,
    practice: data.stats.faults_injected ?? data.runs.filter((r) => r.fault_mode && r.fault_mode !== 'none').length,
    done: data.stats.clean_runs ?? data.runs.filter((r) => r.status === 'clean').length,
  };
}

/** Events for one job type (oldest first) and derived license-card facts. */
export function licenseFacts(data, key) {
  const events = data.events.filter((e) => (e.task_class || 'refund') === key).slice().sort((a, b) => a.id - b.id);
  const lastDemote = [...events].reverse().find((e) => e.kind === 'demote');
  const last = events[events.length - 1];
  const committed = [...events].reverse().find((e) => e.git_sha);
  const runs = data.runs.filter((r) => r.task_class === key);
  const firstRun = runs[runs.length - 1];
  const incidentRun = lastDemote?.run_id ? data.runs.find((r) => r.id === lastDemote.run_id) : null;
  return {
    events,
    issued: events[0]?.created_at || firstRun?.created_at || null,
    lastChange: last?.created_at || null,
    lastIncident: lastDemote || null,
    incidentProblem: lastDemote ? problemFor(data, incidentRun || { id: lastDemote.run_id, fault_mode: null }) : null,
    sha: committed?.git_sha || null,
    runs: runs.length,
  };
}

/** Permission level over time for one job type: the starting level, then
 *  every recorded change (oldest first), ending at the current state. */
export function levelHistory(data, key) {
  const events = data.events.filter((e) => (e.task_class || 'refund') === key).slice().sort((a, b) => at(a.created_at) - at(b.created_at) || a.id - b.id);
  const lic = data.licenses?.[key];
  const points = [];
  if (events.length) {
    points.push({ level: events[0].from_level, paused: false, at: null, kind: 'start' });
    for (const e of events) points.push({ level: e.to_level, paused: e.kind === 'demote', at: e.created_at, kind: e.kind, event: e });
  } else {
    points.push({ level: lic?.effective_level ?? 0, paused: !!lic?.quarantined, at: null, kind: 'start' });
  }
  return points;
}
