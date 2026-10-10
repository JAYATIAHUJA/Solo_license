import { useState } from 'react';
import { money } from '../../../lib/format.js';

const EMPTY = { order_id: '', customer: '', amount: '' };
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9-]{2,31}$/;

export function StepOrders({ form, set, data }) {
  const [draft, setDraft] = useState(EMPTY);
  const [adding, setAdding] = useState(form.orders.length > 0);
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
      <h1 className="ob-title">Sample orders</h1>
      <p className="ob-sub">The agent needs some orders to refund or credit. Start with our sample set — you can add your own too.</p>

      {existing.length > 0 ? (
        <p className="pl-help">This workspace already has {existing.length} order{existing.length === 1 ? '' : 's'}.</p>
      ) : (
        <label className={`pl-choice ${form.load_sample_orders ? 'is-on' : ''}`}>
          <input type="checkbox" checked={form.load_sample_orders} onChange={(e) => set({ load_sample_orders: e.target.checked })} />
          <span>
            <b>Load sample orders</b>
            <span className="pl-tag">Recommended</span>
            <small>A handful of realistic orders at different prices, so you can try everything right away.</small>
          </span>
        </label>
      )}

      {!adding ? (
        <div><button type="button" className="btn btn-line btn-sm" onClick={() => setAdding(true)}>Add your own order</button></div>
      ) : (
        <form className="ob-order-form" onSubmit={add}>
          <label className="field">
            <span>Order number</span>
            <input className="input" placeholder="ORD-2001" maxLength={32} value={draft.order_id} onChange={(e) => setDraft({ ...draft, order_id: e.target.value })} />
          </label>
          <label className="field">
            <span>Customer</span>
            <input className="input" placeholder="Jane Doe" maxLength={80} value={draft.customer} onChange={(e) => setDraft({ ...draft, customer: e.target.value })} />
          </label>
          <label className="field">
            <span>Amount paid ($)</span>
            <input className="input" type="number" min="0.01" step="0.01" placeholder="35.00" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
          </label>
          <button className="btn btn-line" disabled={!valid}>Add</button>
        </form>
      )}
      {duplicate && <p className="ob-error">That order number is already used.</p>}

      {form.orders.length > 0 && (
        <ul className="ob-orders">
          {form.orders.map((o) => (
            <li key={o.order_id}>
              <span>{o.order_id}</span>
              <span>{o.customer}</span>
              <span>{money(o.amount)}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label={`Remove ${o.order_id}`}
                onClick={() => set({ orders: form.orders.filter((x) => x.order_id !== o.order_id) })}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
