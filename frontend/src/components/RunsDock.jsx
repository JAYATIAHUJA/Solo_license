import React from 'react';

export function RunsDock({ runs, onSelect }) {
  return <section className="runs-dock"><div className="dock-title"><span>Recent runs</span><small>{runs.length} recorded</small></div>{runs.length === 0 ? <p>No runs yet.</p> : runs.map((run) => <button key={run.id} onClick={() => onSelect(run.id)}><i className={run.status} /> <strong>#{String(run.id).padStart(3, '0')}</strong><span>{run.order_id}</span><em>{run.status}</em><b>${(Number(run.after_refunded) - Number(run.before_refunded)).toFixed(2)}</b></button>)}</section>;
}
