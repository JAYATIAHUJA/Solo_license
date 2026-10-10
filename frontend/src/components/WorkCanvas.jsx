import React from 'react';
import { FAULT_MODES, LICENSE_LEVELS } from '../constants.js';

export function WorkCanvas({ data, packet, orderId, fault, busy, condensed, onOrderChange, onFaultChange, onRun }) {
  const selectedOrder = data.orders.find((order) => order.order_id === orderId);
  const level = data.license.effective_level;
  const progress = data.license.quarantined ? 'Review needed' : level === 3 ? 'Post-hoc audit' : `${data.license.clean_runs}/${data.config.promotion_clean_runs} clean runs`;
  return <main className="flow-canvas">
    <div className="flow-header"><span>Autonomy dial</span><span className="tab active">Live run</span></div>
    <section className="autonomy-card">
      <div className="autonomy-label"><span>Task class</span><strong>Refund</strong><em>{progress}</em></div>
      <div className="level-track">{LICENSE_LEVELS.map(([name, label], index) => <div className={`level-node ${index === level ? 'active' : ''} ${data.license.quarantined && index === 0 ? 'alert' : ''}`} key={name}><i>{name}</i><strong>{label}</strong></div>)}</div>
      <p>{data.license.quarantined ? `The last detection moved this task from L${data.license.demoted_from ?? 0} to L0. Human review is required to restore it.` : 'The worker checks this level before it plans, executes, or verifies any side effect.'}</p>
    </section>
    {!condensed && <section className="activity-stream">
      <div className="stream-prompt">Run a real refund. The result appears here with its verified side effect.</div>
      <div className="stream-line"><i /> Reading current license <span>›</span></div><div className="stream-line"><i /> Planning within authority <span>›</span></div><div className="stream-line"><i /> Verifying SQLite after execution <span>›</span></div>
      {packet && <div className="stream-summary"><span>Latest evidence</span><strong>{packet.detections.length ? 'Detection recorded' : 'Verified clean'}</strong><p>Before ${Number(packet.before_refunded).toFixed(2)} · after ${Number(packet.after_refunded).toFixed(2)} · intended ${Number(packet.intended_delta).toFixed(2)}</p></div>}
    </section>}
    <section className="run-composer">
      <div className="composer-tags"><span>Refund</span>{fault !== 'none' && <span className="fault-tag">{fault.replace('_', ' ')}</span>}</div>
      <label>Order<select value={orderId} onChange={(event) => onOrderChange(event.target.value)} disabled={busy}>{data.orders.map((order) => <option key={order.order_id} value={order.order_id}>{order.order_id} · {order.customer} · ${Number(order.amount).toFixed(2)}</option>)}</select></label>
      <div className="composer-actions"><select value={fault} onChange={(event) => onFaultChange(event.target.value)} disabled={busy}>{FAULT_MODES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="run-action" disabled={busy || !orderId} onClick={onRun}>{busy ? 'Running' : 'Run refund'} <span>↗</span></button></div>
      {selectedOrder && <p>${Number(selectedOrder.amount).toFixed(2)} {Number(selectedOrder.amount) <= data.config.l2_auto_refund_ceiling ? 'is within' : 'exceeds'} the L2 ceiling.</p>}
    </section>
  </main>;
}
