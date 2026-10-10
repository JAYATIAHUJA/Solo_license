import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { jobsName, levelWords, pausedNow } from './words.js';
import './plain-form.css';
import './activity.css';

const DEFAULT_REASON = 'I read what happened and the problem is understood.';

/** Resume one paused job type after a person has read what happened.
 *  The chosen level and reason are recorded in the permission history. */
export function RestorePanel({ taskClass = 'refund', evidenceRunId }) {
  const { data, run, busy } = useStore();
  const license = data.licenses?.[taskClass];
  const fell = license?.demoted_from;
  const recommended = Math.max(0, (fell ?? 2) - 1);
  const [level, setLevel] = useState(recommended);
  const [reason, setReason] = useState(DEFAULT_REASON);
  useEffect(() => setLevel(recommended), [recommended]);
  if (!license?.quarantined) return null;
  const jobs = jobsName(data, taskClass);
  const evidence = evidenceRunId ?? data.runs.find((r) => r.task_class === taskClass && r.status === 'demoted')?.id;

  function resume() {
    const words = levelWords(data, taskClass, level);
    run(() => api.restore(level, reason.trim(), taskClass), `${jobs} resumed at “${words.short}”.`)
      .then((ok) => ok && setReason(DEFAULT_REASON));
  }

  return (
    <section className="pl-card act-resume pl-form" aria-label={`Resume ${jobs}`}>
      <div>
        <h3>Resume {jobs.toLowerCase()}</h3>
        <p className="pl-muted">
          {pausedNow(data, taskClass)}. Read what happened{evidenceRunId == null && evidence ? <> (<Link to={`/app/runs/${evidence}`}>open it</Link>)</> : ' above'}.
          {' '}Choose how much freedom to give back — you can always lower it later.
        </p>
      </div>

      <div className="pl-choices" role="radiogroup" aria-label="How much freedom to give back">
        {[0, 1, 2, 3].map((id) => {
          const words = levelWords(data, taskClass, id);
          return (
            <label key={id} className={`pl-choice ${level === id ? 'is-on' : ''}`}>
              <input type="radio" name={`resume-${taskClass}`} checked={level === id} onChange={() => setLevel(id)} />
              <span>
                <b>{words.short}</b>
                {id === recommended && <span className="pl-tag">Recommended</span>}
                {fell === id && <span className="pl-tag muted">Where it was</span>}
                <small>{words.long}</small>
              </span>
            </label>
          );
        })}
      </div>

      <label className="field">
        <span>Why are you resuming?</span>
        <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
        <small>Saved in the permission history.</small>
      </label>

      <div className="pl-actions">
        <button className="btn btn-ink" disabled={busy || reason.trim().length < 4} onClick={resume}>Resume</button>
      </div>
    </section>
  );
}

/** A resume card for every paused job type. Kept for screens that list them all. */
export function RestorePanels() {
  const { data } = useStore();
  const keys = Object.entries(data.licenses || {}).filter(([, l]) => l.quarantined).map(([k]) => k);
  if (!keys.length) return null;
  return (
    <div className="act-resumes">
      {keys.map((k) => <RestorePanel key={k} taskClass={k} />)}
    </div>
  );
}
