import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, money, when } from '../../../lib/format.js';
import { ClassPicker, ClassTag, Empty, PageHeader, Panel, StatusMark } from '../components/Bits.jsx';
import { EvidencePacket } from '../components/EvidencePacket.jsx';
import { RestorePanels } from '../components/RestorePanel.jsx';
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
  const [cls, setCls] = useState('all');
  const selected = Number(runId) || data.runs[0]?.id;
  const classes = useMemo(() => (data.task_classes || []).map((c) => ({ key: c.key, label: c.label })), [data.task_classes]);

  useEffect(() => {
    if (selected && data.packet?.run?.id !== selected) load(selected);
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = data.runs.filter((r) => (filter === 'all' || r.status === filter) && (cls === 'all' || r.task_class === cls));
  const packet = data.packet?.run?.id === selected ? data.packet : null;

  return (
    <>
      <PageHeader eyebrow="Runs & evidence" title={<>Every run, <em className="italic">on the record.</em></>}>
        Pick a run to read its evidence packet: what was asked, what the license allowed, what the tool claimed, and what the database actually shows.
      </PageHeader>

      <RestorePanels />

      <div className="app-cols app-cols-runs">
        <Panel title="Runs" icon="layers" count={list.length} className="app-run-list">
          {classes.length > 1 && <ClassPicker classes={classes} value={cls} onChange={setCls} allowAll label="Filter by task class" />}
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
                    <span className="muted app-small mc-run-meta"><ClassTag label={classMeta(data, r.task_class).label} /> L{r.level_at_run} · {when(r.created_at)}{r.fault_mode && r.fault_mode !== 'none' ? ' · fault' : ''}</span>
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
