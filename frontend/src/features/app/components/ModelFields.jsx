import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import './model-fields.css';

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

function describe(p) {
  if (!p.needs_key) return 'No key. Rule-based intake and template plans.';
  if (p.needs_base_url) return 'Any OpenAI-style endpoint: your key, base URL and model.';
  return p.default_model ? `Your API key · default ${p.default_model}` : 'Your API key.';
}

/** Provider picker + key + model (+ base URL) + live connection test.
 *  Driven entirely by `providers` (data.providers). `settings` (data.settings)
 *  supplies masked hints for keys already stored. */
export function ModelFields({ providers = [], values, onChange, settings = {} }) {
  const [test, setTest] = useState(null);
  const [testing, setTesting] = useState(false);
  const provider = providers.find((p) => p.key === values.llm_provider) || null;
  const hint = provider ? savedHint(settings, provider.key_field) : '';

  function pick(p) {
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
      setTest(await api.testLlm(providerValues(provider, values)));
    } catch (cause) {
      setTest({ ok: false, message: cause.message });
    } finally {
      setTesting(false);
    }
  }

  const canTest = provider && (!provider.needs_key || String(values[provider.key_field] || '').trim() || hint);

  return (
    <div className="mf">
      <div className="mf-providers" role="radiogroup" aria-label="Model provider">
        {providers.map((p, i) => {
          const on = provider?.key === p.key;
          return (
            <SketchBox
              key={p.key}
              as="button"
              type="button"
              role="radio"
              aria-checked={on}
              seed={70 + i}
              fill={on ? 'solid' : undefined}
              className={`mf-provider ${on ? 'is-on' : ''}`}
              onClick={() => pick(p)}
            >
              {p.key === RECOMMENDED && <em className="mf-badge mono">Recommended · free tier</em>}
              <b>{p.label}</b>
              <span>{describe(p)}</span>
              {p.key_field && savedHint(settings, p.key_field) && <span className="mf-saved mono">Key saved</span>}
            </SketchBox>
          );
        })}
      </div>

      {provider && provider.needs_key && (
        <div className="mf-grid">
          <label className="field">
            <span>API key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={hint ? `Saved ${hint} — leave blank to keep` : 'Paste your key'}
              value={values[provider.key_field] || ''}
              onChange={(e) => { onChange({ [provider.key_field]: e.target.value }); setTest(null); }}
            />
            <small>Encrypted at rest and never shown back in full.</small>
          </label>
          {provider.model_field && (
            <label className="field">
              <span>Model</span>
              <input
                className="input"
                spellCheck={false}
                placeholder={provider.default_model || 'e.g. glm-4.6, llama-3.3-70b'}
                value={values[provider.model_field] || ''}
                onChange={(e) => { onChange({ [provider.model_field]: e.target.value }); setTest(null); }}
              />
              {provider.default_model && <small>Default: {provider.default_model}</small>}
            </label>
          )}
          {provider.needs_base_url && (
            <label className="field mf-wide">
              <span>Base URL</span>
              <input
                className="input"
                type="url"
                spellCheck={false}
                placeholder="https://api.example.com/v1"
                value={values.compat_base_url || ''}
                onChange={(e) => { onChange({ compat_base_url: e.target.value }); setTest(null); }}
              />
              <small>The provider's API root, usually ending in /v1. Must start with https://.</small>
            </label>
          )}
          <div className="mf-test">
            <button type="button" className="btn btn-line btn-sm" onClick={runTest} disabled={testing || !canTest}>
              <HandIcon name="refresh" size={14} /> {testing ? 'Testing…' : 'Test connection'}
            </button>
            {test && (
              <span className={test.ok ? 'mf-ok' : 'mf-bad'} role="status">
                <HandIcon name={test.ok ? 'check' : 'warn'} size={14} /> {test.message}
              </span>
            )}
          </div>
        </div>
      )}
      {provider && !provider.needs_key && (
        <p className="mf-note">The agent parses messages with fixed rules and writes template plans. Good for a dry run; switch to a model any time in Settings.</p>
      )}
    </div>
  );
}
