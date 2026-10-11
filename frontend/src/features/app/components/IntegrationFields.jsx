import { useEffect, useState } from 'react';
import { api } from '../../../lib/api.js';
import { plainError, savedHint } from './ModelFields.jsx';
import './plain-form.css';
import './integration-fields.css';

/** Which setting holds the "works alone up to $X" limit for each job type. */
export const CEILING_FIELD = {
  refund: 'l2_auto_refund_ceiling',
  store_credit: 'l2_auto_credit_ceiling',
};

/** Cost assumptions used only to estimate savings on the Reports page. */
export const ECON_FIELDS = [
  { key: 'econ_hourly_cost', label: 'What an hour of your time costs ($)', step: '1', note: 'Used to price the time the agent saves you.' },
  { key: 'econ_monthly_volume', label: 'Jobs per month, per job type', step: '100', note: 'Roughly how many refunds (or store credits) you handle in a month.' },
  { key: 'econ_incident_cost', label: 'Cost of one mistake ($)', step: '5', note: 'What it costs you to fix one wrong refund or credit.' },
];

const SECRET_FIELDS = ['neatlogs_api_key', 'alert_webhook_url', 'stripe_secret_key'];

/** "How sure must the evidence be?" — the choices offered for trust_confidence. */
export const CONFIDENCE_CHOICES = [
  { value: 0.8, label: 'Fairly sure (80%)', note: 'Freedom comes sooner. Fine for small amounts.' },
  { value: 0.9, label: 'Very sure (90%)', note: 'A good balance for most shops.' },
  { value: 0.95, label: 'Almost certain (95%)', note: 'Slowest, safest.' },
];

/** Editable form values from data.settings + data.providers + data.task_classes.
 *  Secrets always start blank (blank = keep the stored one). */
export function formFromSettings(settings = {}, providers = [], taskClasses = []) {
  const form = {
    business_name: settings.business_name || '',
    llm_provider: settings.llm_provider || providers[0]?.key || 'deterministic',
    compat_base_url: settings.compat_base_url || '',
    trust_confidence: settings.trust_confidence ?? 0.9,
    refund_window_days: settings.refund_window_days ?? 30,
    orders_source: settings.orders_source || '',
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
        placeholder={hint ? 'Saved — leave blank to keep' : placeholder}
        value={values[field] || ''}
        onChange={(e) => onChange({ [field]: e.target.value })}
      />
      {note && <small>{note}</small>}
    </label>
  );
}

/** A "Test" button with a plain one-line result. `okText` replaces the
 *  server's success message; failures are translated by plainError. */
export function TestRow({ label = 'Test', okText = 'Connected', disabled, onTest }) {
  const [result, setResult] = useState(null);
  const [testing, setTesting] = useState(false);
  async function go() {
    setTesting(true); setResult(null);
    try {
      const res = await onTest();
      setResult(res.ok ? { ok: true, text: okText } : { ok: false, text: plainError(res.message), raw: res.message });
    } catch (cause) {
      setResult({ ok: false, text: plainError(cause.message), raw: cause.message });
    } finally {
      setTesting(false);
    }
  }
  return (
    <div className="pl-test">
      <button type="button" className="btn btn-line btn-sm" onClick={go} disabled={testing || disabled}>
        {testing ? 'Testing…' : label}
      </button>
      {result && (
        <span className={result.ok ? 'pl-test-ok' : 'pl-test-bad'} role="status" title={result.raw || undefined}>
          {result.ok ? '✓ ' : '✗ '}{result.text}
        </span>
      )}
    </div>
  );
}

const has = (values, settings, field) => Boolean(String(values[field] || '').trim() || savedHint(settings, field));

/** neatlogs API key + project + test. */
export function NeatlogsFields({ values, onChange, settings = {} }) {
  return (
    <div className="pl-form">
      <div className="pl-fields">
        <SecretInput
          label="neatlogs API key"
          field="neatlogs_api_key"
          values={values}
          onChange={onChange}
          settings={settings}
          placeholder="Paste your neatlogs key"
          note="From your neatlogs account. Stored encrypted."
        />
        <label className="field">
          <span>Project ID</span>
          <input className="input" spellCheck={false} value={values.neatlogs_project || ''} onChange={(e) => onChange({ neatlogs_project: e.target.value })} />
          <small>Which neatlogs project receives the records. Leave as is unless neatlogs gave you another.</small>
        </label>
      </div>
      <TestRow
        disabled={!has(values, settings, 'neatlogs_api_key')}
        onTest={() => api.testNeatlogs({ neatlogs_api_key: values.neatlogs_api_key, neatlogs_project: values.neatlogs_project })}
      />
    </div>
  );
}

export const validWebhook = (url) => !String(url || '').trim() || /^https:\/\/\S+$/.test(String(url).trim());

