import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { useStore } from '../../lib/store.jsx';
import { Logo } from '../../components/brand/Logo.jsx';
import { modelReady, providerValues } from '../app/components/ModelFields.jsx';
import { CEILING_FIELD, formFromSettings, validWebhook } from '../app/components/IntegrationFields.jsx';
import { StepWorkspace } from './steps/StepWorkspace.jsx';
import { StepModel } from './steps/StepModel.jsx';
import { StepSignals } from './steps/StepSignals.jsx';
import { StepRules } from './steps/StepRules.jsx';
import { StepOrders, ordersReady } from './steps/StepOrders.jsx';
import { StepReview } from './steps/StepReview.jsx';
import '../app/components/plain-form.css';
import './onboarding.css';

/** The order here is the order on screen. `optional` steps can be skipped. */
const STEPS = [
  { key: 'workspace', title: 'Your business', Body: StepWorkspace },
  { key: 'data', title: 'Orders', Body: StepOrders },
  { key: 'rules', title: 'Rules', Body: StepRules },
  { key: 'model', title: 'AI model', Body: StepModel },
  { key: 'signals', title: 'Connections', Body: StepSignals, optional: true },
  { key: 'review', title: 'Review', Body: StepReview },
];

/** Where every job type starts if the user doesn't choose: "Needs your OK". */
const RECOMMENDED_START = 1;

/** Keys that live in the onboarding form but are not settings values. */
const NOT_VALUES = new Set(['business_name', 'starting_levels', 'load_sample_orders', 'orders', 'orders_csv', 'stripe_sample']);

function initialForm(data) {
  const form = formFromSettings(data.settings, data.providers, data.task_classes);
  const startingLevels = {};
  for (const tc of data.task_classes || []) {
    startingLevels[tc.key] = data.settings?.onboarded ? (data.licenses?.[tc.key]?.level ?? RECOMMENDED_START) : RECOMMENDED_START;
  }
  return {
    ...form,
    starting_levels: startingLevels,
    orders_source: form.orders_source || ((data.orders || []).length ? '' : 'sample'),
    load_sample_orders: !(data.orders || []).length && !form.orders_source,
    orders: [],
    orders_csv: '',
    stripe_sample: false,
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
        <p className="pl-muted">Loading your workspace…</p>
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
  useEffect(() => { window.scrollTo(0, 0); }, [step]);

  const ceilingsOk = (data.task_classes || []).every((tc) => {
    const field = CEILING_FIELD[tc.key];
    return !field || Number(form[field]) >= 0;
  });
  const ready = {
    workspace: form.business_name.trim().length > 1,
    model: modelReady(data.providers, form, data.settings),
    rules: ceilingsOk && Number(form.trust_confidence) >= 0.5 && Number(form.refund_window_days) >= 0,
    signals: validWebhook(form.alert_webhook_url),
    data: ordersReady(form, data),
    review: true,
  };
  const current = STEPS[step];
  const canNext = ready[current.key];
  const last = step === STEPS.length - 1;

  async function finish() {
    setSaving(true); setError('');
    try {
      await api.onboard({
        business_name: form.business_name.trim(),
        starting_levels: form.starting_levels,
        load_sample_orders: form.orders_source === 'sample',
        orders: form.orders,
        orders_csv: form.orders_source === 'csv' ? form.orders_csv : null,
        values: settingsValues(form, data.providers),
      });
      if (form.orders_source === 'stripe') {
        await (form.stripe_sample ? api.stripeSample() : api.syncStripe());
      }
      await load();
      navigate('/app?welcome=1');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  function skip() {
    set({ neatlogs_api_key: '', alert_webhook_url: '' });
    setStep(step + 1);
  }

  const { Body } = current;

  return (
    <div className="ob">
      <aside className="ob-aside">
        <div className="ob-aside-card">
          <Link to="/" className="ob-brand"><Logo /> Solo License</Link>
          <ol className="ob-steps" aria-label="Setup steps">
            {STEPS.map((s, i) => (
              <li key={s.key} className={i === step ? 'is-current' : i < step ? 'is-done' : ''}>
                <button type="button" onClick={() => i < step && setStep(i)} disabled={i > step} aria-current={i === step ? 'step' : undefined}>
                  <span className="ob-step-box" aria-hidden="true">{i < step ? '✓' : i + 1}</span>
                  <span className="ob-step-label">{s.title}{s.optional ? <small> (optional)</small> : null}</span>
                </button>
              </li>
            ))}
          </ol>
          <p className="ob-aside-note">Everything here can be changed later in Settings.</p>
        </div>
      </aside>

      <main className="ob-main pl-form">
        <div className="ob-progress" aria-hidden="true"><i style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>
        <div className="ob-panel">
          <p className="ob-step-count">Step {step + 1} of {STEPS.length} · {current.title}</p>
          <Body form={form} set={set} data={data} goTo={setStep} />
        </div>
        {error && <p className="ob-error" role="alert">{error}</p>}
        <div className="ob-nav">
          <button type="button" className="btn btn-ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || saving}>
            ← Back
          </button>
          <div className="pl-actions">
            {current.optional && <button type="button" className="btn btn-ghost" onClick={skip}>Skip for now</button>}
            {!last ? (
              <button type="button" className="btn btn-ink" onClick={() => setStep(step + 1)} disabled={!canNext}>
                Continue →
              </button>
            ) : (
              <button type="button" className="btn btn-ink" onClick={finish} disabled={saving}>
                {saving ? 'Setting up…' : 'Finish setup'}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
