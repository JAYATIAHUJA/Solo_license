import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useStore } from '../../../lib/store.jsx';
import { when } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { Empty, PageHeader, Panel } from '../components/Bits.jsx';

const KIND_ICON = { promote: 'arrow-up-right', demote: 'bolt', restore: 'refresh' };

export function Ledger() {
  const { data } = useStore();
  return (
    <>
      <PageHeader eyebrow="Ledger" title={<>How trust was <em className="italic">earned & lost.</em></>}>
        Every promotion, demotion and restore is a row here and a commit in <code className="mono">ledger/license_ledger.jsonl</code>.
      </PageHeader>
      <Panel title={`${data.events.length} changes`} icon="commit">
        {data.events.length === 0 ? <Empty icon="ledger" title="Nothing yet">Promotions and demotions are recorded as they happen.</Empty> : (
          <ol className="app-timeline">
            {data.events.map((e, i) => (
              <motion.li key={e.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className={`is-${e.kind}`}>
                <span className="app-timeline-node"><HandIcon name={KIND_ICON[e.kind] || 'commit'} size={16} /></span>
                <div className="app-timeline-body">
                  <div className="app-timeline-top">
                    <b className="serif">{e.kind} · L{e.from_level} → L{e.to_level}</b>
                    <span className="muted app-small">{when(e.created_at)}</span>
                  </div>
                  <p>{e.reason}</p>
                  <div className="app-timeline-meta mono">
                    {e.git_sha ? <span>commit {e.git_sha.slice(0, 7)}</span> : <span className="muted">no git commit</span>}
                    {e.run_id && <Link to={`/app/runs/${e.run_id}`}>run #{e.run_id} →</Link>}
                  </div>
                </div>
              </motion.li>
            ))}
          </ol>
        )}
      </Panel>
    </>
  );
}
