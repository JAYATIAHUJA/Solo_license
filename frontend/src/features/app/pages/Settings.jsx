import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { PageHeader, Panel } from '../components/Bits.jsx';
import { ModelFields, modelReady } from '../components/ModelFields.jsx';
import {
  AlertFields, CEILING_FIELD, ECON_FIELDS, NeatlogsFields, formFromSettings, validWebhook,
} from '../components/IntegrationFields.jsx';

export function Settings() {
  const { data } = useStore();
  if (!data || !data.settings || !data.providers) {
    return <p className="mono muted">Loading settings…</p>;
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

function SettingsForm({ data }) {
  const { run, busy } = useStore();
  const { settings: s, providers, task_classes: taskClasses = [] } = data;
  const [initial, setInitial] = useState(() => formFromSettings(s, providers, taskClasses));
  const [form, setForm] = useState(initial);
  const [confirmReset, setConfirmReset] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const changes = useMemo(() => changedValues(form, initial), [form, initial]);
  const dirty = Object.keys(changes).length > 0;
  const nameOk = String(form.business_name).trim().length > 1;
  const modelOk = modelReady(providers, form, s);
  const webhookOk = validWebhook(form.alert_webhook_url);
  const canSave = dirty && nameOk && modelOk && webhookOk && !busy;
  const activeProvider = providers.find((p) => p.key === s.llm_provider);

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

  function discard() {
    setForm(initial);
  }

  return (
    <>
      <PageHeader eyebrow="Settings" title={<>Tune the <em className="italic">rules.</em></>}>
        Changes apply to the next run. Keys are encrypted at rest and never shown back in full.
      </PageHeader>

      <form onSubmit={save} className="app-settings">
        <Panel title="Workspace" icon="home">
          <label className="field">
            <span>Name</span>
            <input className="input" value={form.business_name} onChange={(e) => set({ business_name: e.target.value })} maxLength={60} />
            {!nameOk && <small>At least two characters.</small>}
          </label>
        </Panel>

        <Panel
          title="Model"
          icon="spark"
          aside={<span className="mono muted">{s.llm_enabled ? `live · ${activeProvider?.label || s.llm_provider}` : 'built-in rules'}</span>}
        >
          <ModelFields providers={providers} values={form} onChange={set} settings={s} />
          {!modelOk && <p className="app-small muted">Add a key{providers.find((p) => p.key === form.llm_provider)?.needs_base_url ? ', model and https:// base URL' : ''} for this provider to save it.</p>}
        </Panel>

        <Panel title="Autonomy rules" icon="dial">
          <div className="app-form-grid">
            <label className="field">
              <span>Clean runs to promote</span>
              <input className="input" type="number" min={1} max={20} value={form.promotion_clean_runs} onChange={(e) => set({ promotion_clean_runs: e.target.value })} />
              <small>Consecutive verified runs to climb one rung, for every action type.</small>
            </label>
            {taskClasses.map((tc) => {
              const field = CEILING_FIELD[tc.key];
              if (!field) return null;
              return (
                <label key={tc.key} className="field">
                  <span>{tc.label} · L2 ceiling ($)</span>
                  <input className="input" type="number" min={0} step="5" value={form[field]} onChange={(e) => set({ [field]: e.target.value })} />
                  <small>At L2, any {tc.label.toLowerCase()} above this waits for a human.</small>
                </label>
              );
            })}
          </div>
        </Panel>

        <Panel title="Observability" icon="eye" aside={<span className="mono muted">{s.neatlogs_enabled ? 'neatlogs on' : 'local only'}</span>}>
          <NeatlogsFields values={form} onChange={set} settings={s} />
          <p className="muted app-small">Without a key, every trace is still recorded locally and shown in the evidence packet.</p>
        </Panel>

        <Panel title="Alerts" icon="flag" aside={<span className="mono muted">{s.alerts_enabled ? 'on' : 'off'}</span>}>
          <AlertFields values={form} onChange={set} settings={s} />
        </Panel>

        <Panel title="Unit economics" icon="ledger">
          <p className="muted app-small">These assumptions drive the live savings meter: supervision time per action at each license level, priced at your hourly cost and scaled to your monthly volume, compared with handling everything by hand. Incidents caught by the detectors are priced at your cost per incident.</p>
          <div className="app-form-grid">
            {ECON_FIELDS.map((f) => (
              <label key={f.key} className="field">
                <span>{f.label}</span>
                <input className="input" type="number" min={0} step={f.step} value={form[f.key]} onChange={(e) => set({ [f.key]: e.target.value })} />
                <small>{f.note}</small>
              </label>
            ))}
          </div>
        </Panel>

        <div className="app-save-bar">
          <Link to="/onboarding" className="btn btn-ghost">Run setup again</Link>
          {dirty && <button type="button" className="btn btn-ghost" onClick={discard}>Discard</button>}
          <button className="btn btn-ink" disabled={!canSave}>
            <HandIcon name="check" size={16} /> {dirty ? `Save ${Object.keys(changes).length} change${Object.keys(changes).length === 1 ? '' : 's'}` : 'Saved'}
          </button>
        </div>
      </form>

      <Panel title="Danger zone" icon="warn" className="app-block">
        <p className="app-small">Reset wipes runs, detections and ledger rows, then reinstalls the sample orders and resets each license to its demo level. Settings and keys are kept. Git commits already made stay in history.</p>
        {!confirmReset ? (
          <button className="btn btn-line" onClick={() => setConfirmReset(true)}><HandIcon name="refresh" size={14} /> Reset demo data…</button>
        ) : (
          <div className="app-confirm">
            <span>Wipe all runs and orders?</span>
            <button className="btn btn-ink btn-sm" disabled={busy} onClick={() => run(api.reseed, 'Demo data reset.').then(() => setConfirmReset(false))}>Yes, reset</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setConfirmReset(false)}>Cancel</button>
          </div>
        )}
      </Panel>
    </>
  );
}
