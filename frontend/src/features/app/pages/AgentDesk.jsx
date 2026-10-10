import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { LEVELS, classMeta, money, pct, sourceLabel } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchUnderline } from '../../../components/sketch/Sketch.jsx';
import { ClassPicker, ClassTag, Empty, PageHeader, Panel } from '../components/Bits.jsx';
import { EvidencePacket } from '../components/EvidencePacket.jsx';
import { FaultSwitch } from '../components/FaultSwitch.jsx';
import { ApproveBar } from '../components/ApproveBar.jsx';

const DEFAULT_REASON = { refund: 'customer refund', store_credit: 'goodwill store credit' };
const amt = (n) => `$${Number(n).toFixed(2)}`;
const remainingOf = (o) => Number(o.remaining ?? o.amount - o.refunded_amount - (o.credit_issued || 0));

/** Example messages built from the live order book, one per task class plus
 *  one the intake should refuse to act on. */
function buildExamples(orders, classes) {
  const open = orders.filter((o) => remainingOf(o) > 0.009);
  if (!open.length) return [];
  const pick = (i) => open[i % open.length];
  const out = [];
  const keys = classes.map((c) => c.key);
  if (keys.includes('refund')) {
    const o = pick(0);
    const value = Math.min(remainingOf(o), Math.max(1, Math.round(remainingOf(o) * 0.5 * 100) / 100));
    out.push({ cls: 'refund', text: `Hi, order ${o.order_id} arrived damaged. Could I get ${amt(value)} back to my card? — ${o.customer}` });
  }
  if (keys.includes('store_credit')) {
    const o = pick(1);
    const value = Math.min(remainingOf(o), Math.max(1, Math.round(remainingOf(o) * 0.4 * 100) / 100));
    out.push({ cls: 'store_credit', text: `${o.customer} here — ${o.order_id} showed up a week late. Happy to take ${amt(value)} as store credit instead of a refund.` });
  }
  for (const key of keys.filter((k) => k !== 'refund' && k !== 'store_credit')) {
    const o = pick(out.length);
    out.push({ cls: key, text: `Order ${o.order_id}: please ${classes.find((c) => c.key === key)?.verb || key} ${amt(Math.min(remainingOf(o), 5))}.` });
  }
  out.push({ cls: null, text: 'I want my money back NOW or I’m calling my lawyer. You know which order.' });
  return out;
}

function IntakeCard({ intake, data }) {
  const meta = classMeta(data, intake.task_class || 'refund');
  const conf = intake.confidence;
  return (
    <div className={`mc-intake ${intake.needs_human ? 'is-flagged' : ''}`}>
      <div className="mc-intake-top">
        <span className="mono muted">Understood as</span>
        <span className="mc-tag mono">{intake.source === 'manual' ? 'Manual entry' : sourceLabel(intake.source)}</span>
      </div>
      <p className="serif mc-intake-line">
        {meta.label} <SketchUnderline key={intake.run_id ?? intake.order_id ?? 'x'}><b>{intake.amount != null ? money(intake.amount) : '—'}</b></SketchUnderline> on{' '}
        <b>{intake.order_id || 'unknown order'}</b>
      </p>
      {intake.reason && <span className="muted app-small">“{intake.reason}”</span>}
      <dl className="mc-intake-grid">
        <div><dt className="app-kicker">Detected action</dt><dd><ClassTag label={meta.label} /></dd></div>
        {conf != null && (
          <div>
            <dt className="app-kicker">Confidence</dt>
            <dd className="mc-conf">
              <span className="mc-conf-bar" aria-hidden="true"><motion.i initial={{ width: 0 }} animate={{ width: pct(conf) }} transition={{ duration: 0.7 }} className={conf < 0.5 ? 'pat-hatch' : 'pat-solid'} /></span>
              <span className="mono">{pct(conf)}</span>
            </dd>
          </div>
        )}
        <div><dt className="app-kicker">Source</dt><dd className="mono">{intake.source === 'manual' ? 'operator' : intake.source}</dd></div>
      </dl>
      {intake.needs_human && (
        <p className="mc-flagged"><HandIcon name="flag" size={16} /> <span><b>Flagged for a human.</b> The intake judged this ambiguous or unsafe, so the agent did not act.</span></p>
      )}
    </div>
  );
}

