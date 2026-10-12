import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { useStore } from '../../lib/store.jsx';
import { when } from '../../lib/format.js';
import { Logo } from '../../components/brand/Logo.jsx';
import { SecretInput, TestRow } from '../app/components/IntegrationFields.jsx';
import '../app/components/plain-form.css';
import './setup.css';

const TRANSPORT = { http: 'HTTP hooks', command: 'Command hooks', plugin: 'Plugin' };
const TABS = [
  { key: 'terminal', label: 'One command' },
  { key: 'agent', label: 'Let your agent do it' },
  { key: 'plugin', label: 'Claude Code plugin', only: 'claude-code' },
];

function Copy({ text, block = false }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(text)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
    .catch(() => {});
  return (
    <div className={`su-copy ${block ? 'is-block' : ''}`}>
      {block ? <pre>{text}</pre> : <code>{text}</code>}
      <button type="button" className="btn btn-line btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
    </div>
  );
}

function Step({ n, title, children, done }) {
  return (
    <section className={`pl-card su-step ${done ? 'is-done' : ''}`}>
      <header><span className="su-n">{done ? '✓' : n}</span><h2>{title}</h2></header>
      {children}
    </section>
  );
}

/** Coding-first setup: pick the agent, install in one line (or let the agent
 *  install itself), optional keys, then watch the first hook arrive. */
