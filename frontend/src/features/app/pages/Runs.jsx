import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { money, when } from '../../../lib/format.js';
import { Empty, PageHeader, Panel, StatusMark } from '../components/Bits.jsx';
import { EvidencePacket } from '../components/EvidencePacket.jsx';
import { RestorePanel } from '../components/RestorePanel.jsx';
import { ApproveBar } from '../components/ApproveBar.jsx';

const FILTERS = [
  ['all', 'All'],
  ['pending_approval', 'Awaiting'],
  ['demoted', 'Demoted'],
  ['clean', 'Clean'],
  ['suggested', 'Suggested'],
];

export function Runs() {
  const { data, load } = useStore();
  const { runId } = useParams();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const selected = Number(runId) || data.runs[0]?.id;

  useEffect(() => {
    if (selected && data.packet?.run?.id !== selected) load(selected);
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = data.runs.filter((r) => filter === 'all' || r.status === filter);
  const packet = data.packet?.run?.id === selected ? data.packet : null;

  return (
    <>
      <PageHeader eyebrow="Runs & evidence" title={<>Every run, <em className="italic">on the record.</em></>}>
        Pick a run to read its evidence packet: what was asked, what the license allowed, what the tool claimed, and what the database actually shows.
      </PageHeader>

      {data.license.quarantined && <div className="app-block"><RestorePanel /></div>}

      <div className="app-cols app-cols-runs">
        <Panel title="Runs" icon="layers" count={data.runs.length} className="app-run-list">
          <div className="app-filters">
            {FILTERS.map(([id, label]) => (
              <button key={id} className={filter === id ? 'is-on' : ''} onClick={() => setFilter(id)}>{label}</button>
            ))}
          </div>
          {list.length === 0 ? <Empty icon="eye" title="Nothing here">{data.runs.length ? 'Try another filter.' : <Link to="/app/agent">Run the agent first.</Link>}</Empty> : (
            <ul className="app-runs">
              {list.map((r) => (
                <li key={r.id}>
                  <button className={r.id === selected ? 'is-on' : ''} onClick={() => navigate(`/app/runs/${r.id}`)}>
                    <span className="mono">#{r.id}</span>
                    <span><b>{r.order_id}</b> <span className="muted">{money(r.requested_amount)}</span></span>
                    <StatusMark status={r.status} />
                    <span className="muted app-small">L{r.level_at_run} · {when(r.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Evidence packet" icon="eye">
          {!packet ? <Empty icon="eye" title={selected ? 'Loading…' : 'No run selected'} /> : (
            <>
              <EvidencePacket packet={packet} />
              <ApproveBar run={packet.run} onDone={(id) => navigate(`/app/runs/${id}`)} />
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
