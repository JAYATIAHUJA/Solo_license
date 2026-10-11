import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { toDate, when } from '../../../lib/format.js';
import {
  jobsName, levelWords, pausedSentence, personName, problemFromReason,
} from '../components/words.js';
import '../components/activity.css';

function CopyCmd({ cmd }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(cmd)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
    .catch(() => {});
  return (
    <span className="hist-cmd">
      <code>{cmd}</code>
      <button type="button" className="btn btn-ghost btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
    </span>
  );
}

/** One permission change as a sentence a shop owner can read. */
function sentence(data, e, threshold) {
  const key = e.task_class || 'refund';
  const jobs = jobsName(data, key);
  const to = levelWords(data, key, e.to_level).short;
  if (e.kind === 'promote') {
    const n = Number(/^(\d+)/.exec(e.reason || '')?.[1]) || threshold;
    return <>{jobs} earned <b>‘{to}’</b> after {n} correct job{n === 1 ? '' : 's'}</>;
  }
  if (e.kind === 'demote') {
    const p = problemFromReason(e.reason);
    return (
      <>
        {pausedSentence(data, key)}{p ? <> — {p.title.charAt(0).toLowerCase() + p.title.slice(1)}</> : ''}
        {e.run_id ? <> (<Link to={`/app/runs/${e.run_id}`}>job #{e.run_id}</Link>)</> : null}
      </>
    );
  }
  if (e.kind === 'restore') {
    const who = personName(e.actor_id) || 'Someone';
    return <>{who} resumed {jobs.toLowerCase()} at <b>‘{to}’</b>{e.reason ? `: ${e.reason}` : ''}</>;
  }
  return <>{jobs} changed to <b>‘{to}’</b>{e.reason ? `: ${e.reason}` : ''}</>;
}

/** Permission history: every change to what the agent may do. */
export function Ledger() {
  const { data } = useStore();
  const [cls, setCls] = useState('all');
  const classes = (data.task_classes || []).map((c) => c.key);
  const events = data.events.filter((e) => cls === 'all' || (e.task_class || 'refund') === cls);
  const repo = data.observability?.ledger?.repo;
  const threshold = data.config?.promotion_clean_runs || 3;

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Permission history</h1>
          <p>Every change to what the agent may do is recorded here and in your code repository's history.</p>
        </div>
        {classes.length > 1 && (
          <select className="act-select" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Job type">
            <option value="all">All job types</option>
            {classes.map((k) => <option key={k} value={k}>{jobsName(data, k)}</option>)}
          </select>
        )}
      </header>

      {events.length === 0 ? (
        <div className="pl-empty">No changes yet. When the agent earns more freedom or gets paused, it shows up here.</div>
      ) : (
        <ul className="act-list hist-list" data-tour="history">
          {events.map((e) => {
            const who = personName(e.actor_id);
            const date = toDate(e.created_at);
            return (
              <li key={e.id} className="hist-row">
                <b>{sentence(data, e, threshold)}</b>
                <small>
                  <span title={date ? date.toLocaleString() : undefined}>{when(e.created_at)}</span>
                  {who && e.kind !== 'restore' ? ` · during a job by ${who}` : ''}
                </small>
                {e.git_sha && (
                  <details className="pl-more">
                    <summary>For auditors</summary>
                    <div className="hist-cmds">
                      <span className="pl-small pl-muted">Recorded as commit <code>{e.git_sha.slice(0, 7)}</code>{repo ? <> in <code>{repo}</code></> : null}.</span>
                      <CopyCmd cmd={`git ${repo ? `-C "${repo}" ` : ''}show ${e.git_sha.slice(0, 7)}`} />
                      <CopyCmd cmd={`entire checkpoint explain ${e.git_sha.slice(0, 7)}`} />
                    </div>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
