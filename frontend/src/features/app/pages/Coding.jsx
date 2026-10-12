import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { moneyWhole, toDate, when } from '../../../lib/format.js';
import { flagRequest, flaggedTargets, levelChanges, levelsOf, licenseKey, pauseCause } from '../../../lib/coding-live.js';
import { byTurn, loopBadge, remediationView } from '../../../lib/coding-guidance.js';
import { personName } from '../../../lib/ledger-words.js';
import { classLabel, isMcpClass } from '../../../lib/action-classes.js';
import { CopyCommand } from '../../../components/CopyCommand.jsx';
import './coding.css';

const POLL_MS = 4000;
const FLASH_MS = 1600;

export const CODING_LEVELS = [
  { short: 'Asks you', long: 'Asks you before every action of this kind.' },
  { short: 'Runs what you approved', long: 'Runs the commands you already approved here on its own; anything new still asks.' },
  { short: 'Runs on its own', long: 'Runs every action of this kind on its own. One failure takes that away.' },
];

const DECISION = {
  allow: { label: 'Ran on its own', tone: 'ok' },
  ask: { label: 'Asked you', tone: 'wait' },
  deny: { label: 'Blocked', tone: 'bad' },
};

const TURN = {
  open: { label: 'Working', tone: 'muted' },
  verified: { label: 'Verified', tone: 'ok' },
  blocked: { label: 'Sent back', tone: 'wait' },
  failed: { label: 'Failed checks', tone: 'bad' },
  rewound: { label: 'Rewound', tone: 'muted' },
};

/** Live coding-agent state, polled while the tab is visible. */
export function useCoding() {
  const [coding, setCoding] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      setCoding(await api.coding());
      setError('');
    } catch (cause) {
      setError(cause.message);
    }
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);
  return { coding, setCoding, error, load };
}

/** { "repo:class": "up" | "down" } for levels that moved at the last poll, cleared after a moment. */
function useLevelFlash(licenses) {
  const seen = useRef(null);
  const [flash, setFlash] = useState({});
  const signature = JSON.stringify(levelsOf(licenses));
  useEffect(() => {
    const levels = JSON.parse(signature);
    const changes = levelChanges(seen.current, levels);
    seen.current = levels;
    if (Object.keys(changes).length) setFlash(changes);
  }, [signature]);
  useEffect(() => {
    if (!Object.keys(flash).length) return undefined;
    const timer = window.setTimeout(() => setFlash({}), FLASH_MS);
    return () => window.clearTimeout(timer);
  }, [flash]);
  return flash;
}

/** "Report mistake": a required reason, then the flag. */
function FlagBox({ target, onDone, onCancel }) {
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event) => {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      onDone(await api.codingFlag(flagRequest(target, reason)));
    } catch (cause) {
      setError(cause.message);
      setPending(false);
    }
  };
  return (
    <form className="cd-flag" onSubmit={submit}>
      <label>
        <span>What was wrong? The agent is told on its next prompt, and this kind of action goes back to asking you.</span>
        <input type="text" value={reason} maxLength={500} required autoFocus disabled={pending}
          onChange={(e) => setReason(e.target.value)} placeholder="e.g. it deleted the migrations folder" />
      </label>
      <span className="cd-actions">
        <button type="submit" className="btn btn-ink btn-sm" disabled={pending || !reason.trim()}>
          {pending ? 'Reporting…' : 'Report mistake'}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" disabled={pending} onClick={onCancel}>Cancel</button>
      </span>
      {error && <p className="cd-flag-error" role="alert">{error}</p>}
    </form>
  );
}

/** What the agent was told (or will be told at its next prompt) during one turn. */
function Told({ remediations }) {
  return remediations.map((r) => {
    const view = remediationView(r);
    return (
      <div key={r.id} className="cd-told">
        <span className="cd-told-head">
          <b>{r.delivered_at ? 'Agent was told:' : 'Agent will be told:'}</b>
          <span className={`pl-status ${view.status.tone}`}>{view.status.label}</span>
          <small>{when(r.delivered_at || r.created_at)}</small>
        </span>
        <pre className="cd-reason cd-told-text">{view.text}</pre>
      </div>
    );
  });
}

