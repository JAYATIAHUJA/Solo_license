/** Plain-language helpers for the Activity, Permission history and run detail
 *  screens. Built on lib/copy.js so every screen uses the same words. */
import { levelCopy, problem } from '../../../lib/copy.js';
import { classMeta, money, moneyWhole } from '../../../lib/format.js';

/** "demo:jayati" → "Jayati"; system actors → "Solo License". */
export function personName(actorId) {
  if (!actorId) return '';
  const id = String(actorId);
  if (id.startsWith('system')) return 'Solo License';
  const raw = id.includes(':') ? id.split(':').slice(1).join(':') : id;
  const name = raw.replace(/[-_.]+/g, ' ').trim();
  return name ? name.replace(/\b\w/g, (c) => c.toUpperCase()) : 'Someone';
}

/** The job type as a group noun: "Refunds", "Store credit". */
export function jobsName(data, key) {
  if (key === 'refund') return 'Refunds';
  if (key === 'store_credit') return 'Store credit';
  return classMeta(data, key).label;
}

const isPlural = (data, key) => /s$/i.test(jobsName(data, key));

/** "Refunds were paused" / "Store credit was paused". */
export const pausedSentence = (data, key) => `${jobsName(data, key)} ${isPlural(data, key) ? 'were' : 'was'} paused`;
export const pausedNow = (data, key) => `${jobsName(data, key)} ${isPlural(data, key) ? 'are' : 'is'} paused`;

/** Whole dollars where possible: "$50", otherwise "$12.50". */
export function shortMoney(n) {
  const v = Number(n || 0);
  return Number.isInteger(v) ? moneyWhole(v) : money(v);
}

/** The $ limit a job type may handle alone at "Works alone up to …". */
export function limitText(data, key) {
  const ceiling = data?.config?.ceilings?.[key] ?? classMeta(data, key).ceiling;
  return shortMoney(ceiling);
}

export const levelWords = (data, key, level) => levelCopy(level, limitText(data, key));

/** How the double-check describes the order column for this job type. */
export function effectWord(key) {
  if (key === 'refund') return 'refunded';
  if (key === 'store_credit') return 'store credit issued';
  return 'paid out';
}

/** "most the agent may refund" / "give as store credit". */
export function limitVerb(key) {
  if (key === 'refund') return 'refund';
  if (key === 'store_credit') return 'give as store credit';
  return 'pay out';
}

export function customerOf(data, orderId) {
  return data?.orders?.find((o) => o.order_id === orderId)?.customer || '';
}

/** "Refund $40.00 for Grace Hopper (ORD-1002)". */
export function runSentence(data, run, customer) {
  const who = customer ?? customerOf(data, run.order_id);
  const amount = money(run.requested_amount);
  const tail = who ? `for ${who} (${run.order_id})` : `on ${run.order_id}`;
  if (run.task_class === 'store_credit') return `${amount} store credit ${tail}`;
  if (run.task_class === 'refund' || !run.task_class) return `Refund ${amount} ${tail}`;
  return `${classMeta(data, run.task_class).label} ${amount} ${tail}`;
}

export const isPractice = (run) => Boolean(run?.fault_mode && run.fault_mode !== 'none');

/** Guess the safety check behind a recorded pause reason (events carry only the message). */
export function ruleFromReason(reason = '') {
  const r = String(reason);
  if (/moved|state mismatch/i.test(r)) return 'state_mismatch';
  if (/without verifying|verif/i.test(r)) return 'missing_verification';
  if (/idempotency|duplicate/i.test(r)) return 'duplicate_action';
  if (/only authori[sz]ed|license only|policy/i.test(r)) return 'policy_breach';
  return null;
}

export function problemFromReason(reason) {
  const rule = ruleFromReason(reason);
  return rule ? problem(rule) : null;
}
