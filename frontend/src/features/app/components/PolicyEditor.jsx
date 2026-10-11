import { useEffect, useMemo, useState } from 'react';
import { api } from '../../../lib/api.js';
import { draftFromPolicy, policyPayload, validatePolicyDraft } from './policyForm.js';
import './policy-editor.css';

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

/**
 * An explicit two-step editor: operators can inspect a calculated impact
 * before an admin activates a new immutable policy version. Secrets and
 * execution permits are deliberately outside this component's data contract.
 */
export function PolicyEditor({ policy, taskClasses = [], onActivated, disabled = false }) {
  const [draft, setDraft] = useState(() => draftFromPolicy(policy));
  const [preview, setPreview] = useState(null);
  const [note, setNote] = useState('');
  const [working, setWorking] = useState(false);

  useEffect(() => {
    setDraft(draftFromPolicy(policy));
    setPreview(null);
    setNote('');
  }, [policy?.version]);

  const errors = useMemo(() => validatePolicyDraft(draft, taskClasses), [draft, taskClasses]);
  const payload = useMemo(
    () => (errors.length === 0 ? policyPayload(draft, taskClasses) : null),
    [draft, errors.length, taskClasses],
  );
  const fingerprint = payload ? JSON.stringify(payload) : '';
  const previewCurrent = preview?.fingerprint === fingerprint;

  function setRule(taskClass, patch) {
    setDraft((current) => ({
      ...current,
      rules: {
        ...current.rules,
        [taskClass.key]: {
          ...(current.rules[taskClass.key] || { task_class: taskClass.key, allowed_tool: taskClass.key }),
          ...patch,
        },
      },
    }));
  }

  async function previewChanges() {
    if (!payload) return;
    setWorking(true);
    setNote('');
    try {
      const response = await api.previewPolicy(payload);
      setPreview({ impacts: response.impacts || [], fingerprint });
    } catch (error) {
      setNote(error.message || 'Could not preview this policy.');
    } finally {
      setWorking(false);
    }
  }

  async function activate() {
    if (!payload || !previewCurrent) return;
    setWorking(true);
    setNote('');
    try {
      await onActivated(payload);
    } catch (error) {
      setNote(error.message || 'Could not activate this policy.');
    } finally {
      setWorking(false);
    }
  }

  if (!policy) return null;
  return (
    <section className="policy-editor" aria-labelledby="policy-title">
      <div className="policy-editor-head">
        <div>
          <h2 id="policy-title">Autonomy policy</h2>
          <p>Version {policy.version} governs the agent now. A change only affects future runs; it never silently grants more autonomy.</p>
        </div>
        <span className="pl-status wait">v{policy.version} active</span>
      </div>

      <div className="policy-editor-intro">
        <b>How activation works</b>
        <span>Adjust a proposed version, preview its evidence impact, then explicitly activate it. Each past run stays tied to the version that governed it.</span>
      </div>

      <div className="pl-fields">
        <label className="field">
          <span>Policy name</span>
          <input className="input" value={draft.name} maxLength={120} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} disabled={disabled || working} />
        </label>
        <label className="field">
          <span>Policy summary</span>
          <input className="input" value={draft.summary} maxLength={1000} onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))} disabled={disabled || working} />
        </label>
      </div>

      <div className="policy-rule-list">
        {taskClasses.map((taskClass) => {
          const rule = draft.rules[taskClass.key] || { task_class: taskClass.key, allowed_tool: taskClass.key };
          return (
            <article className="policy-rule" key={taskClass.key}>
              <div className="policy-rule-head">
                <div>
                  <h3>{taskClass.label}</h3>
                  <p>{taskClass.description}</p>
                </div>
                <code>{rule.allowed_tool || taskClass.key}</code>
              </div>
              <div className="policy-rule-fields">
                <label className="field">
                  <span>Lowest level that may act without approval</span>
                  <select className="input" value={rule.requires_approval_at_or_above ?? '2'} onChange={(event) => setRule(taskClass, { requires_approval_at_or_above: event.target.value })} disabled={disabled || working}>
                    <option value="1">L1 - approval through suggestions only</option>
                    <option value="2">L2 - approval through drafts</option>
                    <option value="3">L3 - approval through capped auto-actions</option>
                  </select>
                </label>
                <label className="field">
                  <span>L2 auto-action ceiling ($)</span>
                  <input className="input" type="number" min="0" step="1" value={rule.l2_ceiling ?? ''} onChange={(event) => setRule(taskClass, { l2_ceiling: event.target.value })} disabled={disabled || working} />
                </label>
                <label className="field">
                  <span>Evidence window (runs)</span>
                  <input className="input" type="number" min="1" step="1" value={rule.evaluation_window ?? ''} onChange={(event) => setRule(taskClass, { evaluation_window: event.target.value })} disabled={disabled || working} />
                </label>
                <label className="field">
                  <span>Minimum clean runs</span>
                  <input className="input" type="number" min="1" step="1" value={rule.minimum_samples ?? ''} onChange={(event) => setRule(taskClass, { minimum_samples: event.target.value })} disabled={disabled || working} />
                </label>
                <label className="field">
                  <span>Verified pass rate (0–1)</span>
                  <input className="input" type="number" min="0" max="1" step="0.05" value={rule.minimum_verified_pass_rate ?? ''} onChange={(event) => setRule(taskClass, { minimum_verified_pass_rate: event.target.value })} disabled={disabled || working} />
                </label>
              </div>
            </article>
          );
        })}
      </div>

      {errors.length > 0 && <ul className="policy-errors" role="alert">{errors.map((error) => <li key={error}>{error}</li>)}</ul>}
      {note && <p className="policy-errors" role="alert">{note}</p>}

      <div className="policy-actions">
        <button type="button" className="btn btn-line btn-sm" disabled={disabled || working || !payload} onClick={previewChanges}>
          {working ? 'Checking…' : 'Preview impact'}
        </button>
        <small>Preview is required before activation.</small>
      </div>

      {previewCurrent && (
        <div className="policy-preview" aria-live="polite">
          <h3>Impact of this new version</h3>
          <p>Existing license levels are held safely. New evidence is measured only after this version becomes active.</p>
          <ul>
            {preview.impacts.map((impact) => (
              <li key={impact.task_class}>
                <b>{taskClasses.find((item) => item.key === impact.task_class)?.label || impact.task_class}</b>
                <span className={`pl-status ${impact.action === 'eligible' ? 'ok' : 'wait'}`}>{impact.action === 'eligible' ? 'Evidence ready' : 'Held for review'}</span>
                <small>{impact.reason} Current evidence: {impact.evaluation.sample_size}/{impact.evaluation.required_samples} runs, {percent(impact.evaluation.pass_rate)} verified.</small>
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn-ink btn-sm" disabled={disabled || working} onClick={activate}>
            {working ? 'Activating…' : 'Activate this policy version'}
          </button>
        </div>
      )}
    </section>
  );
}