/** Flag state for one decision or turn row: the side button, and the box and result below it. */
function flagRow({ id, target, flagged, flag, busy }) {
  const status = flagged ? <span className="pl-status bad">Flagged as wrong</span> : null;
  const button = flagged || flag.open === id ? status : (
    <button type="button" className="btn btn-ghost btn-sm cd-report" disabled={busy} onClick={() => flag.setOpen(id)}
      title="Tell Solo License this action went wrong. This kind of action goes back to asking you, and the agent is told what to undo.">
      Report mistake
    </button>
  );
  const below = (
    <>
      {flag.open === id && !flagged && (
        <FlagBox target={target} onDone={(body) => flag.done(id, body)} onCancel={() => flag.setOpen(null)} />
      )}
      {flag.result?.id === id && <p className="cd-flag-done" role="status">{flag.result.text}</p>}
    </>
  );
  return { button, below };
}

function nextSentence(lic) {
  if (lic.always_asks) return 'Always asks a person. This kind of action is never automatic.';
  if (lic.next_level == null) return `At the highest level this kind of action may reach (L${lic.ceiling}).`;
  if (lic.runs_needed == null) return 'Not reachable with the current costs.';
  if (lic.runs_needed === 0) return `Ready for L${lic.next_level}: one more verified run promotes it.`;
  return `${lic.runs_needed} more verified run${lic.runs_needed === 1 ? '' : 's'} to earn L${lic.next_level}.`;
}

const START = [
  { n: '1', title: 'Connect your agent', text: 'One command adds Solo License to its hooks.' },
  { n: '2', title: 'Work as usual', text: 'Every action starts at L0 and asks you.' },
  { n: '3', title: 'It earns autonomy', text: 'Verified turns unlock L1, then L2.' },
];

/** First visit, nothing connected yet: what happens, and one button. */
function Start() {
  return (
    <section className="cd-start">
      <div className="cd-start-head">
        <h2>Connect your first coding agent</h2>
        <p>Claude Code, Codex, Cursor, Gemini and more. Takes about two minutes.</p>
      </div>
      <ol className="cd-start-steps">
        {START.map((s) => (
          <li key={s.n}>
            <span className="cd-start-n">{s.n}</span>
            <b>{s.title}</b>
            <span>{s.text}</span>
          </li>
        ))}
      </ol>
      <div className="cd-start-cta">
        <Link className="btn btn-ink" to="/onboarding">Set up your agent →</Link>
        <span className="pl-small pl-muted">Nothing is ever allowed silently. If Solo License is down, your agent asks you as before.</span>
      </div>
    </section>
  );
}

/** "Jayati flagged it as wrong", or "" when the class was paused by a failure. */
function flaggedBy(events, lic) {
  const cause = pauseCause(events, lic);
  return cause.flagged ? `${personName(cause.actorId) || 'A person'} flagged it as wrong` : '';
}

function LicenseCard({ lic, onResume, busy, flash, flagged }) {
  const paused = lic.demoted_from != null && lic.level === 0;
  const total = lic.successes + (lic.runs_needed || 0);
  const share = lic.runs_needed ? Math.min(1, lic.successes / Math.max(1, total)) : 1;
  const words = CODING_LEVELS[Math.min(lic.level, 2)];
  return (
    <article className={`pl-card cd-lic ${paused ? 'is-paused' : ''}`}>
      <div className="app-card-top">
        <h3>{lic.label} <small className="pl-muted">· {lic.principal === 'main' ? 'Main agent' : lic.principal}</small></h3>
        <span aria-live="polite"
          className={`pl-status cd-level ${paused ? 'bad' : lic.level >= 1 ? 'ok' : 'wait'}${flash ? ` is-${flash}` : ''}`}>
          L{lic.level} · {paused ? 'Paused' : words.short}
        </span>
      </div>
      <p>{!paused ? words.long : flagged
        ? `${flagged}, so it lost L${lic.demoted_from}. It asks you again until it earns it back.`
        : `Lost L${lic.demoted_from} after a failure. It asks you again until it earns it back.`}</p>
      {!lic.always_asks && lic.next_level != null && (
        <div className="app-evidence" role="img" aria-label={nextSentence(lic)}><i style={{ width: `${share * 100}%` }} /></div>
      )}
      <p className="pl-small pl-muted">{nextSentence(lic)}</p>
      {isMcpClass(lic.action_class) && (
        <p className="pl-small pl-muted">MCP tools: reads can run on their own, writes once you approved that tool, and destructive tools (merge, delete, deploy) always ask.</p>
      )}
      <p className="pl-small pl-muted">{lic.successes} verified · {lic.failures} failed · ceiling L{lic.ceiling ?? lic.max_level} · <code>{lic.action_class}</code></p>
      {paused && (
        <div className="cd-actions">
          <button type="button" className="btn btn-line btn-sm" disabled={busy} onClick={() => onResume(lic, lic.demoted_from)}>
            Resume at L{lic.demoted_from}
          </button>
        </div>
      )}
    </article>
  );
}

