import { Link } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { LEVELS, money, when } from '../../../lib/format.js';
import { LevelStepper } from '../../../components/domain/LevelStepper.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Empty, PageHeader, Panel, StatusMark } from '../components/Bits.jsx';
import { RestorePanel } from '../components/RestorePanel.jsx';

const KIND_ICON = { promote: 'arrow-up-right', demote: 'bolt', restore: 'refresh' };

/* Hierarchy, top to bottom: where the agent stands (focal) → what needs a
   human → the numbers → the history. */
export function Overview() {
  const { data } = useStore();
  const { license, stats, runs, config, settings, events } = data;
  const pending = runs.filter((r) => r.status === 'pending_approval');
  const suggested = runs.filter((r) => r.status === 'suggested').slice(0, 3);
  const level = LEVELS[license.effective_level];
  const toNext = Math.max(0, config.promotion_clean_runs - license.clean_runs);
  const todo = pending.length + (license.quarantined ? 1 : 0);

  const status = license.quarantined
    ? 'A detection fired. It can only suggest until you review the evidence and restore it.'
    : license.level >= 3
      ? 'Full autonomy. Every run is sampled for audit.'
      : `${toNext} more clean run${toNext === 1 ? '' : 's'} to reach L${license.level + 1}.`;

  return (
    <>
      <PageHeader
        eyebrow={`${settings.business_name} · refund`}
        title="Overview"
        actions={<Link to="/app/agent" className="btn btn-ink btn-sm"><HandIcon name="message" size={14} /> Open agent desk</Link>}
      />

      <div className="ov-top">
        <section className={`ov-status ${license.quarantined ? 'is-q' : ''}`}>
          <div className="ov-status-head">
            <span className="app-kicker">Autonomy now</span>
            <span className={`ov-pill ${license.quarantined ? 'is-alert' : ''}`}>
              <i /> {license.quarantined ? 'Quarantined' : 'Live'}
            </span>
          </div>
          <div className="ov-status-main">
            <b className="ov-level serif">{level.code}</b>
            <div>
              <p className="ov-level-name serif">{license.quarantined ? 'Suggest only' : level.name}</p>
              <p className="ov-level-note">{status}</p>
            </div>
          </div>
          <LevelStepper
            level={license.effective_level}
            cleanRuns={license.clean_runs}
            threshold={config.promotion_clean_runs}
            quarantined={license.quarantined}
            demotedFrom={license.demoted_from}
          />
        </section>

        <Panel title="Needs you" icon="flag" count={todo} tone="raised" className="ov-needs">
          {license.quarantined && (
            <Link to={data.runs.find((r) => r.status === 'demoted') ? `/app/runs/${data.runs.find((r) => r.status === 'demoted').id}` : '/app/runs'} className="ov-task is-alert">
              <HandIcon name="warn" size={16} />
              <span><b>Review the evidence and restore</b><small>The class fell from L{license.demoted_from ?? '?'}.</small></span>
              <HandIcon name="arrow-right" size={14} />
            </Link>
          )}
          {pending.slice(0, 4).map((r) => (
            <Link key={r.id} to={`/app/runs/${r.id}`} className="ov-task">
              <HandIcon name="check" size={16} />
              <span><b>Approve {money(r.requested_amount)} on {r.order_id}</b><small>Held for a human · {when(r.created_at)}</small></span>
              <HandIcon name="arrow-right" size={14} />
            </Link>
          ))}
          {todo === 0 && (
            <div className="ov-clear">
              <p className="serif">Nothing waiting on you.</p>
              <p className="app-small muted">
                {license.effective_level === 0 && suggested.length
                  ? <>At L0 you can execute a suggestion to earn credit — <Link to={`/app/runs/${suggested[0].id}`}>open the latest</Link>.</>
                  : `Drafts land here at L1, or at L2 above ${money(config.l2_auto_refund_ceiling)}.`}
              </p>
            </div>
          )}
        </Panel>
      </div>

      {license.quarantined && <div className="app-block"><RestorePanel /></div>}

      <section className="app-stats">
        <div><span className="app-kicker">Runs</span><b className="serif">{stats.total_runs}</b></div>
        <div><span className="app-kicker">Clean</span><b className="serif">{stats.clean_runs}</b></div>
        <div><span className="app-kicker">Demotions</span><b className="serif">{stats.demotions}</b></div>
        <div><span className="app-kicker">Refunded</span><b className="serif">{money(stats.refunded_total)}</b></div>
      </section>

      <div className="app-cols">
        <Panel title="Latest runs" icon="eye" count={runs.length} aside={<Link className="app-link" to="/app/runs">All runs →</Link>}>
          {runs.length === 0 ? (
            <Empty icon="message" title="No runs yet" action={<Link to="/app/agent" className="btn btn-ink btn-sm">Run your first refund</Link>}>
              Paste a customer message in the agent desk and the agent takes it from there.
            </Empty>
          ) : (
            <table className="app-table">
              <thead><tr><th>Run</th><th>Order</th><th className="num">Amount</th><th>Level</th><th>Status</th><th className="num">When</th></tr></thead>
              <tbody>
                {runs.slice(0, 7).map((r) => (
                  <tr key={r.id} className="is-link">
                    <td><Link to={`/app/runs/${r.id}`} className="mono">#{r.id}</Link></td>
                    <td className="mono">{r.order_id}</td>
                    <td className="num">{money(r.requested_amount)}</td>
                    <td className="mono">L{r.level_at_run}</td>
                    <td><StatusMark status={r.status} /></td>
                    <td className="num muted">{when(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="License changes" icon="commit" count={events.length} aside={<Link className="app-link" to="/app/ledger">Ledger →</Link>}>
          {events.length === 0 ? <p className="app-small muted">No promotions or demotions yet. They appear here — and as git commits — the moment they happen.</p> : (
            <ol className="ov-events">
              {events.slice(0, 6).map((e) => (
                <li key={e.id} className={`is-${e.kind}`}>
                  <span className="ov-event-node"><HandIcon name={KIND_ICON[e.kind] || 'commit'} size={12} /></span>
                  <span><b>{e.kind}</b> L{e.from_level} → L{e.to_level}</span>
                  <span className="muted">{when(e.created_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </>
  );
}
