import { motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, humanize, money, when } from '../../../lib/format.js';
import { ClassTag, StatusMark } from './Bits.jsx';

const SPAN_ICON = {
  'trace.start': 'flag',
  'license.check': 'key',
  plan: 'message',
  'tool.result': 'inbox',
  'execute.skipped': 'pause',
  'verify.readback': 'eye',
};

function parseAttrs(raw) {
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw || {}; } catch { return {}; }
}

function attrLine(name, a) {
  if (name === 'trace.start') return [a.kind, a.order_id, a.amount != null ? money(a.amount) : null, a.actor].filter(Boolean).join(' · ');
  if (name === 'license.check') return `level ${a.level}${a.quarantined ? ' · quarantined' : ''} · fault ${a.fault}`;
  if (name === 'plan') return a.source;
  if (name.startsWith('tool.execute')) return `${money(a.amount)} → ${a.order_id}${a.suppress_write ? ' · write suppressed' : ''}`;
  if (name === 'tool.result') return `“${a.message}” · trusted=${String(a.trusted)}`;
  if (name === 'execute.skipped') return a.reason;
  if (name === 'verify.readback') return `${money(a.before)} → ${money(a.after)} · matched=${String(a.matched)}`;
  if (name.startsWith('detection.')) return a.message;
  return Object.entries(a).map(([k, v]) => `${k}=${v}`).join(' · ');
}

const iconFor = (name) => SPAN_ICON[name] || (name.startsWith('tool.execute') ? 'play' : 'spark');

/** The one page a reviewer reads before restoring: numbers, plan, trace, rules.
 *  Labels follow the run's task class (e.g. credit_issued for store credit). */
export function EvidencePacket({ packet, taskClass, animate = true }) {
  const { data } = useStore();
  if (!packet) return null;
  const { run, detections = [], spans = [] } = packet;
  const meta = classMeta(data, taskClass || run.task_class || 'refund');
  const col = meta.effect_column || 'refunded_amount';
  const plan = spans.find((s) => s.name === 'plan');
  const planAttrs = plan ? parseAttrs(plan.attributes) : {};
  const mismatch = Math.abs((packet.intended_delta ?? 0) - (packet.actual_delta ?? 0)) > 1e-9;

  return (
    <div className="ev">
      <div className="ev-head">
        <div>
          <span className="mono muted">Run #{run.id} · {when(run.created_at)} {run.actor_id ? `· ${run.actor_id}` : ''}</span>
          <h2 className="serif">{run.order_id} <span className="muted">· {money(run.requested_amount)}</span></h2>
          <span className="ev-tags"><ClassTag label={meta.label} />{run.fault_mode && run.fault_mode !== 'none' && <span className="mc-tag mono is-alert">fault · {humanize(run.fault_mode)}</span>}</span>
        </div>
        <StatusMark status={run.status} />
      </div>

      {packet.neatlogs_link ? (
        <a className="btn btn-ink mc-trace-btn" href={packet.neatlogs_link} target="_blank" rel="noreferrer">
          <HandIcon name="eye" size={16} /> Open trace in neatlogs <HandIcon name="external" size={14} />
        </a>
      ) : run.trace_id ? (
        <p className="app-small muted mono">trace {run.trace_id.slice(0, 12)} · stored locally (neatlogs not connected)</p>
      ) : null}

      <div className="ev-nums">
        <div><span className="mono muted">Level at run</span><b className="serif">L{run.level_at_run}</b></div>
        <div><span className="mono muted">Decision</span><b className="ev-decision">{humanize(run.decision).toLowerCase()}</b></div>
        <div><span className="mono muted">Intended Δ</span><b className="serif">{money(packet.intended_delta)}</b></div>
        <div className={mismatch ? 'is-alert' : ''}><span className="mono muted">Verified Δ</span><b className="serif">{money(packet.actual_delta)}</b></div>
      </div>

      <div className={`ev-readback ${mismatch ? 'is-alert' : ''}`}>
        <span className="mono">{col} · read back from the database</span>
        <span className="ev-readback-row">
          <span><small className="mono muted">before</small><b className="serif">{money(packet.before_refunded ?? run.before_refunded)}</b></span>
          <HandIcon name="arrow-right" size={16} />
          <span><small className="mono muted">after</small><b className="serif">{money(packet.after_refunded ?? run.after_refunded)}</b></span>
        </span>
      </div>

      {detections.length > 0 && (
        <div className="ev-detections">
          {detections.map((d) => (
            <div key={d.id} className="ev-detection">
              <HandIcon name="bolt" size={18} />
              <div><code className="mono">{d.rule}</code>{d.severity && <span className="mono"> · {d.severity}</span>}<p>{d.message}</p></div>
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
              <span className="ev-node"><HandIcon name={bad ? 'bolt' : iconFor(s.name)} size={14} /></span>
              <code>{s.name}</code>
              <span className="ev-attr">{attrLine(s.name, a)}</span>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