const isLink = (url) => /^https?:\/\//i.test(String(url || ''));

/** Where this turn's story is told: its neatlogs trace and the CLI command that prints all of it. */
function TurnLinks({ turn }) {
  return (
    <small className="cd-links">
      {isLink(turn.neatlogs_link)
        ? <a className="hist-link" href={turn.neatlogs_link} target="_blank" rel="noreferrer">Trace in neatlogs</a>
        : turn.trace_id ? <span title="Add a neatlogs key in Settings to send traces">Trace kept locally</span> : null}
      {turn.trace_id ? ' · ' : ''}<code>solo-license explain {turn.id}</code>
    </small>
  );
}

function Savings({ s }) {
  if (!s) return null;
  const items = [
    { n: s.auto_allowed, label: 'prompts you did not have to answer' },
    { n: `${Math.round(s.minutes_saved)} min`, label: `developer time saved (${moneyWhole(s.usd_saved)})` },
    { n: s.blocked, label: 'forbidden actions blocked' },
    { n: s.sent_back, label: 'turns sent back (over-editing or failing tests)' },
  ];
  return (
    <div className="cd-savings" aria-label="What Solo License did">
      {items.map((i) => (
        <div key={i.label}><b>{i.n}</b><span>{i.label}</span></div>
      ))}
    </div>
  );
}

