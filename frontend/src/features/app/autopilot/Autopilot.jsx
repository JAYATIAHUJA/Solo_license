import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { moneyWhole } from '../../../lib/format.js';
import { levelCopy } from '../../../lib/copy.js';
import { jobIs, jobName, limitOf } from '../components/mission/derive.js';
import './autopilot.css';

const PAUSE_MS = 2600;
/** Each demo action is a new request; without a fresh key a replayed demo
 *  would (correctly) be caught as a duplicate action. */
const demoKey = () => `demo:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 10)}`;
const sleep = (ms) => new Promise((resolve) => { window.setTimeout(resolve, ms); });

/** Pick an order with balance left, sized under the class's L2 ceiling. */
function pickOrder(data, ceiling, skip = new Set()) {
  const open = data.orders
    .filter((o) => o.remaining > 0.5 && !skip.has(o.order_id))
    .sort((a, b) => b.remaining - a.remaining);
  const order = open[0];
  if (!order) return null;
  const amount = Math.max(1, Math.min(order.remaining, Math.floor(ceiling * 0.4)));
  return { order_id: order.order_id, amount: Number(amount.toFixed(2)) };
}

function classInfo(data, key) {
  const spec = data.task_classes.find((t) => t.key === key) || data.task_classes[0];
  return { spec, state: data.licenses[spec.key], ceiling: data.config.ceilings[spec.key] };
}

/** The 1-minute demo: a narrated, real run of the whole product loop against
 *  the live API. Nothing is simulated — every step calls the same endpoints a
 *  person would, so history and numbers are genuine. Practice problems are
 *  labelled as practice in the run record. */
function buildScript(primary) {
  const nameOf = (d) => jobName(classInfo(d, primary).spec);
  return [
    {
      id: 'intro',
      title: 'Meet your agent',
      say: (d) => {
        const { state, ceiling } = classInfo(d, primary);
        const now = state.quarantined ? 'paused' : `set to “${levelCopy(state.effective_level, limitOf(ceiling)).short}”`;
        return `Your agent handles ${nameOf(d).toLowerCase()} for the shop. Right now it is ${now}. Each kind of job earns its own freedom, one correct job at a time.`;
      },
    },
    {
      id: 'baseline',
      title: 'Start with some earned freedom',
      say: (d) => `For this demo, the agent is allowed to handle ${nameOf(d).toLowerCase()} up to ${limitOf(classInfo(d, primary).ceiling)} on its own. We also add a few sample orders so there is work to do.`,
      run: async (ctx) => {
        const { spec, state } = classInfo(ctx.data(), primary);
        if (state.quarantined || state.effective_level < 2) {
          await ctx.call(() => api.restore(2, 'Guided demo baseline: start from an earned L2.', spec.key));
        }
        const open = ctx.data().orders.filter((o) => o.remaining > 0.5).length;
        if (open < 6) await ctx.call(() => api.topUp(spec.key, 6));
        ctx.go('/app');
      },
    },
    {
      id: 'clean',
      title: 'Correct jobs earn more freedom',
      say: (d) => {
        const { state } = classInfo(d, primary);
        const need = state.level >= 3 ? 1 : Math.max(1, d.config.promotion_clean_runs - state.clean_runs);
        return `The agent now handles ${need} real job${need > 1 ? 's' : ''}. After each one we re-read the order to double-check the money actually moved. Only double-checked jobs count toward more freedom.`;
      },
      run: async (ctx) => {
        const { spec, state, ceiling } = classInfo(ctx.data(), primary);
        const need = state.level >= 3 ? 1 : Math.max(1, ctx.data().config.promotion_clean_runs - state.clean_runs);
        const used = new Set();
        for (let i = 0; i < need; i += 1) {
          let pick = pickOrder(ctx.data(), ceiling, used);
          if (!pick) {
            await ctx.call(() => api.topUp(spec.key, 4));
            pick = pickOrder(ctx.data(), ceiling, used);
          }
          if (!pick) break;
          used.add(pick.order_id);
          await ctx.call(() => api.runAction({ ...pick, reason: `Guided demo clean run ${i + 1}`, task_class: spec.key, idempotency_key: demoKey() }));
          await sleep(700);
        }
        ctx.go('/app');
      },
    },
    {
      id: 'fault',
      title: 'Something goes wrong',
      say: () => 'We make the payment tool pretend it worked while changing nothing. The agent believes it is done, but the double-check sees that the money never moved.',
      run: async (ctx) => {
        const { spec, ceiling } = classInfo(ctx.data(), primary);
        ctx.mem.savedBefore = ctx.data().economics.net_saved_month;
        await ctx.call(() => api.arm('quiet_failure', spec.key));
        let pick = pickOrder(ctx.data(), ceiling);
        if (!pick) {
          await ctx.call(() => api.topUp(spec.key, 4));
          pick = pickOrder(ctx.data(), ceiling);
        }
        const result = await ctx.call(() => api.runAction({ ...pick, reason: 'Guided demo: injected quiet failure', task_class: spec.key, idempotency_key: demoKey() }));
        const runId = result?.runs?.[0]?.id;
        ctx.mem.demotedRun = runId;
        if (runId) ctx.go(`/app/runs/${runId}`);
      },
    },
    {
      id: 'evidence',
      title: 'Paused right away',
      say: (d) => `${jobIs(nameOf(d))} now paused. The agent can only suggest until a person looks. This page shows what it meant to do, what really happened, and why it stopped.`,
    },
    {
      id: 'money',
      title: 'What the pause costs',
      say: (d, mem) => {
        const before = mem.savedBefore;
        const after = d.economics.net_saved_month;
        const delta = before !== undefined ? ` Estimated savings went from ${moneyWhole(before)} to ${moneyWhole(after)} a month.` : '';
        return `While paused, people check every job again, so you save less time.${delta} That is the trade: safety first, freedom earned back.`;
      },
      run: async (ctx) => ctx.go('/app/reports'),
    },
    {
      id: 'restore',
      title: 'A person resumes it',
      say: () => 'A person reviews what happened and gives back some freedom — not all of it. The decision and the reason are saved in History.',
      run: async (ctx) => {
        const { spec } = classInfo(ctx.data(), primary);
        await ctx.call(() => api.restore(
          2,
          `Reviewed run #${ctx.mem.demotedRun ?? '?'}: the problem was a practice problem from the guided demo. Resuming with limited freedom.`,
          spec.key,
        ));
        ctx.go('/app/ledger');
      },
    },
    {
      id: 'close',
      title: 'That is the whole idea',
      say: (d) => {
        const others = d.task_classes.filter((t) => t.key !== primary)
          .map((t) => `${jobName(t)} kept its own level the whole time.`).join(' ');
        return `Freedom is earned job by job, taken away the moment something goes wrong, and every change is written down.${others ? ` ${others}` : ''}`;
      },
      run: async (ctx) => ctx.go('/app'),
    },
  ];
}