/** Slack / Discord webhook link + test message. */
export function AlertFields({ values, onChange, settings = {} }) {
  const ok = validWebhook(values.alert_webhook_url);
  return (
    <div className="pl-form">
      <SecretInput
        label="Slack or Discord webhook link"
        field="alert_webhook_url"
        type="url"
        values={values}
        onChange={onChange}
        settings={settings}
        placeholder="https://hooks.slack.com/services/…"
        note={ok ? 'In Slack or Discord, create an “incoming webhook” for a channel and paste its link here.' : 'The link should start with https://'}
      />
      <TestRow
        label="Send a test message"
        okText="Sent — check your channel."
        disabled={!ok || !has(values, settings, 'alert_webhook_url')}
        onTest={() => api.testAlert({ alert_webhook_url: values.alert_webhook_url })}
      />
    </div>
  );
}

/** Stripe test-mode key + test. Sample charges and sync need a saved key. */
export function StripeFields({ values, onChange, settings = {} }) {
  const key = String(values.stripe_secret_key || '').trim();
  const looksRight = !key || /^(sk|rk)_test_[A-Za-z0-9]+$/.test(key);
  return (
    <div className="pl-form">
      <div className="pl-fields">
        <SecretInput
          label="Stripe secret key (test mode)"
          field="stripe_secret_key"
          values={values}
          onChange={onChange}
          settings={settings}
          placeholder="sk_test_…"
          note={looksRight
            ? 'Stripe Dashboard → Developers → API keys, with “Test mode” on. Stored encrypted. Live keys are refused.'
            : 'Use a test-mode secret key: it starts with sk_test_.'}
        />
      </div>
      <TestRow
        disabled={!looksRight || !has(values, settings, 'stripe_secret_key')}
        okText="Connected to Stripe (test mode)"
        onTest={() => api.testStripe({ stripe_secret_key: values.stripe_secret_key })}
      />
    </div>
  );
}

/** Where a helpdesk or email forwarder sends customer messages. */
export function InboxFields() {
  const [info, setInfo] = useState(null);
  const [copied, setCopied] = useState('');
  useEffect(() => { api.inboxSecret().then(setInfo).catch(() => setInfo(null)); }, []);
  if (!info) return <p className="pl-help">The inbox address appears here once your workspace is set up.</p>;
  const url = `${window.location.origin}${info.path}`;
  const curl = `curl -X POST "${url}" -H "Content-Type: application/json" -H "X-Solo-Inbox-Key: ${info.secret}" `
    + `-d '{"email":"ada@example.com","subject":"Broken","body":"ORD-1001 arrived broken, refund please"}'`;
  const copy = (text, what) => navigator.clipboard?.writeText(text).then(() => setCopied(what));
  return (
    <div className="pl-form inbox-fields">
      <dl className="pl-kv">
        <dt>Address</dt><dd><code>{url}</code></dd>
        <dt>Key header</dt><dd><code>X-Solo-Inbox-Key: {info.secret}</code></dd>
      </dl>
      <p className="pl-help">
        Point a Zendesk / Gorgias / Help Scout trigger, a Zapier or Make step, or an email-to-webhook forwarder here.
        Send <code>email</code>, <code>subject</code> and <code>body</code>; the answer contains the reply to send back.
      </p>
      <div className="pl-actions">
        <button type="button" className="btn btn-line btn-sm" onClick={() => copy(url, 'address')}>Copy address</button>
        <button type="button" className="btn btn-line btn-sm" onClick={() => copy(info.secret, 'key')}>Copy key</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => copy(curl, 'test command')}>Copy a test command</button>
        {copied && <span className="pl-test-ok" role="status">✓ Copied {copied}</span>}
      </div>
    </div>
  );
}

/** How freedom is earned: confidence, refund window and the cost of a mistake. */
export function TrustFields({ values, onChange }) {
  return (
    <div className="pl-form">
      <fieldset className="pl-choices" aria-label="How sure before more freedom">
        <legend className="pl-legend">Before giving the agent more freedom, how sure should we be?</legend>
        {CONFIDENCE_CHOICES.map((c) => (
          <label key={c.value} className={`pl-choice ${Number(values.trust_confidence) === c.value ? 'is-on' : ''}`}>
            <input type="radio" name="trust_confidence" checked={Number(values.trust_confidence) === c.value}
              onChange={() => onChange({ trust_confidence: c.value })} />
            <span><b>{c.label}</b>{c.value === 0.9 && <span className="pl-tag">Recommended</span>}<small>{c.note}</small></span>
          </label>
        ))}
      </fieldset>
      <div className="pl-fields">
        <label className="field">
          <span>Cost of one mistake ($)</span>
          <input className="input" type="number" min={1} step="5" value={values.econ_incident_cost}
            placeholder="120" onChange={(e) => onChange({ econ_incident_cost: e.target.value })} />
          <small>A wrong refund plus the time to fix it. The higher it is, the more proof the agent needs.</small>
        </label>
        <label className="field">
          <span>Refunds allowed for (days)</span>
          <input className="input" type="number" min={0} step="1" value={values.refund_window_days}
            onChange={(e) => onChange({ refund_window_days: e.target.value })} />
          <small>Older orders are offered store credit instead. 0 = no limit.</small>
        </label>
      </div>
    </div>
  );
}
