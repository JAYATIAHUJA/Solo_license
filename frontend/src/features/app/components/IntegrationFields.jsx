import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { savedHint } from './ModelFields.jsx';
import './integration-fields.css';

/** Which setting holds the L2 auto-approve ceiling for each task class. */
export const CEILING_FIELD = {
  refund: 'l2_auto_refund_ceiling',
  store_credit: 'l2_auto_credit_ceiling',
};

/** Unit-economics assumptions behind the live savings meter. */
export const ECON_FIELDS = [
  { key: 'econ_hourly_cost', label: 'Loaded hourly cost ($)', step: '1', note: 'What an hour of a person handling tickets costs, all-in.' },
  { key: 'econ_monthly_volume', label: 'Monthly actions per class', step: '100', note: 'How many refunds (or credits) your team handles a month.' },
  { key: 'econ_incident_cost', label: 'Cost per incident ($)', step: '5', note: 'What one wrong refund or credit costs to clean up.' },
];

const SECRET_FIELDS = ['neatlogs_api_key', 'alert_webhook_url'];

/** Editable form values from data.settings + data.providers + data.task_classes.
 *  Secrets always start blank (blank = keep the stored one). */
export function formFromSettings(settings = {}, providers = [], taskClasses = []) {
  const form = {
    business_name: settings.business_name || '',
    llm_provider: settings.llm_provider || providers[0]?.key || 'deterministic',
    compat_base_url: settings.compat_base_url || '',
    promotion_clean_runs: settings.promotion_clean_runs ?? 3,
    neatlogs_project: settings.neatlogs_project || '',
    econ_hourly_cost: settings.econ_hourly_cost ?? '',
    econ_monthly_volume: settings.econ_monthly_volume ?? '',
    econ_incident_cost: settings.econ_incident_cost ?? '',
  };
  for (const p of providers) {
    if (p.key_field) form[p.key_field] = '';
    if (p.model_field) form[p.model_field] = settings[p.model_field] || p.default_model || '';
  }
  for (const tc of taskClasses) {
    const field = CEILING_FIELD[tc.key];
    if (field) form[field] = settings[field] ?? tc.ceiling ?? 0;
  }
  for (const field of SECRET_FIELDS) form[field] = '';
  return form;
}

/** Password-style input that shows the masked stored value as a hint. */
export function SecretInput({ label, field, values, onChange, settings, placeholder, note, type = 'password' }) {
  const hint = savedHint(settings, field);
  return (
    <label className="field">
      <span>{label}</span>
      <input
        className="input"
        type={type}
        autoComplete="off"
        spellCheck={false}
        placeholder={hint ? `Saved ${hint} — leave blank to keep` : placeholder}
        value={values[field] || ''}
        onChange={(e) => onChange({ [field]: e.target.value })}
      />
      {note && <small>{note}</small>}
    </label>
  );
}

/** A "test" button with an inline ok / failed result line. */
export function TestRow({ label, icon = 'refresh', disabled, onTest }) {
  const [result, setResult] = useState(null);
  const [testing, setTesting] = useState(false);
  async function go() {
    setTesting(true); setResult(null);
    try {
      setResult(await onTest());
    } catch (cause) {
      setResult({ ok: false, message: cause.message });
    } finally {
      setTesting(false);
    }
  }
  return (
    <div className="if-test">
      <button type="button" className="btn btn-line btn-sm" onClick={go} disabled={testing || disabled}>
        <HandIcon name={icon} size={14} /> {testing ? 'Working…' : label}
      </button>
      {result && (
        <span className={result.ok ? 'if-ok' : 'if-bad'} role="status">
          <HandIcon name={result.ok ? 'check' : 'warn'} size={14} /> {result.message}
        </span>
      )}
    </div>
  );
}

const has = (values, settings, field) => Boolean(String(values[field] || '').trim() || savedHint(settings, field));

/** neatlogs API key + project + probe. */
export function NeatlogsFields({ values, onChange, settings = {} }) {
  return (
    <div className="if-block">
      <div className="if-grid">
        <SecretInput
          label="neatlogs API key"
          field="neatlogs_api_key"
          values={values}
          onChange={onChange}
          settings={settings}
          placeholder="Optional"
          note="Encrypted at rest and never shown back in full."
        />
        <label className="field">
          <span>Project</span>
          <input className="input" spellCheck={false} value={values.neatlogs_project || ''} onChange={(e) => onChange({ neatlogs_project: e.target.value })} />
          <small>The neatlogs project that receives run traces.</small>
        </label>
      </div>
      <TestRow
        label="Test neatlogs"
        icon="eye"
        disabled={!has(values, settings, 'neatlogs_api_key')}
        onTest={() => api.testNeatlogs({ neatlogs_api_key: values.neatlogs_api_key, neatlogs_project: values.neatlogs_project })}
      />
    </div>
  );
}

export const validWebhook = (url) => !String(url || '').trim() || /^https:\/\/\S+$/.test(String(url).trim());

/** Slack / Discord incoming webhook + test message. */
export function AlertFields({ values, onChange, settings = {} }) {
  const ok = validWebhook(values.alert_webhook_url);
  return (
    <div className="if-block">
      <SecretInput
        label="Alert webhook URL (Slack or Discord)"
        field="alert_webhook_url"
        type="url"
        values={values}
        onChange={onChange}
        settings={settings}
        placeholder="https://hooks.slack.com/services/…"
        note={ok ? 'Posts a message whenever an agent’s license changes (promotion, demotion, quarantine). Stored encrypted.' : 'The webhook must start with https://.'}
      />
      <TestRow
        label="Send test alert"
        icon="flag"
        disabled={!ok || !has(values, settings, 'alert_webhook_url')}
        onTest={() => api.testAlert({ alert_webhook_url: values.alert_webhook_url })}
      />
    </div>
  );
}
