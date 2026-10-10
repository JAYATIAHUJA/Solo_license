import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useStore } from '../../../lib/store.jsx';
import { classMeta, when } from '../../../lib/format.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { ClassPicker, ClassTag, Empty, PageHeader, Panel } from '../components/Bits.jsx';

const KIND_ICON = { promote: 'arrow-up-right', demote: 'bolt', restore: 'refresh' };

function CopySha({ sha }) {
  const [copied, setCopied] = useState(false);
  const cmd = `git show ${sha}`;
  return (
    <button
      type="button"
      className="mc-sha mono"
      title={`Copy “${cmd}”`}
      onClick={() => navigator.clipboard?.writeText(cmd).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {})}
    >
      <HandIcon name={copied ? 'check' : 'commit'} size={12} /> {copied ? 'copied' : `commit ${sha.slice(0, 7)}`}
    </button>
  );
}

export function Ledger() {
  const { data } = useStore();
  const [cls, setCls] = useState('all');
  const classes = useMemo(() => (data.task_classes || []).map((c) => ({ key: c.key, label: c.label })), [data.task_classes]);
  const events = data.events.filter((e) => cls === 'all' || (e.task_class || 'refund') === cls);
  const ledger = data.observability?.ledger;
  const sample = data.events.find((e) => e.git_sha)?.git_sha?.slice(0, 7) || '<sha>';

  return (
    <>
      <PageHeader eyebrow="Ledger" title={<>How trust was <em className="italic">earned & lost.</em></>}>
        Every promotion, demotion and restore is a row here and a commit in <code className="mono">ledger/license_ledger.jsonl</code>
        {ledger ? <> — {ledger.commits} commit{ledger.commits === 1 ? '' : 's'} so far.</> : '.'}
      </PageHeader>

      <aside className="mc-inspect">
        <span className="app-kicker"><HandIcon name="search" size={12} /> Inspect any commit yourself</span>
        <code className="mono">git -C {ledger?.repo ? `"${ledger.repo}"` : '<ledger repo>'} show {sample}</code>
        <code className="mono">entire checkpoint explain {sample}</code>
        <span className="app-small muted">Click a commit below to copy its <code className="mono">git show</code> command.</span>
      </aside>

      <Panel title={`${events.length} change${events.length === 1 ? '' : 's'}`} icon="commit" aside={classes.length > 1 ? <ClassPicker classes={classes} value={cls} onChange={setCls} allowAll label="Filter by task class" /> : null}>
        {events.length === 0 ? <Empty icon="ledger" title="Nothing yet">Promotions and demotions are recorded as they happen.</Empty> : (
          <ol className="app-timeline">
            {events.map((e, i) => (
              <motion.li key={e.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 12) * 0.04 }} className={`is-${e.kind}`}>
                <span className="app-timeline-node"><HandIcon name={KIND_ICON[e.kind] || 'commit'} size={16} /></span>
                <div className="app-timeline-body">
                  <div className="app-timeline-top">
                    <b className="serif">{e.kind} · L{e.from_level} → L{e.to_level}</b>
                    <span className="muted app-small">{when(e.created_at)}</span>
                  </div>
                  <p><ClassTag label={classMeta(data, e.task_class || 'refund').label} /> {e.reason}</p>
                  <div className="app-timeline-meta mono">
                    {e.git_sha ? <CopySha sha={e.git_sha} /> : <span className="muted">no git commit</span>}
                    {e.run_id && <Link to={`/app/runs/${e.run_id}`}>run #{e.run_id} →</Link>}
                    {e.actor_id && <span className="muted">by {e.actor_id}</span>}
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
