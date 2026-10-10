import { useState } from 'react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { money } from '../../../lib/format.js';

const EMPTY = { order_id: '', customer: '', amount: '' };
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9-]{2,31}$/;

export function StepOrders({ form, set, data }) {
  const [draft, setDraft] = useState(EMPTY);
  const existing = data.orders || [];
  const id = draft.order_id.trim().toUpperCase();
  const duplicate = Boolean(id) && (
    form.orders.some((o) => o.order_id === id)
    || existing.some((o) => String(o.order_id).toUpperCase() === id)
  );
  const valid = ID_RE.test(id) && draft.customer.trim() && Number(draft.amount) > 0 && !duplicate;

  function add(e) {
    e.preventDefault();
    if (!valid) return;
    set({ orders: [...form.orders, { order_id: id, customer: draft.customer.trim(), amount: Number(draft.amount) }] });
    setDraft(EMPTY);
  }

  return (
    <>
      <h1 className="ob-title serif">Something to <em className="italic">act on.</em></h1>
      <p className="ob-sub">Orders are what the agent refunds or credits against. Every action is checked against its order before it is allowed.</p>

      {existing.length > 0 ? (
        <p className="ob-note">
          <HandIcon name="check" size={14} /> This workspace already has {existing.length} order{existing.length === 1 ? '' : 's'}. Add more below if you like.
        </p>
      ) : (
        <label className="ob-check">
          <input type="checkbox" checked={form.load_sample_orders} onChange={(e) => set({ load_sample_orders: e.target.checked })} />
          <span className="ob-check-box">{form.load_sample_orders && <HandIcon name="check" size={16} />}</span>
          <span>
            <b>Load sample orders</b>
            <small>A small set of realistic orders across price points, so you can try every level right away.</small>
          </span>
        </label>
      )}

      <form className="ob-order-form" onSubmit={add}>
        <label className="field">
          <span>Order id</span>
          <input className="input" placeholder="ORD-2001" maxLength={32} value={draft.order_id} onChange={(e) => setDraft({ ...draft, order_id: e.target.value })} />
        </label>
        <label className="field">
          <span>Customer</span>
          <input className="input" placeholder="Jane Doe" maxLength={80} value={draft.customer} onChange={(e) => setDraft({ ...draft, customer: e.target.value })} />
        </label>
        <label className="field">
          <span>Amount ($)</span>
          <input className="input" type="number" min="0.01" step="0.01" placeholder="35.00" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
        </label>
        <button className="btn btn-line" disabled={!valid}><HandIcon name="plus" size={14} /> Add</button>
      </form>
      {duplicate && <p className="ob-error"><HandIcon name="warn" size={14} /> That order id is already taken.</p>}

      {form.orders.length > 0 && (
        <ul className="ob-orders">
          {form.orders.map((o) => (
            <li key={o.order_id}>
              <code className="mono">{o.order_id}</code>
              <span>{o.customer}</span>
              <span>{money(o.amount)}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label={`Remove ${o.order_id}`}
                onClick={() => set({ orders: form.orders.filter((x) => x.order_id !== o.order_id) })}
              >
                <HandIcon name="cross" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="ob-sub">Orders you add here are saved together with the rest of setup when you finish.</p>
    </>
  );
}
