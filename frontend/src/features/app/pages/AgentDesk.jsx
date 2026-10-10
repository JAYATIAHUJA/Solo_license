import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { money } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchUnderline } from '../../../components/sketch/Sketch.jsx';
import { Empty, PageHeader, Panel } from '../components/Bits.jsx';
import { EvidencePacket } from '../components/EvidencePacket.jsx';
import { FaultSwitch } from '../components/FaultSwitch.jsx';
import { ApproveBar } from '../components/ApproveBar.jsx';

const TEMPLATES = [
  (o) => `Hi, my order ${o.order_id} arrived damaged. Could I get my $${Number(o.amount).toFixed(2)} back? — ${o.customer}`,
  (o) => `Order ${o.order_id}: charged twice, please refund $${(Number(o.amount) / 2).toFixed(2)}.`,
  (o) => `${o.customer} here. Never received ${o.order_id}, want a full refund.`,
];

export function AgentDesk() {
  const { data, run, busy } = useStore();
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState('message');
  const [message, setMessage] = useState(() => params.get('message') || '');
  const [manual, setManual] = useState({ order_id: '', amount: '', reason: 'customer refund' });
  const [intake, setIntake] = useState(null);

  const refundable = data.orders.filter((o) => o.amount - o.refunded_amount > 0.001);
  const examples = useMemo(() => refundable.slice(0, 3).map((o, i) => TEMPLATES[i % TEMPLATES.length](o)), [refundable]);
  const welcome = params.get('welcome') === '1';

  async function submitMessage(e) {
    e.preventDefault();
    const result = await run(() => api.intake(message.trim()), (r) => (r.intake.error ? null : 'Agent finished the run.'));
    if (result) {
      setIntake(result.intake);
      if (!result.intake.error) setMessage('');
    }
  }

  async function submitManual(e) {
    e.preventDefault();
    const body = { order_id: manual.order_id, reason: manual.reason || 'customer refund' };
    if (manual.amount !== '') body.amount = Number(manual.amount);
    const result = await run(() => api.refund(body), 'Run complete.');
    if (result) setIntake({ order_id: body.order_id, amount: body.amount ?? null, reason: body.reason, source: 'manual', run_id: result.runs[0]?.id });
  }

  const packet = intake?.run_id && data.packet?.run?.id === intake.run_id ? data.packet : null;

  return (
    <>
      <PageHeader eyebrow="Agent desk" title={<>Hand it a <em className="italic">refund.</em></>}>
        Paste what the customer wrote. The agent finds the order and amount, checks its license, and acts only as far as it’s allowed.
      </PageHeader>

      <AnimatePresence>
        {welcome && (
          <motion.div className="app-welcome" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <p className="hand">You’re set up. Try an example below — then arm a fault and watch it get caught.</p>
            <button className="btn btn-ghost btn-sm" onClick={() => setParams({})} aria-label="Dismiss"><HandIcon name="cross" size={14} /></button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="app-cols app-cols-desk">
        <div className="app-col">
          <Panel className="app-composer" tone="raised">
            <div className="app-tabs" role="tablist">
              <button role="tab" aria-selected={mode === 'message'} className={mode === 'message' ? 'is-on' : ''} onClick={() => setMode('message')}><HandIcon name="message" size={14} /> Customer message</button>
              <button role="tab" aria-selected={mode === 'manual'} className={mode === 'manual' ? 'is-on' : ''} onClick={() => setMode('manual')}><HandIcon name="receipt" size={14} /> Manual</button>
            </div>

            {refundable.length === 0 ? (
              <Empty icon="receipt" title="No refundable orders" action={<Link to="/app/orders" className="btn btn-ink btn-sm">Add an order</Link>}>
                Every order is fully refunded. Add an order or reset the sample data in Settings.
              </Empty>
            ) : mode === 'message' ? (
              <form onSubmit={submitMessage} className="app-form">
                <textarea className="input" rows={5} placeholder="Paste a customer email or chat message…" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} />
                <div className="app-examples">
                  <span className="mono muted">Try</span>
                  {examples.map((ex) => (
                    <button type="button" key={ex} className="app-example" onClick={() => setMessage(ex)}>{ex}</button>
                  ))}
                </div>
                <button className="btn btn-ink" disabled={busy || message.trim().length < 3}>
                  {busy ? 'Agent working…' : 'Run agent'} <HandIcon name="arrow-right" size={16} />
                </button>
              </form>
            ) : (
              <form onSubmit={submitManual} className="app-form app-form-grid">
                <label className="field">
                  <span>Order</span>
                  <select className="input" value={manual.order_id} onChange={(e) => setManual({ ...manual, order_id: e.target.value })} required>
                    <option value="">Choose…</option>
                    {refundable.map((o) => (
                      <option key={o.order_id} value={o.order_id}>{o.order_id} · {o.customer} · {money(o.amount - o.refunded_amount)} left</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Amount ($)</span>
                  <input className="input" type="number" step="0.01" min="0" placeholder="Full remaining" value={manual.amount} onChange={(e) => setManual({ ...manual, amount: e.target.value })} />
                </label>
                <label className="field app-span-2">
                  <span>Reason</span>
                  <input className="input" value={manual.reason} onChange={(e) => setManual({ ...manual, reason: e.target.value })} maxLength={140} />
                </label>
                <button className="btn btn-ink" disabled={busy || !manual.order_id}>Run <HandIcon name="play" size={14} /></button>
              </form>
            )}
          </Panel>

          <FaultSwitch />
        </div>

        <Panel title="What the agent did" icon="eye">
          {!intake ? (
            <Empty icon="spark" title="Waiting for a request">The result, the plan and every step of the trace show up here.</Empty>
          ) : (
            <div className="app-result">
              <div className="app-parsed">
                <span className="mono muted">Understood as · {intake.source}</span>
                <p className="serif">
                  Refund <SketchUnderline key={intake.run_id ?? 'x'}><b>{intake.amount != null ? money(intake.amount) : '—'}</b></SketchUnderline> on{' '}
                  <b>{intake.order_id || 'unknown order'}</b>
                </p>
                <span className="muted">“{intake.reason}”</span>
              </div>
              {intake.error && <p className="app-error"><HandIcon name="warn" size={16} /> {intake.error}</p>}
              {packet && (
                <>
                  <EvidencePacket packet={packet} />
                  <ApproveBar run={packet.run} onDone={(id) => setIntake({ ...intake, run_id: id })} />
                </>
              )}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
