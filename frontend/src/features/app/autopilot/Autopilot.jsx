import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { moneyWhole } from '../../../lib/format.js';
import { levelCopy } from '../../../lib/copy.js';
import { jobIs, jobName, limitOf } from '../components/mission/derive.js';
import { Spotlight } from './Spotlight.jsx';
import './autopilot.css';

/** Reading time per step when auto-playing. */
const PAUSE_MS = 7000;
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
      where: () => ({ route: '/app', target: `[data-tour="job-${primary}"]` }),
      say: (d) => {
        const { state, ceiling } = classInfo(d, primary);
        const now = state.quarantined ? 'paused' : `set to “${levelCopy(state.effective_level, limitOf(ceiling)).short}”`;
        return `Your agent handles ${nameOf(d).toLowerCase()} for the shop. Right now it is ${now}. Each kind of job earns its own freedom from double-checked results — and loses it the moment something goes wrong.`;
      },
    },
    {
      id: 'inbox',
      title: 'Customer messages come in',
      where: () => ({ route: '/app/inbox', target: '[data-tour="inbox"]' }),
      say: () => 'These are real customer emails. For each one the agent reads it, finds the order (even from just the email address), checks the shop’s rules, acts only as far as its licence allows, and writes a reply that states only what was verified.',
      run: async (ctx) => {
        if ((ctx.data().tickets || []).some((t) => t.status === 'new')) {
          await ctx.call(() => api.handleNewTickets());
        }
      },
    },
    {
      id: 'baseline',
      title: 'Start with some earned freedom',
      where: () => ({ route: '/app', target: `[data-tour="job-${primary}"]` }),
      say: (d) => `For this demo, the agent is allowed to handle ${nameOf(d).toLowerCase()} up to ${limitOf(classInfo(d, primary).ceiling)} on its own. We also add a few sample orders so there is work to do.`,
      run: async (ctx) => {
        const { spec, state } = classInfo(ctx.data(), primary);
        // A practice problem left armed earlier would trip the "correct jobs"
        // step; start every tour from a clean slate.
        if (ctx.data().armed_faults?.[spec.key] && ctx.data().armed_faults[spec.key] !== 'none') {
          await ctx.call(() => api.arm('none', spec.key));
        }
        if (state.quarantined || state.effective_level < 2) {
          await ctx.call(() => api.restore(2, 'Guided demo baseline: start from an earned L2.', spec.key));
        }
        const open = ctx.data().orders.filter((o) => o.remaining > 0.5).length;
        if (open < 6) await ctx.call(() => api.topUp(spec.key, 6));
      },
    },
    {
      id: 'clean',
      title: 'Correct jobs earn more freedom',
      where: () => ({ route: '/app', target: '[data-tour="recent"]' }),
      say: (d) => {
        const { state } = classInfo(d, primary);
        const p = state.progress || {};
        const pct = (x) => `${(x * 100).toFixed(x < 0.01 ? 2 : 1)}%`;
        const why = p.target_rate != null && d.trust
          ? ` To move up it needs ${p.runs_needed} more: a mistake costs about $${Math.round(d.trust.incident_cost)}, so the next level only pays if fewer than ${pct(p.target_rate)} of jobs go wrong — and the record has to prove it.`
          : '';
        return `The agent now handles three real jobs. After each one we re-read the order to check the money actually moved. Only double-checked jobs count as evidence.${why}`;
      },
      run: async (ctx) => {
        const { spec, ceiling } = classInfo(ctx.data(), primary);
        const need = 3;
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
      },
    },
    {
      id: 'fault',
      title: 'Something goes wrong',
      where: () => ({ route: '/app', target: `[data-tour="paused-${primary}"]` }),
      say: () => 'We made the payment tool say “done” while changing nothing. The agent re-read the order, saw no money had moved, retried once with the same request key and checked again — so the customer still got their refund. But the tool could not be trusted, so this job type was paused at once.',
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
        const caught = result?.runs?.find((r) => r.task_class === spec.key && r.status === 'demoted');
        ctx.mem.demotedRun = caught?.id ?? result?.runs?.[0]?.id;
      },
    },
    {
      id: 'evidence',
      title: 'Paused right away',
      where: (d, mem) => ({ route: mem.demotedRun ? `/app/runs/${mem.demotedRun}` : '/app/runs', target: '[data-tour="what-happened"]' }),
      say: (d) => `${jobIs(nameOf(d))} now paused. The agent can only suggest until a person looks. This page shows what it meant to do, what really happened, and why it stopped.`,
    },
    {
      id: 'money',
      title: 'What the pause costs',
      where: () => ({ route: '/app/reports', target: '[data-tour="savings"]' }),
      say: (d, mem) => {
        const before = mem.savedBefore;
        const after = d.economics.net_saved_month;
        const delta = before !== undefined ? ` Estimated savings went from ${moneyWhole(before)} to ${moneyWhole(after)} a month.` : '';
        return `While paused, people check every job again, so you save less time.${delta} That is the trade: safety first, freedom earned back.`;
      },
    },
    {
      id: 'review',
      title: 'You decide what happens next',
      where: (d, mem) => ({ route: mem.demotedRun ? `/app/runs/${mem.demotedRun}` : '/app/runs', target: '[data-tour="resume"]' }),
      say: (d) => `Nothing runs on its own again until a person reads what happened and chooses how much freedom to give back. In the next step we choose “${levelCopy(2, limitOf(classInfo(d, primary).ceiling)).short}”.`,
    },
    {
      id: 'restore',
      title: 'A person resumes it',
      where: () => ({ route: '/app/ledger', target: '[data-tour="history"]' }),
      say: () => 'Resumed with limited freedom. Every change — who made it, when and why — is written into Permission history and into your code repository.',
      run: async (ctx) => {
        const { spec } = classInfo(ctx.data(), primary);
        await ctx.call(() => api.restore(
          2,
          `Reviewed run #${ctx.mem.demotedRun ?? '?'}: the problem was a practice problem from the guided demo. Resuming with limited freedom.`,
          spec.key,
        ));
      },
    },
    {
      id: 'close',
      title: 'That is the whole idea',
      where: () => ({ route: '/app', target: '[data-tour="jobs"]' }),
      say: (d) => {
        const others = d.task_classes.filter((t) => t.key !== primary)
          .map((t) => `${jobName(t)} kept its own level the whole time.`).join(' ');
        return `Freedom is earned job by job, taken away the moment something goes wrong, and every change is written down.${others ? ` ${others}` : ''}`;
      },
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
  const [focus, setFocus] = useState(null);
  const [wide, setWide] = useState(() => window.innerWidth >= 700);
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
    setFocus(null);
    const show = () => {
      const w = target.where?.(latest.current, mem.current);
      if (w) {
        navigate(w.route);
        setFocus(w.target);
      }
    };
    if (!target.run) { show(); return true; }
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
      show();
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
  const reset = () => { stop(); setIndex(-1); setError(''); setFocus(null); mem.current = {}; };

  useEffect(() => {
    const onResize = () => setWide(window.innerWidth >= 700);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

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
    <>
      {step && (
        <Spotlight
          selector={working ? null : focus}
          label={`Step ${index + 1} of ${script.length}`}
          title={step.title}
          text={step.say(data, mem.current)}
          busy={working}
          reserveRight={wide ? 420 : 0}
        />
      )}
      <aside className="ap" aria-label="1-minute demo">
        <header className="ap-head">
          <b>1-minute demo</b>
          <span className="pl-small pl-muted">{index >= 0 ? `Step ${index + 1} of ${script.length}` : `${script.length} steps`}</span>
          <button className="btn btn-ghost btn-sm" onClick={() => { reset(); setOpen(false); }} aria-label="Close demo">Close</button>
        </header>

        {index < 0 && (
          <p className="ap-intro">
            A short guided tour that uses this workspace for real. Each step opens the right
            screen and points at what matters. Practice problems are labelled as practice.
          </p>
        )}

        <ol className="ap-list">
          {script.map((s, i) => (
            <li key={s.id} className={i === index ? 'is-on' : i < index ? 'is-done' : ''}>
              <button type="button" disabled={working || playing} onClick={() => execute(i)}>
                <i>{i < index ? '✓' : i + 1}</i> {s.title}
              </button>
            </li>
          ))}
        </ol>
        {error && <p className="ap-error ap-intro">{error}</p>}

        <footer className="ap-foot">
          <button
            className="btn btn-ink btn-sm"
            disabled={working || playing || index >= script.length - 1}
            onClick={() => execute(index + 1)}
          >
            {index < 0 ? 'Start the tour' : 'Next step →'}
          </button>
          {playing ? (
            <button className="btn btn-line btn-sm" onClick={stop}>Pause</button>
          ) : (
            <button className="btn btn-line btn-sm" disabled={working} onClick={() => play(index + 1 >= script.length ? 0 : index + 1)}>
              Auto-play
            </button>
          )}
          <button className="btn btn-ghost btn-sm" disabled={working} onClick={reset}>Start over</button>
        </footer>
      </aside>
    </>
  );
}
