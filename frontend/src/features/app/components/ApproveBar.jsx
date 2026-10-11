import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { money } from '../../../lib/format.js';
import { pausedNow } from './words.js';
import './activity.css';

/** Why a held job can't be approved right now (plain words), or null if it can. */
export function approveBlocker(data, r, taskClass = r.task_class || 'refund') {
  if (data.licenses?.[taskClass]?.quarantined) return `${pausedNow(data, taskClass)} - resume first`;
  const order = data.orders.find((o) => o.order_id === r.order_id);
  const left = order ? (order.remaining ?? order.amount - order.refunded_amount - (order.credit_issued || 0)) : 0;
  if (left + 1e-9 < r.requested_amount) return `Only ${money(left)} left on this order`;
  return null;
}

function resultText(res) {
  const status = res?.runs?.[0]?.status;
  if (status === 'demoted') return 'A problem was caught - see what happened.';
  return 'Done and double-checked.';
}

/** A person's OK on a job the agent prepared ("Approve and run") or only
 *  suggested ("Do it now"). Calls onDone(newRunId). `compact` = button only. */
export function ApproveBar({ run: r, taskClass, onDone, compact = false }) {
  const { data, run, busy } = useStore();
  if (r.status !== 'pending_approval' && r.status !== 'suggested') return null;
  const cls = taskClass || r.task_class || 'refund';
  const blocked = approveBlocker(data, r, cls);
  const held = r.status === 'pending_approval';
  const action = held ? 'Approve and run' : 'Do it now';
  const go = () => run(() => api.approve(r.id), resultText).then((res) => res && onDone?.(res.runs?.[0]?.id));
  const reject = () => run(() => api.reject(r.id), 'Rejected. It counts against this job type, so it needs more proof before more freedom.');

  if (compact) {
    return (
      <span className="pl-actions">
        <button className="btn btn-ink btn-sm" disabled={busy || !!blocked} onClick={go} title={blocked || undefined}>
          {action}
        </button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={reject} title="The agent got this wrong">Reject</button>
      </span>
    );
  }

  return (
    <div className="act-approve">
      <p>
        {held
          ? 'The agent prepared this and is waiting for your OK.'
          : 'The agent suggests this. If you agree, do it now - each double-checked job is evidence toward more freedom.'}
        {' '}If it is wrong, reject it: that counts against the job type.
      </p>
      <div className="pl-actions">
        <button className="btn btn-ink" disabled={busy || !!blocked} onClick={go}>{action}</button>
        <button className="btn btn-line" disabled={busy} onClick={reject}>Reject</button>
        {blocked && <span className="act-blocked">{blocked}.</span>}
      </div>
    </div>
  );
}
