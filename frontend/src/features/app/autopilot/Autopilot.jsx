import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { money } from '../../../lib/format.js';
import './autopilot.css';

const PAUSE_MS = 2600;
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

/** The guided demo: a narrated, real run of the whole product loop against the
 *  live API. Nothing is simulated — every step calls the same endpoints a user
 *  would, so traces, ledger commits and economics are genuine. Injected faults
 *  are labelled as injected in the run record. */
function buildScript(primary) {
  return [
    {
      id: 'intro',
      tool: 'Solo License',
      title: 'An agent on a license',
      say: (d) => {
        const { spec, state } = classInfo(d, primary);
        return `The ${spec.label.toLowerCase()} agent currently holds L${state.effective_level}. It only acts alone at L2+, and only under the $${classInfo(d, primary).ceiling} ceiling. Every other class keeps its own, separate license.`;
      },
    },
    {
      id: 'baseline',
      tool: 'Setup',
      title: 'Start from an earned L2',
      say: () => 'If the class is quarantined or below L2 we restore it to L2 (logged as a guided-demo restore) and top up demo orders so there is work to do.',
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
      tool: 'neatlogs',
      title: 'Clean runs earn the next rung',
      say: (d) => {
        const { state } = classInfo(d, primary);
        const need = state.level >= 3 ? 1 : Math.max(1, d.config.promotion_clean_runs - state.clean_runs);
        return `Running ${need} real action${need > 1 ? 's' : ''}. Each one opens a neatlogs trace (license.check → plan → tool → verify.readback). The tool's "success" is ignored; the verifier reads SQLite back and only a matching delta counts as clean.`;
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
          await ctx.call(() => api.runAction({ ...pick, reason: `Guided demo clean run ${i + 1}`, task_class: spec.key }));
          await sleep(700);
        }
        ctx.go('/app');
      },
    },
    {
      id: 'fault',
      tool: 'neatlogs',
      title: 'A quiet failure: the tool lies',
      say: () => 'We arm a quiet failure: the next tool call reports "Processed" but writes nothing. Watch the read-back catch it — state_mismatch fires and the dial crashes to L0 + quarantine.',
      run: async (ctx) => {
        const { spec, ceiling } = classInfo(ctx.data(), primary);
        ctx.mem.savedBefore = ctx.data().economics.net_saved_month;
        await ctx.call(() => api.arm('quiet_failure', spec.key));
        let pick = pickOrder(ctx.data(), ceiling);
        if (!pick) {
          await ctx.call(() => api.topUp(spec.key, 4));
          pick = pickOrder(ctx.data(), ceiling);
        }
        const result = await ctx.call(() => api.runAction({ ...pick, reason: 'Guided demo: injected quiet failure', task_class: spec.key }));
        const runId = result?.runs?.[0]?.id;
        ctx.mem.demotedRun = runId;
        if (runId) ctx.go(`/app/runs/${runId}`);
      },
    },
    {
      id: 'evidence',
      tool: 'neatlogs',
      title: 'One evidence packet',
      say: () => 'This is the packet a human reviews: intended vs verified delta, the detection, every span, and the git-backed license history. With a neatlogs key it links straight to the trace.',
    },
    {
      id: 'money',
      tool: 'cfo model',
      title: 'Autonomy is a margin driver',
      say: (d, mem) => {
        const before = mem.savedBefore;
        const after = d.economics.net_saved_month;
        const delta = before !== undefined ? ` — net savings moved from ${money(before)} to ${money(after)} per month` : '';
        return `Back at L0 a human reviews every action again, so supervision cost jumps${delta}. The incident rate in this model is measured from real runs, not assumed.`;
      },
      run: async (ctx) => ctx.go('/app'),
    },
    {
      id: 'restore',
      tool: 'Entire',
      title: 'Human restores with judgement',
      say: () => 'A human read the packet, confirmed the fault was injected, and restores to L2 — one level below where it was, not a blind retry. That decision is a git commit Entire can explain.',
      run: async (ctx) => {
        const { spec } = classInfo(ctx.data(), primary);
        await ctx.call(() => api.restore(
          2,
          `Reviewed evidence packet for run #${ctx.mem.demotedRun ?? '?'}: quiet failure was injected by the guided demo. Restoring to L2.`,
          spec.key,
        ));
        ctx.go('/app/ledger');
      },
    },
    {
      id: 'close',
      tool: 'Solo License',
      title: 'Earned. Revocable. Priced.',
      say: (d) => {
        const others = d.task_classes.filter((t) => t.key !== primary)
          .map((t) => `${t.label} stayed at L${d.licenses[t.key].effective_level}`).join(', ');
        return `Every promote, demote and restore above is in the ledger with its reason, run and trace.${others ? ` ${others} — licenses are per task class.` : ''} An agent you'd trust to run without you watching.`;
      },
      run: async (ctx) => ctx.go('/app'),
    },
  ];
}

