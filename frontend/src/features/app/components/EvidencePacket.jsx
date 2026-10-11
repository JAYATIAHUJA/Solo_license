import { useStore } from '../../../lib/store.jsx';
import { outcome, problem } from '../../../lib/copy.js';
import { money, toDate, when } from '../../../lib/format.js';
import {
  effectWord, isPractice, levelWords, pausedSentence, personName, runSentence,
} from './words.js';
import './activity.css';

function parseAttrs(raw) {
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw || {}; } catch { return {}; }
}

/** One line per recorded step, for the technical details only. */
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

const DECISION_WORDS = {
  SUGGEST: 'So it only suggested what to do.',
  DRAFT_FOR_APPROVAL: 'So it prepared it and waited for your OK.',
  AUTO_EXECUTE: 'So it went ahead on its own.',
  AUTO_EXECUTE_AUDITED: 'So it went ahead on its own.',
};

const PRACTICE_WORDS = {
  quiet_failure: 'the tool says “done” but does nothing',
  policy_violation: 'the agent oversteps its permission',
  skip_verification: 'the agent skips the double-check',
};

/** Plain description of the agent's plan. Model-written plans are shown as is;
 *  rule-based ones are rewritten, since their text is internal. */
function planLine(run, planAttrs) {
  const source = String(planAttrs.source || '');
  if (planAttrs.rationale && source.startsWith('llm')) return planAttrs.rationale;
  const found = /\('([^']+)'\)/.exec(planAttrs.rationale || run.notes || '')?.[1];
  const quoted = found === 'approved by human' ? '' : found;
  const what = run.task_class === 'store_credit' ? `Give ${money(run.requested_amount)} store credit` : `Refund ${money(run.requested_amount)}`;
  return `${what} on ${run.order_id}${quoted ? ` — reason given: “${quoted}”` : ''}.`;
}

/** "What happened" for one job: a short checklist in words, then the
 *  technical record behind a disclosure. */
