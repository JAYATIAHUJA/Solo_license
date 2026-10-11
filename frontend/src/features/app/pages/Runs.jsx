import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { outcome } from '../../../lib/copy.js';
import { when } from '../../../lib/format.js';
import { EvidencePacket } from '../components/EvidencePacket.jsx';
import { RestorePanel } from '../components/RestorePanel.jsx';
import { ApproveBar } from '../components/ApproveBar.jsx';
import { isPractice, jobsName, pausedNow, personName, runSentence } from '../components/words.js';
import '../components/activity.css';

const WAITING = new Set(['pending_approval', 'suggested']);
const FILTERS = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'waiting', label: 'Waiting for you', test: (r) => WAITING.has(r.status) },
  { id: 'problems', label: 'Problems caught', test: (r) => r.status === 'demoted' },
];

/** Activity: every job the agent did or suggested, newest first, and the
 *  plain "What happened" for the one you pick. */
export function Runs() {
  const { data, load } = useStore();
  const { runId } = useParams();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const [cls, setCls] = useState('all');
  const selected = Number(runId) || data.runs[0]?.id;
  const classes = useMemo(() => (data.task_classes || []).map((c) => c.key), [data.task_classes]);

  // The background refresh brings back the latest job's record, so keep the
  // last record for the selected job on screen and fetch it again quietly.
  const [kept, setKept] = useState(null);
  const asked = useRef({ id: null, at: 0 });
  const fresh = data.packet?.run?.id === selected ? data.packet : null;
  useEffect(() => {
    if (fresh) { setKept(fresh); return; }
    if (!selected) return;
    const now = Date.now();
    // At most one quiet refetch every few seconds per job, so a missing job can't loop.
    if (asked.current.id === selected && now - asked.current.at < 4000) return;
    asked.current = { id: selected, at: now };
    load(selected);
  }, [selected, data.packet]); // eslint-disable-line react-hooks/exhaustive-deps

  const byClass = data.runs.filter((r) => cls === 'all' || r.task_class === cls);
  const active = FILTERS.find((f) => f.id === filter) || FILTERS[0];
  const list = byClass.filter(active.test);
  const packet = fresh || (kept?.run?.id === selected ? kept : null);
  const paused = Object.entries(data.licenses || {}).filter(([, l]) => l.quarantined).map(([k]) => k);
  const pausedRun = (key) => data.runs.find((r) => r.task_class === key && r.status === 'demoted')?.id;
  const detailClass = packet?.run?.task_class || 'refund';

  return (
    <div className={`pl-page act-page ${runId ? 'has-detail' : ''}`}>
      <header className="pl-head">
        <div>
          <h1>Activity</h1>
          <p>Everything the agent did or suggested. Pick one to see what happened.</p>
        </div>
      </header>

      {paused.map((key) => (
        <div key={key} className="pl-alert">
          <span>
            <b>{pausedNow(data, key)}.</b> A problem was caught.{' '}
            {pausedRun(key) && !(runId && Number(runId) === pausedRun(key))
              ? <Link to={`/app/runs/${pausedRun(key)}`}>Review it and resume →</Link>
              : 'Review it below, then resume.'}
          </span>
        </div>
      ))}

      <div className="act-cols">
        <section className="act-list-col" aria-label="Activity list">
          <div className="act-filters">
            <div className="act-tabs" role="tablist" aria-label="Show">
              {FILTERS.map((f) => {
                const n = byClass.filter(f.test).length;
                return (
                  <button key={f.id} type="button" role="tab" aria-selected={filter === f.id} className={filter === f.id ? 'is-on' : ''} onClick={() => setFilter(f.id)}>
                    {f.label}{f.id !== 'all' && n > 0 ? <span className="act-count">{n}</span> : null}
                  </button>
                );
              })}
            </div>
            {classes.length > 1 && (
              <select className="act-select" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Job type">
                <option value="all">All job types</option>
                {classes.map((k) => <option key={k} value={k}>{jobsName(data, k)}</option>)}
              </select>
            )}
          </div>

          {list.length === 0 ? (
            <div className="pl-empty">
              {data.runs.length
                ? (filter === 'waiting' ? 'Nothing is waiting for you.' : filter === 'problems' ? 'No problems caught.' : 'Nothing here.')
                : <>No activity yet. <Link to="/app/agent">Give the agent its first job →</Link></>}
            </div>
          ) : (
            <ul className="act-list">
              {list.map((r) => {
                const out = outcome(r.status);
                const who = personName(r.actor_id);
                return (
                  <li key={r.id}>
                    <button type="button" className={`act-row ${r.id === selected ? 'is-on' : ''}`} onClick={() => navigate(`/app/runs/${r.id}`)} aria-current={r.id === selected ? 'true' : undefined}>
                      <span className="pl-row-main">
                        <b>{runSentence(data, r)}</b>
                        <small>
                          {who ? `by ${who} · ` : ''}{when(r.created_at)}
                          {isPractice(r) && <span className="act-practice">practice</span>}
                        </small>
                      </span>
                      <span className={`pl-status ${out.tone}`}>{out.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="act-detail-col" aria-label="What happened">
          {runId && <Link className="act-back" to="/app/runs">← All activity</Link>}
          {!selected ? null : !packet ? (
            <div className="pl-empty">Loading…</div>
          ) : (
            <div className="pl-card act-detail-card">
              <div data-tour="what-happened"><EvidencePacket packet={packet} /></div>
              <ApproveBar run={packet.run} onDone={(id) => id && navigate(`/app/runs/${id}`)} />
              {data.licenses?.[detailClass]?.quarantined && (
                <div data-tour="resume"><RestorePanel taskClass={detailClass} evidenceRunId={packet.run.id} /></div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
