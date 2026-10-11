import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { NeatlogsFields } from '../components/IntegrationFields.jsx';
import { CodingPolicy } from '../components/CodingPolicy.jsx';
import '../components/coding-policy.css';
import '../components/plain-form.css';
import './settings.css';

export function Settings() {
  const { data } = useStore();
  if (!data?.settings) {
    return <div className="pl-page"><p className="pl-muted">Loading settings…</p></div>;
  }
  return (
    <div className="pl-page st-page">
      <header className="pl-head">
        <div>
          <h1>Settings</h1>
          <p>Which agents are connected, how far they may go, and where their traces are recorded.</p>
        </div>
      </header>

      <CodingAgentsCard settings={data.settings} />
      <Section
        title="Coding policy"
        sub="Who decides how far the agent may go. The team's file in each repository and this machine's settings can only make it ask more - never less."
      >
        <CodingPolicy />
      </Section>
      <NeatlogsCard settings={data.settings} />
    </div>
  );
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

/** Coding agents first: which agents are wired, Jev, and the setup guide. */
function CodingAgentsCard({ settings }) {
  const [agents, setAgents] = useState([]);
  const [seen, setSeen] = useState([]);
  useEffect(() => {
    api.codingAgents().then((r) => setAgents(r.agents)).catch(() => {});
    api.coding().then((r) => setSeen(r.agents || [])).catch(() => {});
  }, []);
  const label = (key) => agents.find((a) => a.key === key)?.label || key;
  return (
    <Section
      title="Coding agents"
      sub="Which agents send their permission prompts and turns to Solo License. Add another with one command from the setup guide."
      status={<span className={`pl-status ${seen.length ? 'ok' : 'wait'}`}>{seen.length ? `${seen.length} connected` : 'None yet'}</span>}
    >
      {seen.length ? (
        <ul className="pl-list">
          {seen.map((a) => (
            <li key={a.agent} className="pl-row">
              <span className="pl-row-main"><b>{label(a.agent)}</b><small>{a.decisions} decisions · last {a.last_seen}</small></span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="pl-small pl-muted">No agent has called the gate yet.</p>
      )}
      <p className="pl-small">
        Jev (calibrated decisions): <b>{settings.jev_enabled ? 'on' : 'off - built-in rules decide'}</b> · neatlogs traces: <b>{settings.neatlogs_enabled ? 'on' : 'off'}</b>
      </p>
      <div className="pl-actions">
        <Link to="/onboarding" className="btn btn-ink btn-sm">Open the setup guide</Link>
        <span className="pl-small pl-muted">Supported: {agents.map((a) => a.label).join(', ')}.</span>
      </div>
    </Section>
  );
}

function NeatlogsCard({ settings }) {
  const { run, busy } = useStore();
  const [form, setForm] = useState({ neatlogs_api_key: '', neatlogs_project: settings.neatlogs_project || '' });
  const dirty = form.neatlogs_api_key.trim() !== '' || form.neatlogs_project !== (settings.neatlogs_project || '');

  async function save(e) {
    e.preventDefault();
    const values = { neatlogs_project: form.neatlogs_project };
    if (form.neatlogs_api_key.trim()) values.neatlogs_api_key = form.neatlogs_api_key.trim();
    const result = await run(() => api.saveSettings(values), 'Settings saved.');
    if (result?.settings) setForm({ neatlogs_api_key: '', neatlogs_project: result.settings.neatlogs_project || '' });
  }

  return (
    <Section
      title="Activity recording (neatlogs)"
      sub="Every turn becomes a trace you can replay in neatlogs. Without a key, traces stay in this app."
      status={<span className={`pl-status ${settings.neatlogs_enabled ? 'ok' : 'muted'}`}>{settings.neatlogs_enabled ? 'On' : 'Off'}</span>}
    >
      <form onSubmit={save} className="pl-form">
        <NeatlogsFields values={form} onChange={(p) => setForm((f) => ({ ...f, ...p }))} settings={settings} />
        <div className="pl-actions">
          <button className="btn btn-ink btn-sm" disabled={!dirty || busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Section>
  );
}