export function EvidencePacket({ packet, taskClass }) {
  const { data } = useStore();
  if (!packet) return null;
  const { run, detections = [], spans = [] } = packet;
  const key = taskClass || run.task_class || 'refund';
  const effect = effectWord(key);
  const spanNamed = (name) => spans.find((s) => s.name === name);
  const planAttrs = parseAttrs(spanNamed('plan')?.attributes);
  const checkAttrs = parseAttrs(spanNamed('license.check')?.attributes);
  const verifyAttrs = parseAttrs(spanNamed('verify.readback')?.attributes);
  const toolAttrs = parseAttrs(spanNamed('tool.result')?.attributes);
  const executed = Boolean(run.executed) || spans.some((s) => s.name.startsWith('tool.execute'));
  const verified = verifyAttrs.verified !== false;
  // The first read-back is what judged the tool; a recovery adds a second one.
  const before = verifyAttrs.before ?? packet.before_refunded ?? run.before_refunded;
  const after = verifyAttrs.after ?? packet.after_refunded ?? run.after_refunded;
  const firstMatched = verifyAttrs.matched !== undefined ? verifyAttrs.matched
    : Math.abs((packet.intended_delta ?? 0) - (packet.actual_delta ?? 0)) <= 1e-9;
  const recoverDone = parseAttrs(spanNamed('recover.done')?.attributes);
  const recoverySteps = spans.filter((sp) => sp.name.startsWith('recover.')).map((sp) => sp.name);
  const finalAfter = packet.after_refunded ?? run.after_refunded;
  const out = outcome(run.status);
  const caught = run.status === 'demoted' || detections.length > 0;
  const customer = packet.order?.customer;
  const who = personName(run.actor_id);
  const date = toDate(run.created_at);
  const approvedBy = String(run.idempotency_key || '').startsWith('approval') ? (who || 'A person') : '';

  const steps = [
    {
      title: 'Checked permission',
      tone: 'ok',
      body: (
        <>
          Allowed to: <b>{levelWords(data, key, run.level_at_run).short}</b>.
          {checkAttrs.quarantined ? ' This job type was paused at the time.'
            : approvedBy ? ` ${approvedBy} approved it, so it went ahead.`
              : ` ${DECISION_WORDS[run.decision] || ''}`}
        </>
      ),
    },
    { title: 'Made a plan', tone: 'ok', body: planLine(run, planAttrs) },
    executed
      ? {
        title: 'Carried it out',
        tone: 'ok',
        body: toolAttrs.message ? 'Sent it to the payment tool, which replied that it was done.' : 'Sent it to the payment tool.',
      }
      : {
        title: 'Did not carry it out',
        tone: 'muted',
        body: run.status === 'suggested' ? 'Left for you to do.' : run.status === 'pending_approval' ? 'Waiting for your OK.' : 'Nothing was sent.',
      },
  ];
  if (executed) {
    steps.push(verified
      ? {
        title: 'Double-checked the order',
        tone: firstMatched ? 'ok' : 'bad',
        body: <>Before: <b>{money(before)}</b> {effect} · After: <b>{money(after)}</b> {effect}{firstMatched ? '' : ' — not what the tool claimed.'}</>,
      }
      : { title: 'Skipped the double-check', tone: 'bad', body: 'The order was never re-read to confirm the result.' });
  }
  if (recoverySteps.length) {
    const how = recoverDone.how || '';
    const retried = recoverySteps.includes('recover.retry');
    steps.push(run.recovered
      ? {
        title: 'Recovered it safely',
        tone: 'ok',
        body: retried
          ? <>Re-read the order (still nothing), then retried once with the <b>same request key</b> — so it could never pay twice — and checked again: <b>{money(finalAfter)}</b> {effect}.</>
          : <>Re-read the order and found the change had landed after all: <b>{money(finalAfter)}</b> {effect}.</>,
      }
      : {
        title: 'Could not recover it',
        tone: 'bad',
        body: `Tried to put it right but could not confirm the result${how ? ` (${how})` : ''}. A person needs to look.`,
      });
  }

  return (
    <article className="act-detail">
      <header className="act-detail-head">
        <div className="act-detail-tags">
          <span className={`pl-status ${out.tone}`}>{out.label}</span>
          {isPractice(run) && <span className="act-practice">practice</span>}
        </div>
        <h2>{runSentence(data, run, customer)}</h2>
        <p className="pl-muted pl-small">
          {who ? `by ${who} · ` : ''}
          <span title={date ? date.toLocaleString() : undefined}>{when(run.created_at)}</span>
        </p>
      </header>

      {isPractice(run) && (
        <p className="pl-help">
          <span>This was a <b>practice problem</b>: you set it up so that {PRACTICE_WORDS[run.fault_mode] || 'something goes wrong'}, to see the safety net work.</span>
        </p>
      )}

      <section className="pl-section">
        <h2>What happened</h2>
        <ol className="act-steps">
          {steps.map((s) => (
            <li key={s.title} className={`is-${s.tone}`}>
              <span className="act-step-mark" aria-hidden="true">{s.tone === 'bad' ? '✗' : s.tone === 'muted' ? '–' : '✓'}</span>
              <div><b>{s.title}</b><p>{s.body}</p></div>
            </li>
          ))}
          <li className={`is-result is-${caught ? 'bad' : out.tone}`}>
            <span className="act-step-mark" aria-hidden="true">{caught ? '✗' : run.status === 'clean' || run.status === 'approved' ? '✓' : '…'}</span>
            <div>
              <b>Result: {caught ? 'Problem caught' : out.label}</b>
              {caught ? (
                <>
                  {(detections.length ? detections : [{ id: 'x', rule: null }]).map((d) => {
                    const p = problem(d.rule);
                    return <p key={d.id}><b>{p.title}.</b> {p.explain}</p>;
                  })}
                  {run.recovered ? <p><b>The customer still got their money</b> — but the tool could not be trusted, so the licence drops anyway.</p> : null}
                  <p className="act-paused">{pausedSentence(data, key)} — nothing more runs until someone reviews this and presses Resume.</p>
                </>
              ) : run.status === 'clean' ? (
                <p>The order shows the change, so this counts as a correct job.</p>
              ) : run.status === 'approved' ? (
                <p>A person approved this and it was carried out as a new job.</p>
              ) : null}
            </div>
          </li>
        </ol>
      </section>

      {packet.neatlogs_link && (
        <p>
          <a className="btn btn-line btn-sm" href={packet.neatlogs_link} target="_blank" rel="noreferrer">Open the full record in neatlogs ↗</a>
        </p>
      )}

      <details className="pl-more">
        <summary>Show technical details</summary>
        <div className="act-tech">
          <dl className="pl-kv">
            <dt>Job #</dt><dd>{run.id}</dd>
            <dt>Job type</dt><dd><code>{run.task_class}</code></dd>
            <dt>Permission level</dt><dd>L{run.level_at_run}</dd>
            <dt>Decision</dt><dd><code>{run.decision}</code></dd>
            <dt>Status</dt><dd><code>{run.status}</code></dd>
            {run.trace_id && <><dt>Trace id</dt><dd><code>{run.trace_id}</code>{!packet.neatlogs_link && ' (stored locally)'}</dd></>}
            {run.actor_id && <><dt>Started by</dt><dd><code>{run.actor_id}</code>{run.actor_role ? ` · ${run.actor_role}` : ''}</dd></>}
            {run.idempotency_key && <><dt>Idempotency key</dt><dd><code>{run.idempotency_key}</code></dd></>}
            {isPractice(run) && <><dt>Practice mode</dt><dd><code>{run.fault_mode}</code></dd></>}
            <dt>Intended change</dt><dd>{money(packet.intended_delta)}</dd>
            <dt>Verified change</dt><dd>{money(packet.actual_delta)}</dd>
            {planAttrs.source && <><dt>Plan source</dt><dd><code>{planAttrs.source}</code></dd></>}
            {planAttrs.rationale && <><dt>Plan text</dt><dd>{planAttrs.rationale}</dd></>}
          </dl>
          {detections.length > 0 && (
            <div>
              <b className="pl-small">Safety checks that fired</b>
              <ul className="act-tech-list">
                {detections.map((d) => <li key={d.id}><code>{d.rule}</code>{d.severity ? ` · ${d.severity}` : ''} — {d.message}</li>)}
              </ul>
            </div>
          )}
          {spans.length > 0 && (
            <div>
              <b className="pl-small">Recorded steps</b>
              <ol className="act-tech-list">
                {spans.map((s, i) => (
                  <li key={`${s.name}-${i}`} className={s.status === 'error' ? 'is-bad' : ''}>
                    <code>{s.name}</code> {attrLine(s.name, parseAttrs(s.attributes))}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </details>
    </article>
  );
}
