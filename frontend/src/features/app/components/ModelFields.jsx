import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { plainError } from '../../../lib/plain-errors.js';
import './plain-form.css';
import './model-fields.css';

// Re-exported for components that historically imported it from here.
export { plainError };

/** UI-only hint: the provider we nudge first-time users toward. */
const RECOMMENDED = 'gemini';

/** The saved masked hint for a secret field, e.g. "••••aeaw" (or ''). */
export function savedHint(settings, field) {
  return (field && settings?.[`${field}_hint`]) || '';
}

/** Whether the model form is complete enough to use `providerKey`. A key is
 *  only required when the provider needs one and none is stored yet. */
export function modelReady(providers, values, settings) {
  const p = (providers || []).find((x) => x.key === values.llm_provider);
  if (!p) return false;
  if (p.needs_key && !String(values[p.key_field] || '').trim() && !savedHint(settings, p.key_field)) return false;
  if (p.model_field && !String(values[p.model_field] || '').trim()) return false;
  if (p.needs_base_url && !/^https:\/\/\S+/.test(String(values.compat_base_url || '').trim())) return false;
  return true;
}

/** Only the form values relevant to one provider (for tests and payloads). */
export function providerValues(provider, values) {
  if (!provider) return { llm_provider: values.llm_provider };
  const out = { llm_provider: provider.key };
  if (provider.key_field && values[provider.key_field]) out[provider.key_field] = values[provider.key_field];
  if (provider.model_field) out[provider.model_field] = values[provider.model_field] || provider.default_model;
  if (provider.needs_base_url) out.compat_base_url = values.compat_base_url || '';
  return out;
}

/** A provider's name in plain words. */
export function providerLabel(p) {
  if (!p) return '';
  if (!p.needs_key) return 'No AI model (simple rules)';
  if (p.needs_base_url) return 'Other (OpenAI-compatible)';
  return p.label;
}

const ABOUT = {
  deterministic: 'Works without a key. Understands simple, clearly written requests only.',
  gemini: 'Has a free tier. Get a key at aistudio.google.com.',
  anthropic: 'Get a key at console.anthropic.com.',
  openai: 'Get a key at platform.openai.com.',
  groq: 'Fast hosted models. Get a key at console.groq.com; the service address is set automatically.',
  zcode_glm: 'GLM models through a ZCode Coding Plan. Get a Coding Plan key at zcode.z.ai; the service address is set automatically.',
};

/** Provider picker + key + model (+ address) + a plain connection test.
 *  Driven entirely by `providers` (data.providers). `settings` (data.settings)
 *  supplies masked hints for keys already stored. */
export function ModelFields({ providers = [], values, onChange, settings = {} }) {
  const [test, setTest] = useState(null);
  const [testing, setTesting] = useState(false);
  const provider = providers.find((p) => p.key === values.llm_provider) || null;
  const hint = provider ? savedHint(settings, provider.key_field) : '';

  function pick(key) {
    const p = providers.find((x) => x.key === key);
    if (!p) return;
    const patch = { llm_provider: p.key };
    if (p.model_field && !String(values[p.model_field] || '').trim() && p.default_model) {
      patch[p.model_field] = p.default_model;
    }
    onChange(patch);
    setTest(null);
  }

  async function runTest() {
    setTesting(true); setTest(null);
    try {
      const result = await api.testLlm(providerValues(provider, values));
      setTest(result.ok ? { ok: true, text: 'Connected' } : { ok: false, text: plainError(result.message), raw: result.message });
    } catch (cause) {
      setTest({ ok: false, text: plainError(cause.message), raw: cause.message });
    } finally {
      setTesting(false);
    }
  }

  const canTest = provider && (!provider.needs_key || String(values[provider.key_field] || '').trim() || hint);
  const about = provider ? ABOUT[provider.key] || (provider.needs_base_url ? 'For services like Groq, OpenRouter or GLM. You need their key, address and model name.' : '') : '';

  return (
    <div className="pl-form mf">
      <label className="field">
        <span>Which AI model?</span>
        <select className="input" value={provider?.key || ''} onChange={(e) => pick(e.target.value)}>
          {!provider && <option value="">Choose one</option>}
          {providers.map((p) => (
            <option key={p.key} value={p.key}>
              {providerLabel(p)}{p.key === RECOMMENDED ? ' — Recommended' : ''}
            </option>
          ))}
        </select>
        {about && <small>{about}</small>}
      </label>

      {provider && provider.needs_key && (
        <div className="pl-fields">
          <label className="field">
            <span>API key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={hint ? `Saved (ends ${hint.replace(/^•+/, '')}) — leave blank to keep` : 'Paste your key'}
              value={values[provider.key_field] || ''}
              onChange={(e) => { onChange({ [provider.key_field]: e.target.value }); setTest(null); }}
            />
            <small>Stored encrypted. We never show it again.</small>
          </label>
          {provider.model_field && (
            <label className="field">
              <span>Model name</span>
              <input
                className="input"
                spellCheck={false}
                placeholder={provider.default_model || 'e.g. openai/gpt-oss-120b'}
                value={values[provider.model_field] || ''}
                onChange={(e) => { onChange({ [provider.model_field]: e.target.value }); setTest(null); }}
              />
              <small>{provider.default_model ? 'Already filled in. Change it only if you know you need to.' : 'The exact model name from your provider.'}</small>
            </label>
          )}
          {provider.needs_base_url && (
            <label className="field mf-wide">
              <span>Service address</span>
              <input
                className="input"
                type="url"
                spellCheck={false}
                placeholder="https://api.example.com/v1"
                value={values.compat_base_url || ''}
                onChange={(e) => { onChange({ compat_base_url: e.target.value }); setTest(null); }}
              />
              <small>From your provider's docs, usually ending in /v1. Starts with https://.</small>
            </label>
          )}
        </div>
      )}

      {provider && provider.needs_key && (
        <div className="pl-test">
          <button type="button" className="btn btn-line btn-sm" onClick={runTest} disabled={testing || !canTest}>
            {testing ? 'Testing…' : 'Test'}
          </button>
          {test && (
            <span className={test.ok ? 'pl-test-ok' : 'pl-test-bad'} role="status" title={test.raw || undefined}>
              {test.ok ? '✓ ' : '✗ '}{test.text}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