/** Open the demo panel from anywhere (e.g. the Home page button). */
export function openDemo() {
  window.dispatchEvent(new Event('solo-demo-open'));
}

export function Autopilot() {
  const { data, run } = useStore();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(-1);
  const [working, setWorking] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const latest = useRef(data);
  const mem = useRef({});
  const playingRef = useRef(false);
  useEffect(() => { latest.current = data; }, [data]);

  const primary = data?.task_classes?.[0]?.key;
  const script = primary ? buildScript(primary) : [];
  const step = script[index];

  const execute = useCallback(async (i) => {
    const target = script[i];
    if (!target) return false;
    setIndex(i);
    setError('');
    if (!target.run) return true;
    setWorking(true);
    try {
      const ctx = {
        data: () => latest.current,
        mem: mem.current,
        go: (path) => navigate(path),
        call: async (fn) => {
          const result = await run(fn);
          if (!result) throw new Error('A step failed — see the message above.');
          latest.current = result;
          return result;
        },
      };
      await target.run(ctx);
      return true;
    } catch (cause) {
      setError(cause.message);
      return false;
    } finally {
      setWorking(false);
    }
  }, [navigate, run, script]);

  const play = useCallback(async (from) => {
    playingRef.current = true;
    setPlaying(true);
    for (let i = from; i < script.length && playingRef.current; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      const ok = await execute(i);
      if (!ok) break;
      // eslint-disable-next-line no-await-in-loop
      if (i < script.length - 1) await sleep(PAUSE_MS);
    }
    playingRef.current = false;
    setPlaying(false);
  }, [execute, script.length]);

  const stop = () => { playingRef.current = false; setPlaying(false); };
  const reset = () => { stop(); setIndex(-1); setError(''); mem.current = {}; };

  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener('solo-demo-open', show);
    return () => window.removeEventListener('solo-demo-open', show);
  }, []);

  useEffect(() => {
    document.body.classList.toggle('demo-open', open);
    return () => document.body.classList.remove('demo-open');
  }, [open]);

  if (!data || !primary || !open) return null;

  return (
    <aside className="ap" aria-label="1-minute demo">
      <header className="ap-head">
        <b>1-minute demo</b>
        <span className="pl-small pl-muted">{index >= 0 ? `Step ${index + 1} of ${script.length}` : `${script.length} steps`}</span>
        <button className="btn btn-ghost btn-sm" onClick={() => { stop(); setOpen(false); }} aria-label="Close demo">Close</button>
      </header>

      <div className="ap-say" aria-live="polite">
        {step ? (
          <>
            <h3>{step.title}</h3>
            <p>{step.say(data, mem.current)}</p>
          </>
        ) : (
          <>
            <h3>See the whole idea in about a minute</h3>
            <p>
              The demo uses this workspace for real: the agent does a few jobs, earns freedom,
              hits a practice problem, gets paused, and a person resumes it. Practice problems
              are labelled as practice in your history.
            </p>
          </>
        )}
        {working && <p className="pl-muted ap-working">Working…</p>}
        {error && <p className="ap-error">{error}</p>}
      </div>

      <details className="pl-more ap-steps-wrap">
        <summary>All steps</summary>
        <ol className="ap-steps">
          {script.map((s, i) => (
            <li key={s.id} className={i === index ? 'is-on' : i < index ? 'is-done' : ''}>
              <button type="button" disabled={working || playing} onClick={() => execute(i)}>
                <i>{i + 1}</i> {s.title}
              </button>
            </li>
          ))}
        </ol>
      </details>

      <footer className="ap-foot">
        {playing ? (
          <button className="btn btn-line btn-sm" onClick={stop}>Pause</button>
        ) : (
          <button className="btn btn-ink btn-sm" disabled={working} onClick={() => play(index + 1 >= script.length ? 0 : index + 1)}>
            {index < 0 ? 'Start the demo' : index + 1 >= script.length ? 'Play again' : 'Continue'}
          </button>
        )}
        <button
          className="btn btn-line btn-sm"
          disabled={working || playing || index >= script.length - 1}
          onClick={() => execute(index + 1)}
        >
          Next step
        </button>
        <button className="btn btn-ghost btn-sm" disabled={working} onClick={reset}>Start over</button>
      </footer>
    </aside>
  );
}
