import React from 'react';
import { LICENSE_LEVELS } from '../constants.js';

export function Inspector({ data, packet, busy, onRestore }) {
  return <aside className="inspector">
    <div className="inspector-tabs"><span className="tab active">Evidence</span></div>
    {!packet ? <div className="empty-inspector">Run a refund or choose a recent run to inspect verified evidence.</div> : <div className="packet-content">
      <h2>{packet.detections.length ? 'Detection evidence' : 'Verified refund evidence'}</h2>
      <p className="packet-kicker">Run #{packet.run.id} · {packet.run.order_id}</p>
      <div className="amount-strip"><div><span>Before</span><strong>${Number(packet.before_refunded).toFixed(2)}</strong></div><div><span>After</span><strong>${Number(packet.after_refunded).toFixed(2)}</strong></div><div><span>Intended</span><strong>${Number(packet.intended_delta).toFixed(2)}</strong></div></div>
      {packet.detections.length ? <div className="incident-box">{packet.detections.map((item) => <p key={item.id}><strong>{item.rule}</strong>{item.message}</p>)}</div> : <div className="verified-box"><i /> SQLite matches the intended side effect.</div>}
      <div className="trace-heading"><span>Trace spans</span><small>{packet.spans.length} recorded</small></div>
      <div className="trace-rows">{packet.spans.map((span) => <div key={`${span.name}-${span.created_at}`}><i /><span>{span.name}</span><small>{span.status}</small></div>)}</div>
      <div className="restore-panel"><p>Human review</p><span>{data.license.quarantined ? 'Choose the level to restore after reviewing this packet.' : 'No license restoration is needed.'}</span><div>{LICENSE_LEVELS.slice(1).map((_, index) => { const level = index + 1; return <button key={level} disabled={busy || !data.license.quarantined} onClick={() => onRestore(level)}>Restore L{level}</button>; })}</div></div>
    </div>}
  </aside>;
}
