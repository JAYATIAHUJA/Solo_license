import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../../lib/api.js';
import { useStore } from '../../lib/store.jsx';
import { Logo } from '../../components/brand/Logo.jsx';
import { HandIcon } from '../../components/icons/HandIcon.jsx';
import { DitherField } from '../../components/shader/PaperBackdrop.jsx';
import { StepWorkspace } from './steps/StepWorkspace.jsx';
import { StepModel } from './steps/StepModel.jsx';
import { StepRules } from './steps/StepRules.jsx';
import { StepOrders } from './steps/StepOrders.jsx';
import { StepReview } from './steps/StepReview.jsx';
import './onboarding.css';

const STEPS = [
  { key: 'workspace', title: 'Workspace', aside: 'Name the place your agent works. It shows up on every screen and in the ledger.' },
  { key: 'model', title: 'Model', aside: 'The model reads customer messages and writes plans. It never decides permissions. You can skip this and use the built-in parser.' },
  { key: 'rules', title: 'Rules', aside: 'Pick where the agent starts and how much proof it needs to climb. Most teams start at L0 or L1.' },
  { key: 'orders', title: 'Orders', aside: 'The agent needs orders to refund. Load samples to explore, or add a few real ones.' },
  { key: 'review', title: 'Review', aside: 'Everything here can be changed later in Settings.' },
];

const INITIAL = {
  business_name: '',
  llm_provider: 'deterministic',
  anthropic_api_key: '',
  anthropic_model: 'claude-sonnet-5-5',
  openai_api_key: '',
  openai_model: 'gpt-4o',
  starting_level: 0,
  promotion_clean_runs: 3,
  l2_auto_refund_ceiling: 50,
  load_sample_orders: true,
  custom_orders: [],
};

export function Onboarding() {
  const navigate = useNavigate();
  const { load } = useStore();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(INITIAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const canNext = [
    form.business_name.trim().length > 1,
    form.llm_provider === 'deterministic' || (form.llm_provider === 'anthropic' ? form.anthropic_api_key : form.openai_api_key).trim().length > 8,
    form.promotion_clean_runs >= 1 && form.l2_auto_refund_ceiling >= 0,
    form.load_sample_orders || form.custom_orders.length > 0,
    true,
  ][step];

  async function finish() {
    setSaving(true); setError('');
    try {
      await api.onboard({
        business_name: form.business_name,
        starting_level: form.starting_level,
        load_sample_orders: form.load_sample_orders,
        values: {
          llm_provider: form.llm_provider,
          anthropic_api_key: form.anthropic_api_key,
          anthropic_model: form.anthropic_model,
          openai_api_key: form.openai_api_key,
          openai_model: form.openai_model,
          promotion_clean_runs: form.promotion_clean_runs,
          l2_auto_refund_ceiling: form.l2_auto_refund_ceiling,
        },
      });
      for (const order of form.custom_orders) {
        // eslint-disable-next-line no-await-in-loop
        await api.addOrder(order).catch(() => null);
      }
      await load();
      navigate('/app/agent?welcome=1');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  const Body = [StepWorkspace, StepModel, StepRules, StepOrders, StepReview][step];

  return (
    <div className="ob">
      <aside className="ob-aside">
        <DitherField className="ob-shader" shape="simplex" speed={0.2} size={2.4} />
        <div className="ob-aside-card">
          <Link to="/" className="lp-logo"><Logo /> Solo License</Link>
          <ol className="ob-steps">
            {STEPS.map((s, i) => (
              <li key={s.key} className={i === step ? 'is-current' : i < step ? 'is-done' : ''}>
                <button onClick={() => i < step && setStep(i)} disabled={i > step}>
                  <span className="ob-step-box">{i < step ? <HandIcon name="check" size={14} /> : `0${i + 1}`}</span>
                  {s.title}
                </button>
              </li>
            ))}
          </ol>
          <AnimatePresence mode="wait">
            <motion.p key={step} className="ob-aside-note hand" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              {STEPS[step].aside}
            </motion.p>
          </AnimatePresence>
        </div>
      </aside>

      <main className="ob-main">
        <div className="ob-progress"><motion.i animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            className="ob-panel"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="mono muted">Step {step + 1} of {STEPS.length}</p>
            <Body form={form} set={set} />
          </motion.div>
        </AnimatePresence>
        {error && <p className="ob-error"><HandIcon name="warn" size={16} /> {error}</p>}
        <div className="ob-nav">
          <button className="btn btn-ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || saving}>
            <HandIcon name="arrow-left" size={16} /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button className="btn btn-ink" onClick={() => setStep(step + 1)} disabled={!canNext}>
              Continue <HandIcon name="arrow-right" size={16} />
            </button>
          ) : (
            <button className="btn btn-ink" onClick={finish} disabled={saving}>
              {saving ? 'Setting up…' : 'Start the agent'} <HandIcon name="play" size={14} />
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
