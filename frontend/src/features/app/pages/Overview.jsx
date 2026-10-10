import { Link } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, money, when } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { ClassTag, Empty, PageHeader, Panel, StatusMark, WarningBanner } from '../components/Bits.jsx';
import { RestorePanels } from '../components/RestorePanel.jsx';
import { ApproveBar, approveBlocker } from '../components/ApproveBar.jsx';
import { AutonomyDial } from '../components/mission/AutonomyDial.jsx';
import { StatusChips } from '../components/mission/StatusChips.jsx';
import { SavingsMeter } from '../components/mission/SavingsMeter.jsx';
import { ProofStrip } from '../components/mission/ProofStrip.jsx';
import { TrustTimeline } from '../components/mission/TrustTimeline.jsx';
import { classCards } from '../components/mission/derive.js';

/* Mission control, top to bottom: where every class stands (dials) → what
   needs a human → what trust is worth (cfo) and the proof it's verified →
   how trust moved over time → the raw runs. */
export function Overview() {
  const { data } = useStore();
  const { runs, config, settings } = data;
  const cards = classCards(data);
  const threshold = config.promotion_clean_runs;
  const quarantined = cards.filter((c) => c.license.quarantined);
  const pending = runs.filter((r) => r.status === 'pending_approval');
  const suggested = runs.filter((r) => r.status === 'suggested' && !data.licenses?.[r.task_class]?.quarantined).slice(0, 3);
  const queue = [...pending.slice(0, 6), ...suggested];
  const todo = pending.length + quarantined.length + suggested.length;

  return (
    <>
      <PageHeader
        eyebrow={`${settings.business_name || 'Workspace'} · ${cards.length} licensed task class${cards.length === 1 ? '' : 'es'}`}
        title={<>Mission <em className="italic">control.</em></>}
        actions={(
          <>
            <Link to="/app/license" className="btn btn-line btn-sm"><HandIcon name="shield" size={14} /> Licenses</Link>
            <Link to="/app/agent" className="btn btn-ink btn-sm"><HandIcon name="message" size={14} /> Agent desk</Link>
          </>
        )}
      />
      <StatusChips observability={data.observability} />
      <WarningBanner warnings={data.warnings} />

      <section className="mc-dials" aria-label="Autonomy per task class">
        {cards.map((card) => <AutonomyDial key={card.key} card={card} threshold={threshold} />)}
      </section>

      <RestorePanels />

      <div className="mc-row">
        <Panel title="Needs you" icon="flag" count={todo} tone="raised" className="ov-needs mc-needs">
          {quarantined.map((c) => {
            const ev = runs.find((r) => r.task_class === c.key && r.status === 'demoted');
            return (
              <Link key={c.key} to={ev ? `/app/runs/${ev.id}` : '/app/runs'} className="ov-task is-alert">
                <HandIcon name="warn" size={16} />
                <span><b>{c.meta.label} quarantined — review & restore</b><small>Fell from L{c.license.demoted_from ?? '?'}{ev ? ` on run #${ev.id}` : ''}. Restore panel above.</small></span>
                <HandIcon name="arrow-right" size={14} />
              </Link>
            );
          })}
          {queue.map((r) => {
            const meta = classMeta(data, r.task_class);
            const blocked = approveBlocker(data, r);
            return (
              <div key={r.id} className="ov-task mc-task">
                <HandIcon name={r.status === 'suggested' ? 'spark' : 'check'} size={16} />
                <span>
                  <b><Link to={`/app/runs/${r.id}`}>{meta.label} {money(r.requested_amount)} · {r.order_id}</Link></b>
                  <small>{r.status === 'suggested' ? 'L0 suggestion' : 'Held for a human'} · {when(r.created_at)}{blocked ? ` · ${blocked}` : ''}</small>
                </span>
                <ApproveBar run={r} compact />
              </div>
            );
          })}
          {todo === 0 && (
            <div className="ov-clear">
              <p className="serif">Nothing waiting on you.</p>
              <p className="app-small muted">Drafts land here at L1, or at L2 above each class’s ceiling ({cards.map((c) => `${c.meta.label.toLowerCase()} ${money(c.ceiling)}`).join(', ')}).</p>
            </div>
          )}
        </Panel>

        <SavingsMeter economics={data.economics} classes={cards} />
      </div>

      <ProofStrip data={data} />

      <Panel title="Trust over time" icon="layers" aside={<Link className="app-link" to="/app/ledger">Ledger →</Link>} className="app-block mc-block">
        <TrustTimeline data={data} />
      </Panel>

      <Panel title="Latest runs" icon="eye" count={runs.length} aside={<Link className="app-link" to="/app/runs">All runs →</Link>} className="mc-block">
        {runs.length === 0 ? (
          <Empty icon="message" title="No runs yet" action={<Link to="/app/agent" className="btn btn-ink btn-sm">Hand the agent its first task</Link>}>
            Paste a customer message in the agent desk and the agent takes it from there.
          </Empty>
        ) : (
          <div className="mc-table-wrap">
            <table className="app-table">
              <thead><tr><th>Run</th><th>Class</th><th>Order</th><th className="num">Amount</th><th>Level</th><th>Status</th><th className="num">When</th></tr></thead>
              <tbody>
                {runs.slice(0, 8).map((r) => (
                  <tr key={r.id} className="is-link">
                    <td><Link to={`/app/runs/${r.id}`} className="mono">#{r.id}</Link></td>
                    <td><ClassTag label={classMeta(data, r.task_class).label} /></td>
                    <td className="mono">{r.order_id}</td>
                    <td className="num">{money(r.requested_amount)}</td>
                    <td className="mono">L{r.level_at_run}</td>
                    <td><StatusMark status={r.status} /></td>
                    <td className="num muted">{when(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
