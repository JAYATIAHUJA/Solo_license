import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { money } from '../../../lib/format.js';
import { pausedNow } from './words.js';
import './activity.css';

/** Why a held job can't be approved right now (plain words), or null if it can. */
export function approveBlocker(data, r, taskClass = r.task_class || 'refund') {
  if (data.licenses?.[taskClass]?.quarantined) return `${pausedNow(data, taskClass)} — resume first`;
  const order = data.orders.find((o) => o.order_id === r.order_id);
  const left = order ? (order.remaining ?? order.amount - order.refunded_amount - (order.credit_issued || 0)) : 0;
  if (left + 1e-9 < r.requested_amount) return `Only ${money(left)} left on this order`;
  return null;
}

function resultText(res) {
  const status = res?.runs?.[0]?.status;
  if (status === 'demoted') return 'A problem was caught — see what happened.';
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

  if (compact) {
    return (
      <button className="btn btn-ink btn-sm" disabled={busy || !!blocked} onClick={go} title={blocked || undefined}>
        {action}
      </button>
    );
  }

  return (
    <div className="act-approve">
      <p>
        {held
          ? 'The agent prepared this and is waiting for your OK.'
          : 'The agent suggests this. If you agree, do it now — each correct job helps it earn more freedom.'}
      </p>
      <div className="pl-actions">
        <button className="btn btn-ink" disabled={busy || !!blocked} onClick={go}>{action}</button>
        {blocked && <span className="act-blocked">{blocked}.</span>}
      </div>
    </div>
  );
}