export function CodingSetup() {
  const { data, setToast } = useStore();
  const [agents, setAgents] = useState([]);
  const [agent, setAgent] = useState('claude-code');
  const [install, setInstall] = useState(null);
  const [tab, setTab] = useState('terminal');
  const [seen, setSeen] = useState([]);
  const [keys, setKeys] = useState({ typesafe_api_key: '', jev_endpoint: '', neatlogs_api_key: '', neatlogs_project: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.codingAgents().then((r) => setAgents(r.agents)).catch(() => {}); }, []);
  useEffect(() => { api.codingInstall(agent).then(setInstall).catch(() => {}); }, [agent]);
  useEffect(() => {
    const poll = () => api.coding().then((r) => setSeen(r.agents || [])).catch(() => {});
    poll();
    const t = window.setInterval(poll, 4000);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => { if (tab === 'plugin' && agent !== 'claude-code') setTab('terminal'); }, [agent, tab]);

  const spec = agents.find((a) => a.key === agent);
  const connected = useMemo(() => seen.find((s) => s.agent === agent), [seen, agent]);
  const settings = data?.settings || {};

  async function saveKeys() {
    const values = Object.fromEntries(Object.entries(keys).filter(([, v]) => String(v).trim()));
    if (!Object.keys(values).length) return;
    setSaving(true);
    try {
      await api.saveSettings(values);
      setKeys({ typesafe_api_key: '', jev_endpoint: '', neatlogs_api_key: '', neatlogs_project: '' });
      setToast({ kind: 'ok', text: 'Keys saved (encrypted).', at: Date.now() });
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="su">
      <header className="su-top">
        <Link to="/" className="su-brand"><Logo size={18} /> Solo License</Link>
        <Link to="/app" className="btn btn-ghost btn-sm">Skip to the dashboard</Link>
      </header>

      <div className="su-intro">
        <p className="mono">Setup · about 2 minutes</p>
        <h1 className="serif">Let your coding agent <em className="italic">earn</em> its autonomy.</h1>
        <p>
          Solo License sits in your agent’s hooks. It answers permission prompts only for the kinds of actions the
          agent has already proven it does right in this repo, blocks the ones it must never do, and checks every turn
          for over-editing and failing tests. Everything else still comes to you.
        </p>
      </div>

      <Step n="1" title="Which agent do you use?" done={Boolean(agent)}>
        <div className="su-agents" role="radiogroup" aria-label="Coding agent">
          {agents.map((a) => (
            <button
              key={a.key}
              type="button"
              role="radio"
              aria-checked={a.key === agent}
              className={`su-agent ${a.key === agent ? 'is-on' : ''}`}
              onClick={() => setAgent(a.key)}
            >
              <b>{a.label}</b>
              <small>{TRANSPORT[a.transport] || a.transport}{a.can_send_back ? ' · sends turns back' : ' · records turns'}</small>
              {seen.some((s) => s.agent === a.key) && <i className="su-dot" aria-label="connected" />}
            </button>
          ))}
        </div>
        {spec?.notes && <p className="pl-small pl-muted">{spec.notes}</p>}
      </Step>

      <Step n="2" title={`Install it for ${spec?.label || agent}`} done={Boolean(connected)}>
        <div className="su-tabs" role="tablist">
          {TABS.filter((t) => !t.only || t.only === agent).map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
              className={`su-tab ${tab === t.key ? 'is-on' : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
        </div>
        {install && tab === 'terminal' && (
          <div className="su-body">
            <p>
              <b>Recommended: every repository, gate in the background.</b> One line (needs{' '}
              <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">uv</a>) installs Solo License, adds
              its hooks to each agent’s user-level settings on this machine, and starts the gate detached:
            </p>
            {install.global_one_liner && <Copy text={install.global_one_liner} />}
            <p className="pl-small pl-muted">
              Older Windows PowerShell has no <code>&amp;&amp;</code>: run the steps one by one. Preview first with{' '}
              <code>solo-license init --global --dry-run</code>; undo with <code>solo-license init --global --remove</code>.
            </p>
            {install.global_steps && (
              <details className="pl-more">
                <summary>Step by step</summary>
                {install.global_steps.map((line) => <Copy key={line} text={line} />)}
              </details>
            )}
            <details className="pl-more">
              <summary>Only this repository instead?</summary>
              <p>In your repository’s root:</p>
              <Copy text={install.one_liner} />
              <p>Then keep the gate running in another terminal:</p>
              <Copy text={`uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license serve`} />
              <p>Or with a permanent install:</p>
              <Copy text={install.persistent} />
              <Copy text={install.init} />
              <Copy text={install.serve} />
              <Copy text={install.doctor} />
            </details>
          </div>
        )}
        {install && tab === 'agent' && (
          <div className="su-body">
            <p>Paste this into {spec?.label || 'your agent'}. It installs Solo License itself and asks you before anything system-wide.</p>
            <Copy text={install.prompt} block />
          </div>
        )}
        {install && tab === 'plugin' && (
          <div className="su-body">
            <p>Inside Claude Code:</p>
            {install.claude_plugin.map((line) => <Copy key={line} text={line} />)}
            <p className="pl-small pl-muted">The plugin calls this dashboard’s API on 127.0.0.1:8000, so keep the gate running.</p>
          </div>
        )}
        <p className="pl-small pl-muted">
          What it writes: the agent’s user-level hook settings (or <code>{spec?.config_path}</code> for one repository)
          {spec?.transport === 'command' ? <> and a small shim, <code>hook.py</code>, in <code>~/.solo-license/</code> (or the repository’s <code>.solo-license/</code>)</> : null}, merged with any hooks
          already there. If the gate is not running, your agent behaves exactly as before - Solo License never allows anything on its own.
        </p>
      </Step>

      <Step n="3" title="Optional: sharper decisions and traces" done={settings.jev_enabled && settings.neatlogs_enabled}>
        <div className="pl-fields su-keys">
          <SecretInput label="TypeSafe API key (Jev)" field="typesafe_api_key" values={keys} settings={settings}
            onChange={(p) => setKeys((k) => ({ ...k, ...p }))} placeholder="ts_…"
            note="Jev grades each turn’s diff against your request and classifies unknown commands, with calibrated probabilities. Without it, built-in rules do the same job. Get a key at typesafe.ai." />
          <SecretInput label="neatlogs API key" field="neatlogs_api_key" values={keys} settings={settings}
            onChange={(p) => setKeys((k) => ({ ...k, ...p }))} placeholder="Paste your neatlogs key"
            note="Every turn becomes a trace you can open in neatlogs. Without it, traces stay in the local mirror." />
        </div>
        <div className="su-actions">
          <button type="button" className="btn btn-ink btn-sm" disabled={saving || !Object.values(keys).some((v) => String(v).trim())} onClick={saveKeys}>
            {saving ? 'Saving…' : 'Save keys'}
          </button>
          <TestRow label="Test Jev" okText="Jev answered" disabled={!settings.jev_enabled}
            onTest={async () => { const r = await api.testJev(); return { ok: r.ok, message: '' }; }} />
        </div>
        <p className="pl-small pl-muted">API keys are stored encrypted on this machine and never shown back in full.</p>
      </Step>

      <Step n="4" title="Say hello" done={Boolean(connected)}>
        {connected ? (
          <p className="su-ok">
            <b>{spec?.label} is connected.</b> {connected.decisions} decision{connected.decisions === 1 ? '' : 's'} so far,
            last {when(connected.last_seen)}. <Link className="app-link" to="/app">Open the dashboard →</Link>
          </p>
        ) : (
          <p className="su-wait">
            Waiting for {spec?.label || 'your agent'}… Open it in the repository and ask it to <b>“run the tests”</b>.
            The first permission prompt reaches Solo License and shows up here.
          </p>
        )}
        {seen.filter((s) => s.agent !== agent).length > 0 && (
          <p className="pl-small pl-muted">Also connected: {seen.filter((s) => s.agent !== agent).map((s) => s.agent).join(', ')}.</p>
        )}
      </Step>
    </div>
  );
}