export function Coding() {
  const { coding, setCoding, error } = useCoding();
  const { setToast, session, load: loadHistory } = useStore();
  const [repo, setRepo] = useState('');
  const [busy, setBusy] = useState(false);
  const [flagOpen, setFlagOpen] = useState(null);
  const [flagResult, setFlagResult] = useState(null);
  const [allDecisions, setAllDecisions] = useState(null);
  const [loadingAll, setLoadingAll] = useState(false);
  const flash = useLevelFlash(coding?.licenses);
  const flagged = useMemo(() => flaggedTargets(coding?.flags), [coding]);
  const told = useMemo(() => byTurn(coding?.remediations), [coding]);
  const looped = useMemo(() => byTurn(coding?.loops), [coding]);
  const flag = {
    open: flagOpen,
    setOpen: (id) => { setFlagOpen(id); setFlagResult(null); },
    result: flagResult,
    done: (id, body) => {
      if (body?.licenses) setCoding(body);
      setFlagOpen(null);
      setFlagResult({ id, text: 'Flagged. This kind of action is back to L0, and the agent is told what to undo on its next prompt.' });
      loadHistory();
    },
  };

  const repos = useMemo(() => (coding?.repos || []).map((r) => r.repo), [coding]);
  const current = repo || repos[0] || '';
  const licenses = (coding?.licenses || []).filter((l) => !current || l.repo === current);
  const matching = (allDecisions || coding?.decisions || []).filter((d) => !current || d.repo === current);
  const decisions = allDecisions ? matching : matching.slice(0, 15);
  const hasMore = !allDecisions && (coding?.decisions || []).filter((d) => !current || d.repo === current).length > 15;
  const turns = (coding?.turns || []).filter((t) => !current || t.repo === current).slice(0, 10);
  const paused = licenses.filter((l) => l.demoted_from != null && l.level === 0);

  async function act(fn, success) {
    setBusy(true);
    try {
      const body = await fn();
      if (body?.licenses) setCoding(body);
      setToast({ kind: 'ok', text: success, at: Date.now() });
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setBusy(false);
    }
  }

  const viewAll = async () => {
    setLoadingAll(true);
    try {
      const body = await api.codingDecisions(current);
      setAllDecisions(body.decisions || []);
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setLoadingAll(false);
    }
  };

  const resume = (lic, level) => act(
    () => api.codingRestore({ repo: lic.repo, principal: lic.principal || 'main', action_class: lic.action_class, level, reason: 'Reviewed the failure and resumed.' }),
    `${lic.label} resumed at L${level}.`,
  );
  const anyFrozen = (coding?.repos || []).some((r) => r.frozen);
  const freeze = (enabled) => act(() => api.codingFreeze('*', enabled),
    enabled ? 'Frozen: every action asks until you unfreeze.' : 'Unfrozen: earned licenses apply again.');
  const rewind = (turn) => act(() => api.codingRewind(turn.id), 'Repository rewound. The turn’s changes are kept in git stash.');

  const first = session?.name ? session.name.split(/\s+/)[0] : '';

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>{first ? `Hi ${first}` : 'Your coding agent'}</h1>
          <p>What your agent may do alone in each repository, earned from verified results.</p>
        </div>
        <div className="pl-actions">
          <button type="button" className={`btn btn-sm ${anyFrozen ? 'btn-ink' : 'btn-line'}`} disabled={busy}
            onClick={() => freeze(!anyFrozen)} title="Kill switch for every repository on this machine">
            {anyFrozen ? 'Unfreeze' : 'Freeze all'}
          </button>
          <Link to="/app/settings" className="btn btn-ghost btn-sm">Policy</Link>
        </div>
        {repos.length > 1 && (
          <select className="act-select" value={current} onChange={(e) => setRepo(e.target.value)} aria-label="Repository">
            {repos.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        )}
      </header>

      {error && <div className="pl-alert" role="alert"><p>{error}</p></div>}
      {anyFrozen && (
        <div className="pl-alert app-alert-row" role="alert">
          <p><b>Frozen.</b> Every action asks, whatever has been earned. Trust is kept and comes back when you unfreeze.</p>
          <button type="button" className="btn btn-ink btn-sm" disabled={busy} onClick={() => freeze(false)}>Unfreeze</button>
        </div>
      )}

      {paused.map((l) => (
        <div key={licenseKey(l)} className="pl-alert app-alert-row" role="alert">
          <p><b>{l.label} paused in {l.repo}.</b> {flaggedBy(coding?.events, l) || 'It failed a check'}, so it asks you again before every action of this kind.</p>
          <button type="button" className="btn btn-ink btn-sm" disabled={busy} onClick={() => resume(l, l.demoted_from)}>Resume at L{l.demoted_from}</button>
        </div>
      ))}

      {!repos.length && coding && <Start />}
      {repos.length > 0 && <Savings s={coding?.savings} />}

      {repos.length > 0 && (<>
      <section className="pl-section" aria-labelledby="h-lic">
        <h2 id="h-lic">What your agent may do alone{current ? ` in ${current}` : ''}</h2>
        {!licenses.length ? (
          <div className="pl-empty">Nothing yet. Open Claude Code in a repository with the plugin installed; every kind of action it tries appears here, starting at L0.</div>
        ) : (
          <div className="pl-grid">
            {licenses.map((l) => (
              <LicenseCard key={licenseKey(l)} lic={l} onResume={resume} busy={busy} flash={flash[licenseKey(l)]}
                flagged={flaggedBy(coding?.events, l)} />
            ))}
          </div>
        )}
      </section>

      <section className="pl-section" aria-labelledby="h-turns">
        <h2 id="h-turns">Turns, checked at the end</h2>
        <p className="pl-sub">Each request is checked once when the agent finishes: is the diff proportionate to what you asked, and do the tests pass? Only then do its changes count as evidence.</p>
        {!turns.length ? <div className="pl-empty">No turns yet.</div> : (
          <ul className="pl-list">
            {turns.map((t) => {
              const s = t.status === 'verified' && t.reason
                ? { label: 'Sent back, then verified', tone: 'ok' }
                : (TURN[t.status] || TURN.open);
              const date = toDate(t.created_at);
              const row = flagRow({ id: `t${t.id}`, target: { turn_id: t.id }, flagged: flagged.turns.has(t.id), flag, busy });
              const loop = loopBadge(looped.get(t.id));
              return (
                <li key={t.id} className="pl-row cd-turn">
                  <span className="pl-row-main">
                    <b>{t.prompt ? `“${t.prompt.slice(0, 120)}${t.prompt.length > 120 ? '…' : ''}”` : 'Turn without a prompt'}</b>
                    <small title={date ? date.toLocaleString() : undefined}>
                      {when(t.created_at)}
                      {t.files_changed != null ? ` · ${t.lines_changed} lines in ${t.files_changed} file${t.files_changed === 1 ? '' : 's'}` : ''}
                      {t.scope_score != null ? ` · scope ${t.scope_score}/5` : ''}
                      {t.tests && t.tests !== 'none' ? ` · tests ${t.tests}` : ''}
                    </small>
                    {t.reason && <pre className="cd-reason">{t.reason}</pre>}
                    {t.entire_checkpoint && (
                      <CopyCommand text={`entire checkpoint explain ${t.entire_checkpoint.slice(0, 12)}`} />
                    )}
                    <TurnLinks turn={t} />
                    <Told remediations={told.get(t.id) || []} />
                  </span>
                  <span className="pl-row-side">
                    {loop && <span className={`pl-status ${loop.tone}`} title={loop.title}>{loop.label}</span>}
                    <span className={`pl-status ${s.tone}`}>{s.label}</span>
                    {(t.status === 'failed' || t.status === 'blocked') && (
                      <button type="button" className="btn btn-line btn-sm" disabled={busy} onClick={() => rewind(t)}>Rewind</button>
                    )}
                    {row.button}
                  </span>
                  {row.below}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="pl-section" aria-labelledby="h-dec">
        <h2 id="h-dec">Every permission decision</h2>
        {allDecisions && <p className="pl-sub">Showing all {decisions.length} commands from this session. <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAllDecisions(null)}>Show latest only</button></p>}
        {!decisions.length ? <div className="pl-empty">No decisions yet.</div> : (
          <ul className="pl-list">
            {decisions.map((d) => {
              const s = DECISION[d.decision] || DECISION.ask;
              // A blocked action never ran, so there is nothing to call wrong.
              const row = d.decision === 'deny' ? {} : flagRow({
                id: `d${d.id}`, target: { decision_id: d.id }, flagged: flagged.decisions.has(d.id), flag, busy,
              });
              return (
                <li key={d.id} className="pl-row">
                  <span className="pl-row-main">
                    <b><code>{d.command}</code></b>
                    <small>{when(d.created_at)} · {classLabel(d.action_class)} at L{d.level} · {d.reason}
                      {isLink(d.neatlogs_link) && <> · <a className="hist-link" href={d.neatlogs_link} target="_blank" rel="noreferrer">Trace</a></>}
                    </small>
                  </span>
                  <span className="pl-row-side">
                    <span className={`pl-status ${s.tone}`}>{d.decided_by === 'person' ? 'You approved' : s.label}</span>
                    {d.outcome === 'failed' && <span className="pl-status bad">Failed</span>}
                    {d.outcome === 'verified' && <span className="pl-status ok">Verified</span>}
                    {row.button}
                  </span>
                  {row.below}
                </li>
              );
            })}
          </ul>
        )}
        {hasMore && (
          <p><button type="button" className="btn btn-line btn-sm" disabled={loadingAll} onClick={viewAll}>
            {loadingAll ? 'Loading…' : 'View all commands'}
          </button></p>
        )}
      </section>
      </>)}
    </div>
  );
}
