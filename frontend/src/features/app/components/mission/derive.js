/* Pure selectors over the dashboard payload. Everything Mission Control shows
   is computed from server truth here, so components stay presentational. */
import { classKeys, classMeta, toDate } from '../../../../lib/format.js';

const at = (ts) => toDate(ts)?.getTime() ?? 0;

/** One entry per task class with its license, stats, economics and fault. */
export function classCards(data) {
  return classKeys(data).map((key) => ({
    key,
    meta: classMeta(data, key),
    license: data.licenses?.[key] || { level: 0, effective_level: 0, clean_runs: 0, quarantined: false, demoted_from: null },
    stats: data.stats?.by_class?.[key] || {},
    econ: data.economics?.classes?.find((c) => c.task_class === key) || null,
    fault: data.armed_faults?.[key] || 'none',
    ceiling: data.config?.ceilings?.[key] ?? classMeta(data, key).ceiling,
  }));
}

/** "Verified, not trusted": every number is computed, none is configured. */
export function proofMetrics(data) {
  const executedFaults = data.runs.filter((r) => r.executed && r.fault_mode && r.fault_mode !== 'none');
  return {
    executed: data.stats.executed ?? data.runs.filter((r) => r.executed).length,
    faultsInjected: data.stats.faults_injected ?? data.runs.filter((r) => r.fault_mode !== 'none').length,
    caught: data.stats.demotions ?? 0,
    falseSuccesses: executedFaults.filter((r) => r.status !== 'demoted').length,
    paidOut: data.stats.paid_out ?? data.stats.refunded_total ?? 0,
  };
}

/** Events for one class (oldest first) and derived license-card facts. */
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
    lastChangeKind: last?.kind || null,
    lastIncident: lastDemote || null,
    incidentFault: incidentRun?.fault_mode || null,
    sha: committed?.git_sha || null,
    runs: runs.length,
  };
}

/* ---------- trust timeline ---------- */

/** Merge runs and license events of every class into one ordinal sequence and
 *  replay the ladder, so each step knows every class's level at that moment.
 *  Ordinal (not wall-clock) x keeps a fast scripted demo readable. */
export function trustSeries(data, windowSize = 48) {
  const keys = classKeys(data);
  const items = [
    ...data.runs.map((r) => ({ type: 'run', key: r.task_class || 'refund', t: at(r.created_at), anchor: r.id, rank: 0, item: r })),
    ...data.events.map((e) => ({ type: 'event', key: e.task_class || 'refund', t: at(e.created_at), anchor: e.run_id ?? Number.MAX_SAFE_INTEGER, rank: 1, id: e.id, item: e })),
  ].sort((a, b) => a.t - b.t || a.anchor - b.anchor || a.rank - b.rank || (a.id ?? 0) - (b.id ?? 0));

  // Starting level per class: the from_level of its first event, else today.
  const state = {};
  for (const key of keys) {
    const first = data.events.filter((e) => (e.task_class || 'refund') === key).sort((a, b) => a.id - b.id)[0];
    const lic = data.licenses?.[key];
    state[key] = { level: first ? first.from_level : (lic?.level ?? 0), q: false };
  }

  const steps = items.map((it) => {
    if (it.type === 'event') {
      const s = state[it.key] || (state[it.key] = { level: 0, q: false });
      s.level = it.item.to_level;
      s.q = it.item.kind === 'demote' ? true : it.item.kind === 'restore' ? false : s.q;
    }
    const snap = Object.fromEntries(Object.entries(state).map(([k, v]) => [k, { ...v }]));
    return { ...it, snap };
  });

  // Close every line at "now" with the server's current state.
  const now = Object.fromEntries(keys.map((k) => {
    const lic = data.licenses?.[k];
    return [k, { level: lic ? lic.effective_level : state[k]?.level ?? 0, q: !!lic?.quarantined }];
  }));
  const windowed = steps.slice(-windowSize);
  const initial = windowed.length && steps.length > windowed.length
    ? steps[steps.length - windowed.length - 1].snap
    : Object.fromEntries(keys.map((k) => {
      const first = data.events.filter((e) => (e.task_class || 'refund') === k).sort((a, b) => a.id - b.id)[0];
      return [k, { level: first ? first.from_level : now[k].level, q: false }];
    }));
  return { keys, steps: windowed, initial, now, truncated: steps.length > windowed.length };
}
