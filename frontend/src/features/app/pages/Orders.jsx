import { useRef, useState } from 'react';
import { api, saveText } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { money } from '../../../lib/format.js';
import '../components/plain-form.css';
import '../components/activity.css';

const EMPTY = { order_id: '', customer: '', amount: '' };

const SOURCE = { sample: 'Sample', csv: 'CSV', stripe: 'Stripe', manual: 'Added here' };

/** The orders the agent can work on, and the ways to bring them in or out. */
export function Orders() {
  const { data, run, busy, setToast } = useStore();
  const [draft, setDraft] = useState(EMPTY);
  const [adding, setAdding] = useState(false);
  const [problems, setProblems] = useState([]);
  const file = useRef(null);
  const used = new Set(data.runs.map((r) => r.order_id));
  const stripe = data.settings.stripe_connected;

  async function importFile(e) {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    const text = await f.text();
    const result = await run(() => api.importOrders(text), (r) => `Imported ${r?.import?.added ?? 0} new and updated ${r?.import?.updated ?? 0} orders from ${f.name}.`);
    setProblems(result?.import?.problems || []);
  }

  async function download(fn, name) {
    try {
      saveText(await fn(), name);
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    }
  }

  async function add(e) {
    e.preventDefault();
    const id = draft.order_id.trim().toUpperCase();
    const ok = await run(() => api.addOrder({ ...draft, order_id: id, amount: Number(draft.amount) }), `Order ${id} added.`);
    if (ok) { setDraft(EMPTY); setAdding(false); }
  }

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Orders</h1>
          <p>The orders the agent can refund or credit{stripe ? ' - Stripe orders are refunded in Stripe and checked there.' : '.'}</p>
        </div>
        <div className="pl-actions">
          <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={importFile} />
          <button type="button" className="btn btn-line btn-sm" disabled={busy} onClick={() => file.current?.click()}>Import CSV</button>
          {stripe && (
            <button type="button" className="btn btn-line btn-sm" disabled={busy}
              onClick={() => run(api.syncStripe, (r) => `Stripe: ${r?.import?.added ?? 0} new, ${r?.import?.updated ?? 0} updated.`)}>
              Sync Stripe
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => download(api.exportOrders, 'orders.csv')}>Export orders</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => download(api.exportRuns, 'agent-runs.csv')}>Export agent runs</button>
          {!adding && <button type="button" className="btn btn-ink btn-sm" onClick={() => setAdding(true)}>Add an order</button>}
        </div>
      </header>

      {adding && (
        <form className="pl-card pl-form" onSubmit={add}>
          <h3>Add an order</h3>
          <div className="ord-form">
            <label className="field"><span>Order number</span><input className="input" placeholder="ORD-2001" value={draft.order_id} onChange={(e) => setDraft({ ...draft, order_id: e.target.value })} required minLength={3} maxLength={32} autoFocus /></label>
            <label className="field"><span>Customer</span><input className="input" placeholder="Jane Doe" value={draft.customer} onChange={(e) => setDraft({ ...draft, customer: e.target.value })} required maxLength={80} /></label>
            <label className="field"><span>Amount paid ($)</span><input className="input" type="number" step="0.01" min="0.01" placeholder="35.00" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} required /></label>
            <div className="pl-actions">
              <button className="btn btn-ink" disabled={busy}>Add</button>
              <button type="button" className="btn btn-ghost" onClick={() => { setAdding(false); setDraft(EMPTY); }}>Cancel</button>
            </div>
          </div>
        </form>
      )}

      {problems.length > 0 && (
        <details className="pl-more pl-card" open>
          <summary>{problems.length} row{problems.length === 1 ? ' was' : 's were'} skipped</summary>
          <ul className="pl-small">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </details>
      )}

      {data.orders.length === 0 ? (
        <div className="pl-empty">No orders yet. Add one so the agent has something to work on.</div>
      ) : (
        <div className="ord-wrap">
          <table className="ord-table">
            <thead>
              <tr>
                <th>Order</th><th>Customer</th><th>Paid on</th><th>From</th><th className="num">Amount</th><th className="num">Refunded</th><th className="num">Store credit</th><th className="num">Left to pay out</th><th><span className="ord-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.orders.map((o) => {
                const refunded = Number(o.refunded_amount || 0);
                const credit = Number(o.credit_issued || 0);
                const left = Number(o.remaining ?? o.amount - refunded - credit);
                return (
                  <tr key={o.order_id}>
                    <td className="ord-id">{o.order_id}</td>
                    <td>{o.customer}{o.email && <div className="pl-small pl-muted">{o.email}</div>}</td>
                    <td>{o.ordered_at || <span className="pl-muted">-</span>}</td>
                    <td>{SOURCE[o.source] || o.source}</td>
                    <td className="num">{money(o.amount)}</td>
                    <td className="num">{refunded ? money(refunded) : <span className="pl-muted">-</span>}</td>
                    <td className="num">{credit ? money(credit) : <span className="pl-muted">-</span>}</td>
                    <td className="num">{money(left)}</td>
                    <td className="num">
                      {!used.has(o.order_id) && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm ord-del"
                          disabled={busy}
                          onClick={() => run(() => api.deleteOrder(o.order_id), `Order ${o.order_id} deleted.`)}
                          aria-label={`Delete ${o.order_id}`}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="pl-small pl-muted">Orders the agent has already worked on can't be deleted, so their history stays complete.</p>
    </div>
  );
}
