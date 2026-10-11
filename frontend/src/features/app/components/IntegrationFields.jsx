import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { plainError } from '../../../lib/plain-errors.js';
import { plainNeatlogsError } from '../../../lib/probe-errors.js';
import './plain-form.css';
import './integration-fields.css';

/** The masked stored value of a secret setting ("••••abcd"), if one is saved. */
export function savedHint(settings, field) {
  return (field && settings?.[`${field}_hint`]) || '';
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
        placeholder={hint ? 'Saved - leave blank to keep' : placeholder}
        value={values[field] || ''}
        onChange={(e) => onChange({ [field]: e.target.value })}
      />
      {note && <small>{note}</small>}
    </label>
  );
}

/** A "Test" button with a plain one-line result. `okText` replaces the
 *  server's success message; failures are translated by `translate`
 *  (default: the generic provider-error wording). */
export function TestRow({ label = 'Test', okText = 'Connected', disabled, onTest, translate }) {
  const [result, setResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const toText = translate || ((res) => plainError(res.message));
  async function go() {
    setTesting(true); setResult(null);
    try {
      const res = await onTest();
      setResult(res.ok ? { ok: true, text: okText } : { ok: false, text: toText(res), raw: res.message });
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
          <small>A label that groups this workspace's traces in neatlogs. The Test button checks your key by sending one diagnostic trace and reading it back - it works with any Project ID.</small>
        </label>
      </div>
      <TestRow
        disabled={!has(values, settings, 'neatlogs_api_key')}
        onTest={() => api.testNeatlogs({ neatlogs_api_key: values.neatlogs_api_key, neatlogs_project: values.neatlogs_project })}
        translate={plainNeatlogsError}
      />
    </div>
  );
}
