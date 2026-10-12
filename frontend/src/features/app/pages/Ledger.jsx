import { useState } from 'react';
import { useStore } from '../../../lib/store.jsx';
import { eventLinks } from '../../../lib/event-links.js';
import { flagReason, flagSentence, personName } from '../../../lib/ledger-words.js';
import { classLabel, isMcpClass } from '../../../lib/action-classes.js';
import { toDate, when } from '../../../lib/format.js';
import '../components/activity.css';

function useCopy(text) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(text)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
    .catch(() => {});
  return [copied, copy];
}

function CopyCmd({ cmd }) {
  const [copied, copy] = useCopy(cmd);
  return (
    <span className="hist-cmd">
      <code>{cmd}</code>
      <button type="button" className="btn btn-ghost btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
    </span>
  );
}

/** Small links to the neatlogs trace and the agent's Entire checkpoint. */
function EventLinks({ links }) {
  const [copied, copy] = useCopy(links.checkpoint?.explain || '');
  return (
    <>
      {links.trace && (
        <> · <a className="hist-link" href={links.trace} target="_blank" rel="noreferrer">Trace</a></>
      )}
      {links.checkpoint && (
        <> · <button type="button" className="hist-link" onClick={copy} title={`Copy: ${links.checkpoint.explain}`}>
          {copied ? 'Copied' : <>Entire <code>{links.checkpoint.id}</code></>}
        </button></>
      )}
    </>
  );
}

const VERBS = { promote: 'earned', demote: 'lost', restore: 'was resumed at' };

/** One permission change as a sentence. */
function sentence(e) {
  const [cls, repo] = e.task_class.split('@');
  const why = (e.reason || '').split('\n')[0];
  if (e.kind === 'flag') return flagSentence(e);
  if (e.kind === 'policy') {
    return <>Policy for <b>{repo === '*' ? 'all repositories' : repo}</b> changed{why ? <> - {why}</> : ''}</>;
  }
  const level = e.kind === 'demote' ? `L${e.from_level}` : `L${e.to_level}`;
  return <>{isMcpClass(cls) ? <b>{classLabel(cls)}</b> : <code>{cls}</code>} in <b>{repo}</b> {VERBS[e.kind] || 'changed to'} <b>{level}</b>{why ? <> - {why}</> : ''}</>;
}

/** Permission history: every change to what the coding agent may do. */
export function Ledger() {
  const { data } = useStore();
  const events = (data.events || []).filter((e) => (e.task_class || '').includes('@'));
  const repo = data.observability?.ledger?.repo;

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Permission history</h1>
          <p>Every change to what an agent may do - earned, lost or resumed by a person - is recorded here and as a commit in your repository's history.</p>
        </div>
      </header>

      {events.length === 0 ? (
        <div className="pl-empty">No changes yet. When the agent earns more freedom or gets paused, it shows up here.</div>
      ) : (
        <ul className="act-list hist-list">
          {events.map((e) => {
            const who = personName(e.actor_id);
            const date = toDate(e.created_at);
            const links = eventLinks(e);
            return (
              <li key={e.id} className="hist-row">
                <b>{sentence(e)}</b>
                {e.kind === 'flag' && flagReason(e) && <p className="hist-reason">“{flagReason(e)}”</p>}
                <small>
                  <span title={date ? date.toLocaleString() : undefined}>{when(e.created_at)}</span>
                  {who ? ` · by ${who}` : ''}
                  <EventLinks links={links} />
                </small>
                {(e.git_sha || links.checkpoint) && (
                  <details className="pl-more">
                    <summary>For auditors</summary>
                    <div className="hist-cmds">
                      {e.git_sha && (
                        <>
                          <span className="pl-small pl-muted">Recorded as commit <code>{e.git_sha.slice(0, 7)}</code>{repo ? <> in <code>{repo}</code></> : null}.</span>
                          <CopyCmd cmd={`git ${repo ? `-C "${repo}" ` : ''}show ${e.git_sha.slice(0, 7)}`} />
                          <CopyCmd cmd={`entire checkpoint explain ${e.git_sha.slice(0, 7)}`} />
                        </>
                      )}
                      {links.checkpoint && (
                        <>
                          <span className="pl-small pl-muted">The agent's session up to this change, in Entire:</span>
                          <CopyCmd cmd={links.checkpoint.explain} />
                        </>
                      )}
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
