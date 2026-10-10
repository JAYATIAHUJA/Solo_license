import { useState } from 'react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { money } from '../../../lib/format.js';

const EMPTY = { order_id: '', customer: '', amount: '' };

export function StepOrders({ form, set }) {
  const [draft, setDraft] = useState(EMPTY);
  const valid = /^[A-Za-z0-9][A-Za-z0-9-]{2,31}$/.test(draft.order_id) && draft.customer.trim() && Number(draft.amount) > 0;

  function add(e) {
    e.preventDefault();
    if (!valid) return;
    const order = { order_id: draft.order_id.toUpperCase(), customer: draft.customer.trim(), amount: Number(draft.amount) };
    if (form.custom_orders.some((o) => o.order_id === order.order_id)) return;
    set({ custom_orders: [...form.custom_orders, order] });
    setDraft(EMPTY);
  }

  return (
    <>
      <h1 className="ob-title serif">Something to <em className="italic">refund.</em></h1>
      <label className="ob-check">
        <input type="checkbox" checked={form.load_sample_orders} onChange={(e) => set({ load_sample_orders: e.target.checked })} />
        <span className="ob-check-box">{form.load_sample_orders && <HandIcon name="check" size={16} />}</span>
        <span>
          <b>Load 5 sample orders</b>
          <small>ORD-1001 … ORD-1005, $15 – $120. Good for a first test.</small>
        </span>
      </label>

      <form className="ob-order-form" onSubmit={add}>
        <label className="field"><span>Order id</span><input className="input" placeholder="ORD-2001" value={draft.order_id} onChange={(e) => setDraft({ ...draft, order_id: e.target.value })} /></label>
        <label className="field"><span>Customer</span><input className="input" placeholder="Jane Doe" value={draft.customer} onChange={(e) => setDraft({ ...draft, customer: e.target.value })} /></label>
        <label className="field"><span>Amount ($)</span><input className="input" type="number" min="0.01" step="0.01" placeholder="35.00" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} /></label>
        <button className="btn btn-line" disabled={!valid}><HandIcon name="plus" size={14} /> Add</button>
      </form>

      {form.custom_orders.length > 0 && (
        <ul className="ob-orders">
          {form.custom_orders.map((o) => (
            <li key={o.order_id}>
              <code className="mono">{o.order_id}</code>
              <span>{o.customer}</span>
              <span>{money(o.amount)}</span>
              <button className="btn btn-ghost btn-sm" aria-label={`Remove ${o.order_id}`} onClick={() => set({ custom_orders: form.custom_orders.filter((x) => x.order_id !== o.order_id) })}>
                <HandIcon name="cross" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