export function Autopilot() {
  const { data, run } = useStore();
  const navigate = useNavigate();
  const { pathname } = useLocation();
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

  if (!data || !primary) return null;

  return (
    <>
      {!open && !pathname.startsWith('/app/settings') && (
        <button className="ap-launch btn btn-ink" onClick={() => setOpen(true)}>
          <HandIcon name="play" size={14} /> Guided demo
        </button>
      )}
      <AnimatePresence>
        {open && (
          <motion.aside
            className="ap"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            aria-label="Guided demo"
          >
            <header className="ap-head">
              <span className="mono">Guided demo · {index + 1 > 0 ? `${index + 1}/${script.length}` : `${script.length} steps`}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { stop(); setOpen(false); }} aria-label="Close guided demo">
                <HandIcon name="cross" size={14} />
              </button>
            </header>

            <ol className="ap-steps">
              {script.map((s, i) => (
                <li key={s.id} className={i === index ? 'is-on' : i < index ? 'is-done' : ''}>
                  <button disabled={working || playing} onClick={() => execute(i)}>
                    <i>{i < index ? '✓' : i + 1}</i> {s.title}
                  </button>
                </li>
              ))}
            </ol>

            <AnimatePresence mode="wait">
              <motion.div
                key={step?.id || 'start'}
                className="ap-say"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                {step ? (
                  <>
                    <span className="ap-tool mono">{step.tool}</span>
                    <h3 className="serif">{step.title}</h3>
                    <p>{step.say(data, mem.current)}</p>
                  </>
                ) : (
                  <>
                    <h3 className="serif">Show the whole loop in ~60 seconds.</h3>
                    <p>
                      Real runs against this workspace: clean runs → promotion → injected quiet
                      failure → demotion → evidence → cost → human restore. Injected faults are
                      labelled in every run record.
                    </p>
                  </>
                )}
                {working && <p className="mono ap-working">Running…</p>}
                {error && <p className="ap-error"><HandIcon name="warn" size={14} /> {error}</p>}
              </motion.div>
            </AnimatePresence>

            <footer className="ap-foot">
              {playing ? (
                <button className="btn btn-line btn-sm" onClick={stop}><HandIcon name="pause" size={14} /> Pause</button>
              ) : (
                <button className="btn btn-ink btn-sm" disabled={working} onClick={() => play(index + 1 >= script.length ? 0 : index + 1)}>
                  <HandIcon name="play" size={14} /> {index < 0 ? 'Play all' : 'Play from here'}
                </button>
              )}
              <button
                className="btn btn-line btn-sm"
                disabled={working || playing || index >= script.length - 1}
                onClick={() => execute(index + 1)}
              >
                Next step <HandIcon name="arrow-right" size={14} />
              </button>
              <button className="btn btn-ghost btn-sm" disabled={working} onClick={reset}>Reset</button>
            </footer>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
