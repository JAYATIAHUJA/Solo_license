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
function codingSentence(e) {
  const [cls, repo] = e.task_class.split('@');
  const verb = { promote: 'earned', demote: 'lost', restore: 'was resumed at' }[e.kind] || 'changed to';
  const level = e.kind === 'demote' ? `L${e.from_level}` : `L${e.to_level}`;
  const why = (e.reason || '').split('\n')[0];
  return <><code>{cls}</code> in <b>{repo}</b> {verb} <b>{level}</b>{why ? <> - {why}</> : ''}</>;
}

function sentence(data, e) {
  if ((e.task_class || '').includes('@')) return codingSentence(e);
  const key = e.task_class || 'refund';
  const jobs = jobsName(data, key);
  const to = levelWords(data, key, e.to_level).short;
  if (e.kind === 'promote') {
    const n = Number(/^(\d+)/.exec(e.reason || '')?.[1]);
    return <>{jobs} earned <b>‘{to}’</b>{n ? <> with {n} double-checked jobs on record</> : ''}</>;
  }
  if (e.kind === 'demote') {
    const p = problemFromReason(e.reason);
    return (
      <>
        {pausedSentence(data, key)}{p ? <> - {p.title.charAt(0).toLowerCase() + p.title.slice(1)}</> : ''}
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
  const events = data.events.filter((e) => cls === 'all'
    || (cls === 'coding' ? (e.task_class || '').includes('@') : (e.task_class || 'refund') === cls));
  const repo = data.observability?.ledger?.repo;

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Permission history</h1>
          <p>Every change to what an agent may do - earned, lost or resumed by a person - is recorded here and as a commit in your repository's history.</p>
        </div>
        {classes.length > 1 && (
          <select className="act-select" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Job type">
            <option value="all">All job types</option>
            {classes.map((k) => <option key={k} value={k}>{jobsName(data, k)}</option>)}
            <option value="coding">Coding agent</option>
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
                <b>{sentence(data, e)}</b>
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