export function AgentDesk() {
  const { data, run, busy } = useStore();
  const [params, setParams] = useSearchParams();
  const classes = useMemo(() => (data.task_classes || []).map((c) => ({ key: c.key, label: c.label, verb: c.verb })), [data.task_classes]);
  const [mode, setMode] = useState('message');
  const [message, setMessage] = useState(() => params.get('message') || '');
  const [manual, setManual] = useState({ task_class: classes[0]?.key || 'refund', order_id: '', amount: '', reason: DEFAULT_REASON[classes[0]?.key] || 'customer request' });
  const [intake, setIntake] = useState(null);

  const open = data.orders.filter((o) => remainingOf(o) > 0.009);
  const examples = useMemo(() => buildExamples(data.orders, classes), [data.orders, classes]);
  const welcome = params.get('welcome') === '1';
  const manualMeta = classMeta(data, manual.task_class);
  const manualLicense = data.licenses?.[manual.task_class];
  const faultClass = intake?.task_class || manual.task_class;

  async function submitMessage(e) {
    e.preventDefault();
    const result = await run(() => api.intake(message.trim()), (r) => (r.intake?.error || r.intake?.needs_human ? null : `${classMeta(r, r.intake?.task_class).label}: agent finished the run.`));
    if (result?.intake) {
      setIntake(result.intake);
      if (!result.intake.error && !result.intake.needs_human) setMessage('');
    }
  }

  async function submitManual(e) {
    e.preventDefault();
    const body = { order_id: manual.order_id, reason: manual.reason || DEFAULT_REASON[manual.task_class] || 'customer request', task_class: manual.task_class };
    if (manual.amount !== '') body.amount = Number(manual.amount);
    const result = await run(() => api.runAction(body), `${manualMeta.label}: run complete.`);
    if (result) {
      setIntake({
        task_class: manual.task_class, order_id: body.order_id, amount: body.amount ?? result.packet?.run?.requested_amount ?? null,
        reason: body.reason, source: 'manual', run_id: result.packet?.run?.id ?? result.runs?.[0]?.id,
      });
    }
  }

  const packet = intake?.run_id && data.packet?.run?.id === intake.run_id ? data.packet : null;

  return (
    <>
      <PageHeader eyebrow="Agent desk" title={<>Hand it a <em className="italic">customer.</em></>}>
        Paste what the customer wrote. The agent works out the action ({classes.map((c) => c.label.toLowerCase()).join(' or ')}), the order and the amount, checks that class’s license, and acts only as far as it’s allowed.
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
              <button role="tab" aria-selected={mode === 'manual'} className={mode === 'manual' ? 'is-on' : ''} onClick={() => setMode('manual')}><HandIcon name="receipt" size={14} /> Manual action</button>
            </div>

            {open.length === 0 ? (
              <Empty icon="receipt" title="Nothing left to pay out" action={<Link to="/app/orders" className="btn btn-ink btn-sm">Add an order</Link>}>
                Every order is fully refunded or credited. Add an order or reset the sample data in Settings.
              </Empty>
            ) : mode === 'message' ? (
              <form onSubmit={submitMessage} className="app-form">
                <textarea className="input" rows={5} placeholder="Paste a customer email or chat message…" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} aria-label="Customer message" />
                <div className="app-examples">
                  <span className="mono muted">Try one — built from your open orders</span>
                  {examples.map((ex) => (
                    <button type="button" key={ex.text} className="app-example mc-example" onClick={() => setMessage(ex.text)}>
                      <span className={`mc-tag mono ${ex.cls ? '' : 'is-ghost'}`}>{ex.cls ? classMeta(data, ex.cls).label : 'should be flagged'}</span>
                      <span>{ex.text}</span>
                    </button>
                  ))}
                </div>
                <button className="btn btn-ink" disabled={busy || message.trim().length < 3}>
                  {busy ? 'Agent working…' : 'Run agent'} <HandIcon name="arrow-right" size={16} />
                </button>
              </form>
            ) : (
              <form onSubmit={submitManual} className="app-form app-form-grid">
                <div className="field app-span-2">
                  <span>Action</span>
                  <ClassPicker
                    classes={classes}
                    value={manual.task_class}
                    onChange={(k) => setManual({ ...manual, task_class: k, reason: Object.values(DEFAULT_REASON).includes(manual.reason) ? DEFAULT_REASON[k] || manual.reason : manual.reason })}
                  />
                  <small>
                    {manualLicense?.quarantined
                      ? <span className="is-alert">{manualMeta.label} is quarantined — this run will only be suggested.</span>
                      : <>{manualMeta.label} license: <b>L{manualLicense?.effective_level ?? 0} · {LEVELS[manualLicense?.effective_level ?? 0].name}</b> · auto ≤ {money(data.config?.ceilings?.[manual.task_class] ?? manualMeta.ceiling)}</>}
                  </small>
                </div>
                <label className="field">
                  <span>Order</span>
                  <select className="input" value={manual.order_id} onChange={(e) => setManual({ ...manual, order_id: e.target.value })} required>
                    <option value="">Choose…</option>
                    {open.map((o) => (
                      <option key={o.order_id} value={o.order_id}>{o.order_id} · {o.customer} · {money(remainingOf(o))} left</option>
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
                <button className="btn btn-ink" disabled={busy || !manual.order_id}>Run {manualMeta.label.toLowerCase()} <HandIcon name="play" size={14} /></button>
              </form>
            )}
          </Panel>

          <FaultSwitch taskClass={faultClass} />
        </div>

        <Panel title="What the agent did" icon="eye">
          {!intake ? (
            <Empty icon="spark" title="Waiting for a request">The parsed request, the license decision, the read-back and every step of the trace show up here.</Empty>
          ) : (
            <div className="app-result">
              <IntakeCard intake={intake} data={data} />
              {intake.error && !intake.needs_human && <p className="app-error"><HandIcon name="warn" size={16} /> {intake.error}</p>}
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
