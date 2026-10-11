import { useState } from 'react';
import { StripeFields } from '../../app/components/IntegrationFields.jsx';

/** Where the agent's orders come from. Three ways in, from zero setup to live. */
const SOURCES = [
  {
    id: 'sample',
    title: 'Try it with a sample shop',
    note: '8 realistic orders and 6 customer messages. Nothing to set up - best for a first look.',
    tag: 'Fastest',
  },
  {
    id: 'csv',
    title: 'Upload your orders (CSV)',
    note: 'An export from Shopify, WooCommerce, Gumroad or a spreadsheet. Column names are matched for you.',
  },
  {
    id: 'stripe',
    title: 'Connect Stripe (test mode)',
    note: 'Orders come from your Stripe payments. Refunds and credit really happen in Stripe and are checked there.',
  },
];

/** Count data rows the way the server will: header + non-empty lines. */
const rowCount = (text) => Math.max(0, text.split(/\r?\n/).filter((l) => l.trim()).length - 1);

export function StepOrders({ form, set, data }) {
  const existing = (data.orders || []).length;
  const [fileName, setFileName] = useState('');

  async function readFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    set({ orders_csv: await file.text() });
  }

  return (
    <>
      <h1 className="ob-title">Where are your orders?</h1>
      <p className="ob-sub">
        The agent can only refund or credit orders it knows about. Pick one - you can add the others later from the Orders page.
      </p>
      {existing > 0 && <p className="pl-help">This workspace already has {existing} order{existing === 1 ? '' : 's'}.</p>}

      <div className="pl-choices" role="radiogroup" aria-label="Where orders come from">
        {SOURCES.map((s) => (
          <label key={s.id} className={`pl-choice ${form.orders_source === s.id ? 'is-on' : ''}`}>
            <input type="radio" name="orders_source" checked={form.orders_source === s.id}
              onChange={() => set({ orders_source: s.id, load_sample_orders: s.id === 'sample' })} />
            <span>
              <b>{s.title}</b>
              {s.tag && <span className="pl-tag">{s.tag}</span>}
              <small>{s.note}</small>
            </span>
          </label>
        ))}
      </div>

      {form.orders_source === 'csv' && (
        <section className="ob-section">
          <h2>Your orders file</h2>
          <label className="field">
            <span>CSV file</span>
            <input className="input" type="file" accept=".csv,text/csv" onChange={readFile} />
            <small>Needs at least an order number and an amount. Email and date make the agent smarter: it can find an order from the customer's email and apply your refund window.</small>
          </label>
          {form.orders_csv && (
            <p className="pl-help">{fileName || 'File'} · {rowCount(form.orders_csv)} rows ready to import.</p>
          )}
        </section>
      )}

      {form.orders_source === 'stripe' && (
        <section className="ob-section">
          <h2>Stripe</h2>
          <StripeFields values={form} onChange={set} settings={data.settings} />
          <label className={`pl-choice ${form.stripe_sample ? 'is-on' : ''}`}>
            <input type="checkbox" checked={!!form.stripe_sample} onChange={(e) => set({ stripe_sample: e.target.checked })} />
            <span>
              <b>My test account is empty - create sample payments in it</b>
              <small>Adds 8 paid test charges with customers, so there is something to refund. Test mode only.</small>
            </span>
          </label>
        </section>
      )}
    </>
  );
}

/** Is the step complete? */
export function ordersReady(form, data) {
  if ((data.orders || []).length && !form.orders_source) return true;
  if (form.orders_source === 'sample') return true;
  if (form.orders_source === 'csv') return rowCount(form.orders_csv || '') > 0;
  if (form.orders_source === 'stripe') {
    return /^(sk|rk)_test_[A-Za-z0-9]+$/.test(String(form.stripe_secret_key || '').trim()) || !!data.settings?.has_stripe_secret_key;
  }
  return false;
}
