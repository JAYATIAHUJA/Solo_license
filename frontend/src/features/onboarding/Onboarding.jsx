import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../../lib/api.js';
import { useStore } from '../../lib/store.jsx';
import { Logo } from '../../components/brand/Logo.jsx';
import { HandIcon } from '../../components/icons/HandIcon.jsx';
import { DitherField } from '../../components/shader/PaperBackdrop.jsx';
import { modelReady, providerValues } from '../app/components/ModelFields.jsx';
import { CEILING_FIELD, formFromSettings, validWebhook } from '../app/components/IntegrationFields.jsx';
import { StepWorkspace } from './steps/StepWorkspace.jsx';
import { StepModel } from './steps/StepModel.jsx';
import { StepSignals } from './steps/StepSignals.jsx';
import { StepRules } from './steps/StepRules.jsx';
import { StepOrders } from './steps/StepOrders.jsx';
import { StepReview } from './steps/StepReview.jsx';
import './onboarding.css';

const STEPS = [
  { key: 'workspace', title: 'Workspace', Body: StepWorkspace, aside: 'Name the place your agent works. It shows up on every screen and in the ledger.' },
  { key: 'model', title: 'Model', Body: StepModel, aside: 'The model reads customer messages and writes plans. It never decides permissions. Built-in rules work with no key.' },
  { key: 'signals', title: 'Signals', Body: StepSignals, aside: 'Traces show every step the agent took. Alerts tell your team the moment a license changes. Both are optional.' },
  { key: 'rules', title: 'Rules', Body: StepRules, aside: 'Pick where each kind of action starts and how much proof it needs to climb. Most teams start at L0 or L1.' },
  { key: 'data', title: 'Data', Body: StepOrders, aside: 'The agent needs orders to act on. Load the sample set to explore, add a few real ones, or both.' },
  { key: 'review', title: 'Review', Body: StepReview, aside: 'Everything here can be changed later in Settings.' },
];

/** Keys that live in the onboarding form but are not settings values. */
const NOT_VALUES = new Set(['business_name', 'starting_levels', 'load_sample_orders', 'orders']);

function initialForm(data) {
  const form = formFromSettings(data.settings, data.providers, data.task_classes);
  const startingLevels = {};
  for (const tc of data.task_classes || []) startingLevels[tc.key] = data.licenses?.[tc.key]?.level ?? 0;
  return {
    ...form,
    starting_levels: startingLevels,
    load_sample_orders: !(data.orders || []).length,
    orders: [],
  };
}

/** Settings values to submit: everything editable except other providers' fields. */
function settingsValues(form, providers) {
  const values = {};
  const otherProviderFields = new Set();
  for (const p of providers) {
    if (p.key === form.llm_provider) continue;
    if (p.key_field) otherProviderFields.add(p.key_field);
  }
  for (const [key, value] of Object.entries(form)) {
    if (NOT_VALUES.has(key) || otherProviderFields.has(key)) continue;
    if (value === '' || value == null) continue;
    values[key] = value;
  }
  const provider = providers.find((p) => p.key === form.llm_provider);
  return { ...values, ...providerValues(provider, form) };
}

export function Onboarding() {
  const { data } = useStore();
  if (!data || !data.providers || !data.task_classes) {
    return (
      <div className="ob-loading">
        <Logo />
        <p className="mono muted">Loading your workspace…</p>
      </div>
    );
  }
  return <OnboardingFlow data={data} />;
}

function OnboardingFlow({ data }) {
  const navigate = useNavigate();
  const { load } = useStore();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(() => initialForm(data));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const ctx = { form, set, data };
  const ceilingsOk = (data.task_classes || []).every((tc) => {
    const field = CEILING_FIELD[tc.key];
    return !field || Number(form[field]) >= 0;
  });
  const canNext = [
    form.business_name.trim().length > 1,
    modelReady(data.providers, form, data.settings),
    validWebhook(form.alert_webhook_url),
    Number(form.promotion_clean_runs) >= 1 && ceilingsOk,
    form.load_sample_orders || form.orders.length > 0 || (data.orders || []).length > 0,
    true,
  ][step];

  async function finish() {
    setSaving(true); setError('');
    try {
      await api.onboard({
        business_name: form.business_name.trim(),
        starting_levels: form.starting_levels,
        load_sample_orders: form.load_sample_orders,
        orders: form.orders,
        values: settingsValues(form, data.providers),
      });
      await load();
      navigate('/app?welcome=1');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  const { Body } = STEPS[step];
  const last = step === STEPS.length - 1;

  return (
    <div className="ob">
      <aside className="ob-aside">
        <DitherField className="ob-shader" shape="simplex" speed={0.2} size={2.4} />
        <div className="ob-aside-card">
          <Link to="/" className="lp-logo"><Logo /> Solo License</Link>
          <ol className="ob-steps">
            {STEPS.map((s, i) => (
              <li key={s.key} className={i === step ? 'is-current' : i < step ? 'is-done' : ''}>
                <button type="button" onClick={() => i < step && setStep(i)} disabled={i > step} aria-current={i === step ? 'step' : undefined}>
                  <span className="ob-step-box">{i < step ? <HandIcon name="check" size={14} /> : `0${i + 1}`}</span>
                  <span className="ob-step-label">{s.title}</span>
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
        <div className="ob-progress"><motion.i initial={false} animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            className="ob-panel"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="mono muted">Step {step + 1} of {STEPS.length} · {STEPS[step].title}</p>
            <Body {...ctx} goTo={setStep} />
          </motion.div>
        </AnimatePresence>
        {error && <p className="ob-error" role="alert"><HandIcon name="warn" size={16} /> {error}</p>}
        <div className="ob-nav">
          <button type="button" className="btn btn-ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || saving}>
            <HandIcon name="arrow-left" size={16} /> Back
          </button>
          {!last ? (
            <button type="button" className="btn btn-ink" onClick={() => setStep(step + 1)} disabled={!canNext}>
              Continue <HandIcon name="arrow-right" size={16} />
            </button>
          ) : (
            <button type="button" className="btn btn-ink" onClick={finish} disabled={saving}>
              {saving ? 'Setting up…' : 'Start the agent'} <HandIcon name="play" size={14} />
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
