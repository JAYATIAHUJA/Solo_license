import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, money } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

/** Why a held run can't be signed off right now, or null if it can. */
export function approveBlocker(data, r, taskClass = r.task_class || 'refund') {
  if (data.licenses?.[taskClass]?.quarantined) return 'Restore the license first.';
  const order = data.orders.find((o) => o.order_id === r.order_id);
  const left = order ? (order.remaining ?? order.amount - order.refunded_amount - (order.credit_issued || 0)) : 0;
  if (left + 1e-9 < r.requested_amount) return 'Not enough left on this order.';
  return null;
}

/** Human sign-off on a held draft or an L0 suggestion. Calls onDone(newRunId).
 *  `compact` renders just the button (for inline queues). */
export function ApproveBar({ run: r, taskClass, onDone, compact = false }) {
  const { data, run, busy } = useStore();
  if (r.status !== 'pending_approval' && r.status !== 'suggested') return null;
  const cls = taskClass || r.task_class || 'refund';
  const meta = classMeta(data, cls);
  const blocked = approveBlocker(data, r, cls);
  const held = r.status === 'pending_approval';
  const action = held ? 'Approve & execute' : 'Execute suggestion';
  const go = () => run(() => api.approve(r.id), `${meta.label} executed and verified.`).then((res) => res && onDone?.(res.runs?.[0]?.id));

  if (compact) {
    return (
      <button className="btn btn-ink btn-sm" disabled={busy || !!blocked} onClick={go} title={blocked || `${action}: ${meta.verb} ${money(r.requested_amount)} on ${r.order_id}`}>
        <HandIcon name="check" size={13} /> {held ? 'Approve' : 'Execute'}
      </button>
    );
  }

  return (
    <div className="app-approve">
      <p>
        {held
          ? <>The {meta.label.toLowerCase()} license held this for a human: {meta.verb} <b>{money(r.requested_amount)}</b> on <b>{r.order_id}</b>.</>
          : <>At L0 the agent only suggests. If you agree, execute it — a verified run earns {meta.label.toLowerCase()} credit toward L1.</>}
        {blocked && <> <b className="is-alert">{blocked}</b></>}
      </p>
      <button className="btn btn-ink" disabled={busy || !!blocked} onClick={go}>
        <HandIcon name="check" size={16} /> {action}
      </button>
    </div>
  );
}
