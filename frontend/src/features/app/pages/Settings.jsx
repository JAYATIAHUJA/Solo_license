import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { ModelFields, modelReady, providerLabel } from '../components/ModelFields.jsx';
import {
  AlertFields, CEILING_FIELD, ECON_FIELDS, InboxFields, NeatlogsFields, StripeFields, TrustFields,
  formFromSettings, validWebhook,
} from '../components/IntegrationFields.jsx';
import { levelCopy } from '../../../lib/copy.js';
import { jobsName, limitVerb, shortMoney } from '../components/words.js';
import '../components/plain-form.css';
import './settings.css';

export function Settings() {
  const { data } = useStore();
  if (!data || !data.settings || !data.providers) {
    return <div className="pl-page"><p className="pl-muted">Loading settings…</p></div>;
  }
  return <SettingsForm data={data} />;
}

/** Fields whose value differs from the saved snapshot. Secrets count as
 *  changed only when something was typed (blank keeps the stored one). */
function changedValues(form, initial) {
  const out = {};
  for (const [key, value] of Object.entries(form)) {
    if (String(value ?? '') !== String(initial[key] ?? '')) out[key] = value;
  }
  return out;
}

function Section({ title, sub, status, children }) {
  return (
    <section className="pl-card st-section">
      <div className="st-section-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {status}
      </div>
      {children}
    </section>
  );
}

