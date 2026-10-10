import { useState } from 'react';
import { api } from '../../../lib/api.js';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchBox } from '../../../components/sketch/Sketch.jsx';
import './model-fields.css';

const PROVIDERS = [
  { id: 'deterministic', name: 'Built-in', note: 'No key. Regex intake + template plans.' },
  { id: 'anthropic', name: 'Anthropic', note: 'Claude models via your API key.' },
  { id: 'openai', name: 'OpenAI', note: 'GPT models via your API key.' },
];

/** Provider picker + key + model + live connection test. Shared by onboarding
 *  and Settings. `hints` shows the masked stored key when one exists. */
export function ModelFields({ values, onChange, hints = {} }) {
  const [test, setTest] = useState(null);
  const [testing, setTesting] = useState(false);
  const provider = values.llm_provider;
  const keyField = provider === 'anthropic' ? 'anthropic_api_key' : 'openai_api_key';
  const modelField = provider === 'anthropic' ? 'anthropic_model' : 'openai_model';

  async function runTest() {
    setTesting(true); setTest(null);
    try {
      setTest(await api.testLlm({
        llm_provider: provider,
        [keyField]: values[keyField],
        [modelField]: values[modelField],
      }));
    } catch (cause) {
      setTest({ ok: false, message: cause.message });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="mf">
      <div className="mf-providers" role="radiogroup" aria-label="Model provider">
        {PROVIDERS.map((p, i) => (
          <SketchBox
            key={p.id}
            as="button"
            type="button"
            role="radio"
            aria-checked={provider === p.id}
            seed={70 + i}
            fill={provider === p.id ? 'solid' : undefined}
            className={`mf-provider ${provider === p.id ? 'is-on' : ''}`}
            onClick={() => { onChange({ llm_provider: p.id }); setTest(null); }}
          >
            <b>{p.name}</b>
            <span>{p.note}</span>
          </SketchBox>
        ))}
      </div>

      {provider !== 'deterministic' && (
        <div className="mf-grid">
          <label className="field">
            <span>API key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              placeholder={hints[keyField] ? `Saved ${hints[keyField]} — leave blank to keep` : provider === 'anthropic' ? 'sk-ant-…' : 'sk-…'}
              value={values[keyField] || ''}
              onChange={(e) => onChange({ [keyField]: e.target.value })}
            />
            <small>Stored in your local database. Never shown back in full.</small>
          </label>
          <label className="field">
            <span>Model</span>
            <input className="input" value={values[modelField] || ''} onChange={(e) => onChange({ [modelField]: e.target.value })} />
          </label>
          <div className="mf-test">
            <button type="button" className="btn btn-line btn-sm" onClick={runTest} disabled={testing}>
              <HandIcon name="refresh" size={14} /> {testing ? 'Testing…' : 'Test connection'}
            </button>
            {test && (
              <span className={test.ok ? 'mf-ok' : 'mf-bad'}>
                <HandIcon name={test.ok ? 'check' : 'warn'} size={14} /> {test.message}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
