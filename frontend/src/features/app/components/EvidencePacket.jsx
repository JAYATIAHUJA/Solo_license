import { motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { money, when } from '../../../lib/format.js';
import { StatusMark } from './Bits.jsx';

const SPAN_ICON = {
  'license.check': 'key',
  plan: 'message',
  'tool.execute_refund': 'play',
  'tool.result': 'inbox',
  'execute.skipped': 'pause',
  'verify.readback': 'eye',
};

function parseAttrs(raw) {
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw || {}; } catch { return {}; }
}

function attrLine(name, a) {
  if (name === 'license.check') return `level ${a.level}${a.quarantined ? ' · quarantined' : ''} · fault ${a.fault}`;
  if (name === 'plan') return a.source;
  if (name === 'tool.execute_refund') return `${money(a.amount)} → ${a.order_id}${a.suppress_write ? ' · write suppressed' : ''}`;
  if (name === 'tool.result') return `“${a.message}” · trusted=${String(a.trusted)}`;
  if (name === 'execute.skipped') return a.reason;
  if (name === 'verify.readback') return `${money(a.before)} → ${money(a.after)} · matched=${String(a.matched)}`;
  if (name.startsWith('detection.')) return a.message;
  return Object.entries(a).map(([k, v]) => `${k}=${v}`).join(' · ');
}

/** The one page a reviewer reads before restoring: numbers, plan, trace, rules. */
export function EvidencePacket({ packet, animate = true }) {
  if (!packet) return null;
  const { run, detections, spans } = packet;
  const plan = spans.find((s) => s.name === 'plan');
  const planAttrs = plan ? parseAttrs(plan.attributes) : {};

  return (
    <div className="ev">
      <div className="ev-head">
        <div>
          <span className="mono muted">Run #{run.id} · {when(run.created_at)}</span>
          <h2 className="serif">{run.order_id} <span className="muted">· {money(run.requested_amount)}</span></h2>
        </div>
        <StatusMark status={run.status} />
      </div>

      <div className="ev-nums">
        <div><span className="mono muted">Level at run</span><b className="serif">L{run.level_at_run}</b></div>
        <div><span className="mono muted">Decision</span><b className="ev-decision">{run.decision.replaceAll('_', ' ').toLowerCase()}</b></div>
        <div><span className="mono muted">Intended Δ</span><b className="serif">{money(packet.intended_delta)}</b></div>
        <div className={packet.intended_delta !== packet.actual_delta ? 'is-alert' : ''}><span className="mono muted">Verified Δ</span><b className="serif">{money(packet.actual_delta)}</b></div>
      </div>

      {detections.length > 0 && (
        <div className="ev-detections">
          {detections.map((d) => (
            <div key={d.id} className="ev-detection">
              <HandIcon name="bolt" size={18} />
              <div><code className="mono">{d.rule}</code><p>{d.message}</p></div>
            </div>
          ))}
        </div>
      )}

      {planAttrs.rationale && (
        <blockquote className="ev-plan">
          <span className="mono muted">Agent plan · {planAttrs.source}</span>
          <p>{planAttrs.rationale}</p>
        </blockquote>
      )}

      <ol className="ev-trace">
        {spans.map((s, i) => {
          const a = parseAttrs(s.attributes);
          const bad = s.status === 'error';
          return (
            <motion.li
              key={`${s.name}-${i}`}
              className={bad ? 'is-alert' : ''}
              initial={animate ? { opacity: 0, x: -8 } : false}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.07 }}
            >
              <span className="ev-node"><HandIcon name={bad ? 'bolt' : SPAN_ICON[s.name] || 'spark'} size={14} /></span>
              <code>{s.name}</code>
              <span className="ev-attr">{attrLine(s.name, a)}</span>
            </motion.li>
          );
        })}
      </ol>
      {packet.neatlogs_link && (
        <a className="btn btn-line btn-sm" href={packet.neatlogs_link} target="_blank" rel="noreferrer">Open trace in neatlogs <HandIcon name="external" size={14} /></a>
      )}
    </div>
  );
}