function SettingsForm({ data }) {
  const { run, busy } = useStore();
  const { settings: s, providers, task_classes: taskClasses = [] } = data;
  const [initial, setInitial] = useState(() => formFromSettings(s, providers, taskClasses));
  const [form, setForm] = useState(initial);
  const [confirmReset, setConfirmReset] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const changes = useMemo(() => changedValues(form, initial), [form, initial]);
  const count = Object.keys(changes).length;
  const dirty = count > 0;
  const nameOk = String(form.business_name).trim().length > 1;
  const modelOk = modelReady(providers, form, s);
  const webhookOk = validWebhook(form.alert_webhook_url);
  const canSave = dirty && nameOk && modelOk && webhookOk && !busy;
  const activeProvider = providers.find((p) => p.key === s.llm_provider);
  const problem = !nameOk ? 'Add a business name (at least two letters).'
    : !modelOk ? 'Finish the AI model details (key, model name) or choose “No AI model”.'
      : !webhookOk ? 'The alert link should start with https://'
        : '';

  async function save(e) {
    e.preventDefault();
    if (!canSave) return;
    const result = await run(() => api.saveSettings(changes), 'Settings saved.');
    if (result?.settings) {
      const next = formFromSettings(result.settings, result.providers || providers, result.task_classes || taskClasses);
      setInitial(next);
      setForm(next);
    }
  }

  const pill = (on, onText, offText) => <span className={`pl-status ${on ? 'ok' : 'muted'}`}>{on ? onText : offText}</span>;

  return (
    <div className="pl-page st-page">
      <header className="pl-head">
        <div>
          <h1>Settings</h1>
          <p>The defaults work for most shops. Changes apply from the agent's next job.</p>
        </div>
      </header>

      <form onSubmit={save} className="pl-form st-form">
        <Section title="Your workspace">
          <label className="field st-narrow">
            <span>Business name</span>
            <input className="input" value={form.business_name} onChange={(e) => set({ business_name: e.target.value })} maxLength={60} />
            <small>{nameOk ? 'Shown in the app and in alert messages.' : 'At least two letters.'}</small>
          </label>
        </Section>

        <Section
          title="AI model"
          sub="Reads customer messages and writes a short plan. It never decides what the agent is allowed to do."
          status={pill(s.llm_enabled, `Connected: ${providerLabel(activeProvider) || s.llm_provider}`, 'Simple rules')}
        >
          <ModelFields providers={providers} values={form} onChange={set} settings={s} />
        </Section>

        <Section title="Rules" sub="When the agent earns more freedom, and how much it may hand out on its own. Freedom comes from double-checked results, weighed against what a mistake costs you.">
          <div className="st-stack">
            <TrustFields values={form} onChange={set} />
            {taskClasses.map((tc) => {
              const field = CEILING_FIELD[tc.key];
              if (!field) return null;
              const level2 = levelCopy(2, shortMoney(form[field])).short;
              return (
                <label key={tc.key} className="field">
                  <span>Most the agent may {limitVerb(tc.key)} on its own ($)</span>
                  <input className="input st-num" type="number" min={0} step="5" value={form[field]} onChange={(e) => set({ [field]: e.target.value })} />
                  <small>{jobsName(data, tc.key)}: used at “{level2}”. Anything bigger waits for your OK.</small>
                </label>
              );
            })}
          </div>
        </Section>

        <div className="st-group">
          <h2 className="st-group-title">Connections <span className="pl-muted">(optional)</span></h2>
          <Section
            title="Stripe"
            sub="Orders come from your Stripe payments; refunds and store credit happen in Stripe and are checked by reading Stripe back. Test mode only."
            status={pill(s.stripe_connected, 'Connected', 'Not connected')}
          >
            <StripeFields values={form} onChange={set} settings={s} />
            {s.stripe_connected && (
              <div className="pl-actions">
                <button type="button" className="btn btn-line btn-sm" disabled={busy}
                  onClick={() => run(api.syncStripe, (r) => `Stripe: ${r?.import?.added ?? 0} new, ${r?.import?.updated ?? 0} updated.`)}>
                  Sync orders from Stripe
                </button>
              </div>
            )}
          </Section>
          <Section
            title="Customer messages"
            sub="Messages sent to this address go straight to the agent, which answers with the reply to send."
          >
            <InboxFields />
          </Section>
          <Section
            title="Activity recording (neatlogs)"
            sub="Sends a step-by-step record of every agent action to neatlogs so you or an auditor can replay it. Without it, records are still kept in this app."
            status={pill(s.neatlogs_enabled, 'On', 'Off')}
          >
            <NeatlogsFields values={form} onChange={set} settings={s} />
          </Section>
          <Section
            title="Get notified when the agent is paused"
            sub="Paste a Slack or Discord webhook link; we post a message when a job type is paused or resumed."
            status={pill(s.alerts_enabled, 'On', 'Off')}
          >
            <AlertFields values={form} onChange={set} settings={s} />
          </Section>
        </div>

        <details className="pl-more st-advanced">
          <summary>Advanced: costs</summary>
          <div className="st-advanced-body">
            <p className="pl-muted pl-small">Your hourly cost prices the review time the agent saves, so it also sets how much proof each level needs. Volume only affects the savings estimate.</p>
            <div className="pl-fields">
              {ECON_FIELDS.filter((f) => f.key !== 'econ_incident_cost').map((f) => (
                <label key={f.key} className="field">
                  <span>{f.label}</span>
                  <input className="input" type="number" min={0} step={f.step} value={form[f.key]} onChange={(e) => set({ [f.key]: e.target.value })} />
                  <small>{f.note}</small>
                </label>
              ))}
            </div>
          </div>
        </details>

        <div className={`st-savebar ${dirty ? 'is-dirty' : ''}`} role="region" aria-label="Save changes">
          <span className="pl-small">
            {!dirty ? 'All changes saved.' : problem || `${count} unsaved change${count === 1 ? '' : 's'}.`}
          </span>
          {dirty && (
            <div className="pl-actions">
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setForm(initial)}>Discard</button>
              <button className="btn btn-ink btn-sm" disabled={!canSave}>{busy ? 'Saving…' : `Save ${count} change${count === 1 ? '' : 's'}`}</button>
            </div>
          )}
        </div>
      </form>

      <Section title="Start over">
        <p className="pl-small">
          <b>Reset demo data</b> — deletes all activity and history in this workspace and reloads sample orders. Your settings are kept.
        </p>
        {!confirmReset ? (
          <div className="pl-actions">
            <button type="button" className="btn btn-line btn-sm" onClick={() => setConfirmReset(true)}>Reset demo data…</button>
            <Link to="/onboarding" className="btn btn-ghost btn-sm">Run the setup guide again</Link>
          </div>
        ) : (
          <div className="pl-alert st-confirm">
            <span>Delete all activity and history and reload the sample orders?</span>
            <div className="pl-actions">
              <button type="button" className="btn btn-ink btn-sm" disabled={busy} onClick={() => run(api.reseed, 'Demo data reset.').then(() => setConfirmReset(false))}>Yes, reset</button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}
