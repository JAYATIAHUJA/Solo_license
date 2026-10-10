import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const COPY = {
  pending_approval: ['The license held this refund for a human.', 'Approve & execute'],
  suggested: ['At L0 the agent only suggests. If you agree, execute it — a verified run earns credit toward L1.', 'Execute suggestion'],
};

/** Human sign-off on a held draft or an L0 suggestion. Calls onDone(newRunId). */
export function ApproveBar({ run: r, onDone }) {
  const { data, run, busy } = useStore();
  const copy = COPY[r.status];
  if (!copy) return null;
  const order = data.orders.find((o) => o.order_id === r.order_id);
  const left = order ? order.amount - order.refunded_amount : 0;
  const blocked = data.license.quarantined || left + 1e-9 < r.requested_amount;

  return (
    <div className="app-approve">
      <p>{copy[0]} {data.license.quarantined && <b>Restore the license first.</b>}{!data.license.quarantined && blocked && <b>Not enough left to refund on this order.</b>}</p>
      <button
        className="btn btn-ink"
        disabled={busy || blocked}
        onClick={() => run(() => api.approve(r.id), 'Executed and verified.').then((res) => res && onDone?.(res.runs[0].id))}
      >
        <HandIcon name="check" size={16} /> {copy[1]}
      </button>
    </div>
  );
}
