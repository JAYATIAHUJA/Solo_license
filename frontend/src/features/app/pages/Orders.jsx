import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, money } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Empty, PageHeader, Panel } from '../components/Bits.jsx';

const EMPTY = { order_id: '', customer: '', amount: '' };

export function Orders() {
  const { data, run, busy } = useStore();
  const [draft, setDraft] = useState(EMPTY);
  const [query, setQuery] = useState('');
  const used = new Set(data.runs.map((r) => r.order_id));
  const orders = data.orders.filter((o) => `${o.order_id} ${o.customer}`.toLowerCase().includes(query.toLowerCase()));
  const columns = (data.task_classes || []).map((c) => c.effect_column).filter(Boolean);
  const refundLabel = classMeta(data, 'refund').label;
  const creditLabel = classMeta(data, 'store_credit').label;

  async function add(e) {
    e.preventDefault();
    const ok = await run(() => api.addOrder({ ...draft, amount: Number(draft.amount) }), `${draft.order_id.toUpperCase()} added.`);
    if (ok) setDraft(EMPTY);
  }

  return (
    <>
      <PageHeader eyebrow="Orders" title={<>The agent’s <em className="italic">real world.</em></>}>
        {(columns.length ? columns : ['refunded_amount']).map((c, i, all) => (
          <span key={c}><code className="mono">{c}</code>{i < all.length - 1 ? ' and ' : ''}</span>
        ))}{' '}
        are the only proof an action happened. The verifier reads them back after every run.
      </PageHeader>

      <Panel title="Add an order" icon="plus">
        <form className="app-order-form" onSubmit={add}>
          <label className="field"><span>Order id</span><input className="input" placeholder="ORD-2001" value={draft.order_id} onChange={(e) => setDraft({ ...draft, order_id: e.target.value })} required minLength={3} maxLength={32} /></label>
          <label className="field"><span>Customer</span><input className="input" placeholder="Jane Doe" value={draft.customer} onChange={(e) => setDraft({ ...draft, customer: e.target.value })} required maxLength={80} /></label>
          <label className="field"><span>Amount ($)</span><input className="input" type="number" step="0.01" min="0.01" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} required /></label>
          <button className="btn btn-ink" disabled={busy}><HandIcon name="plus" size={14} /> Add order</button>
        </form>
      </Panel>

      <Panel
        title={`${data.orders.length} orders`}
        icon="receipt"
        className="app-block mc-block"
        aside={(
          <label className="app-search">
            <HandIcon name="search" size={14} />
            <input placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search orders" />
          </label>
        )}
      >
        <div className="mc-save-legend app-small">
          <span><i className="pat-solid" /> {refundLabel.toLowerCase()}</span>
          <span><i className="pat-hatch" /> {creditLabel.toLowerCase()}</span>
          <span><i className="pat-none mc-swatch-line" /> remaining</span>
        </div>
        {orders.length === 0 ? <Empty icon="receipt" title={query ? 'No matches' : 'No orders yet'}>Add one above.</Empty> : (
          <div className="mc-table-wrap">
            <table className="app-table">
              <thead><tr><th>Order</th><th>Customer</th><th className="num">Total</th><th className="num">{refundLabel}</th><th className="num">{creditLabel}</th><th>Remaining</th><th>Status</th><th /></tr></thead>
              <tbody>
                {orders.map((o) => {
                  const refunded = Number(o.refunded_amount || 0);
                  const credit = Number(o.credit_issued || 0);
                  const left = Number(o.remaining ?? o.amount - refunded - credit);
                  const share = (n) => `${Math.max(0, Math.min(100, (n / (o.amount || 1)) * 100))}%`;
                  return (
                    <tr key={o.order_id}>
                      <td className="mono">{o.order_id}</td>
                      <td>{o.customer}</td>
                      <td className="num">{money(o.amount)}</td>
                      <td className="num">{refunded ? money(refunded) : <span className="muted">—</span>}</td>
                      <td className="num">{credit ? money(credit) : <span className="muted">—</span>}</td>
                      <td>
                        <span className="app-meter mc-meter" title={`${money(refunded)} refunded · ${money(credit)} credit · ${money(left)} left`}>
                          <i className="pat-solid" style={{ width: share(refunded) }} />
                          <i className="pat-hatch" style={{ width: share(credit) }} />
                        </span>
                        {money(left)}
                      </td>
                      <td className="mono">{o.status}</td>
                      <td className="app-row-actions">
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled={busy || used.has(o.order_id)}
                          title={used.has(o.order_id) ? 'Has runs on record' : 'Delete'}
                          onClick={() => run(() => api.deleteOrder(o.order_id), `${o.order_id} deleted.`)}
                          aria-label={`Delete ${o.order_id}`}
                        >
                          <HandIcon name="trash" size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
