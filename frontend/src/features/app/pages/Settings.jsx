import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { PageHeader, Panel } from '../components/Bits.jsx';
import { ModelFields } from '../components/ModelFields.jsx';

function fromSettings(s) {
  return {
    business_name: s.business_name,
    llm_provider: s.llm_provider,
    anthropic_model: s.anthropic_model,
    openai_model: s.openai_model,
    anthropic_api_key: '',
    openai_api_key: '',
    promotion_clean_runs: s.promotion_clean_runs,
    l2_auto_refund_ceiling: s.l2_auto_refund_ceiling,
    neatlogs_project: s.neatlogs_project,
    neatlogs_api_key: '',
  };
}

export function Settings() {
  const { data, run, busy } = useStore();
  const s = data.settings;
  const [form, setForm] = useState(() => fromSettings(s));
  const [confirmReset, setConfirmReset] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  async function save(e) {
    e.preventDefault();
    const result = await run(() => api.saveSettings(form), 'Settings saved.');
    if (result) setForm(fromSettings(result.settings));
  }

  return (
    <>
      <PageHeader eyebrow="Settings" title={<>Tune the <em className="italic">rules.</em></>}>
        Changes apply to the next run. Keys are stored locally and only ever shown masked.
      </PageHeader>

      <form onSubmit={save} className="app-settings">
        <Panel title="Workspace" icon="home">
          <label className="field"><span>Name</span><input className="input" value={form.business_name} onChange={(e) => set({ business_name: e.target.value })} maxLength={60} /></label>
        </Panel>

        <Panel title="Model" icon="spark" aside={<span className="mono muted">{s.llm_enabled ? 'connected' : 'built-in'}</span>}>
          <ModelFields values={form} onChange={set} hints={{ anthropic_api_key: s.anthropic_key_hint, openai_api_key: s.openai_key_hint }} />
        </Panel>

        <Panel title="License rules" icon="dial">
          <div className="app-form-grid">
            <label className="field"><span>Clean runs to promote</span><input className="input" type="number" min={1} max={20} value={form.promotion_clean_runs} onChange={(e) => set({ promotion_clean_runs: e.target.value })} /></label>
            <label className="field"><span>L2 auto-refund ceiling ($)</span><input className="input" type="number" min={0} step="5" value={form.l2_auto_refund_ceiling} onChange={(e) => set({ l2_auto_refund_ceiling: e.target.value })} /></label>
          </div>
        </Panel>

        <Panel title="Observability (neatlogs)" icon="eye" aside={<span className="mono muted">{s.neatlogs_enabled ? 'on' : 'local only'}</span>}>
          <div className="app-form-grid">
            <label className="field"><span>Project</span><input className="input" value={form.neatlogs_project} onChange={(e) => set({ neatlogs_project: e.target.value })} /></label>
            <label className="field">
              <span>API key</span>
              <input className="input" type="password" autoComplete="off" placeholder={s.neatlogs_key_hint ? `Saved ${s.neatlogs_key_hint}` : 'Optional'} value={form.neatlogs_api_key} onChange={(e) => set({ neatlogs_api_key: e.target.value })} />
            </label>
          </div>
          <p className="muted app-small">Without a key, every trace is still mirrored locally and shown in the evidence packet.</p>
        </Panel>

        <div className="app-save-bar">
          <Link to="/onboarding" className="btn btn-ghost">Run setup again</Link>
          <button className="btn btn-ink" disabled={busy}><HandIcon name="check" size={16} /> Save settings</button>
        </div>
      </form>

      <Panel title="Demo data" icon="warn" className="app-block">
        <p className="app-small">Reset wipes runs, detections and ledger rows in the database, reinstalls the 5 sample orders and sets the dial to L2. Settings and keys are kept. Git commits already made stay in history.</p>
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
