import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../../lib/api.js';
import { useStore } from '../../lib/store.jsx';
import { when } from '../../lib/format.js';
import { Logo } from '../../components/brand/Logo.jsx';
import { PaperGrain } from '../../components/shader/PaperBackdrop.jsx';
import { CopyCommand as Copy, CopyList } from '../../components/CopyCommand.jsx';
import { SecretInput, TestRow } from '../app/components/IntegrationFields.jsx';
import { plainNeatlogsError } from '../../lib/probe-errors.js';
import '../app/components/plain-form.css';
import './setup.css';

const TRANSPORT = { http: 'HTTP hooks', command: 'Command hooks', plugin: 'Plugin' };
const TABS = [
  { key: 'terminal', label: 'One command' },
  { key: 'agent', label: 'Let your agent do it' },
  { key: 'plugin', label: 'Claude Code plugin', only: 'claude-code' },
];

/* Two flows share one screen. Opened by `solo-license onboard` (?wizard=1) the
   browser picks the agents and installs them, so keys come first (required);
   otherwise you pick one agent and run the command yourself. */
const FLOW = {
  manual: [['pick', 'Pick your agent'], ['install', 'Install'], ['keys', 'Add keys (optional)'], ['connect', 'Connect']],
  wizard: [['pick', 'Pick your agents'], ['keys', 'Add keys'], ['install', 'Install'], ['connect', 'Connect']],
};

/** Coding-first setup as a one-screen wizard: pick the agent, install in one
 *  line (or let the agent install itself), optional keys, then watch the
 *  first hook arrive. One step on screen at a time. */
export function CodingSetup() {
  const { data, setToast } = useStore();
  const [params] = useSearchParams();
  const wizard = params.get('wizard') === '1';
  const [picked, setPicked] = useState(null); // wizard: agent keys chosen in the browser
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(null);
  const [wiz, setWiz] = useState(null);
  const [agents, setAgents] = useState([]);
  const [agent, setAgent] = useState('claude-code');
  const [install, setInstall] = useState(null);
  const [tab, setTab] = useState('terminal');
  const [seen, setSeen] = useState([]);
  const [keys, setKeys] = useState({ typesafe_api_key: '', jev_endpoint: '', neatlogs_api_key: '', neatlogs_project: '' });
  const [saving, setSaving] = useState(false);
  const [step, setStep] = useState(0);

  const [detected, setDetected] = useState([]);
  useEffect(() => {
    api.codingAgents().then((r) => {
      const found = r.detected || [];
      // agents found on this machine come first, and the first one is picked
      setAgents([...r.agents].sort((a, b) => found.includes(b.key) - found.includes(a.key)));
      setDetected(found);
      if (found.length) setAgent(found[0]);
    }).catch(() => {});
  }, []);
  useEffect(() => { api.codingInstall(agent).then(setInstall).catch(() => {}); }, [agent]);
  // the paste-in prompt is agent-neutral: whichever agent reads it sets itself up
  const [anyAgentPrompt, setAnyAgentPrompt] = useState('');
  useEffect(() => { api.codingInstall('auto').then((r) => setAnyAgentPrompt(r.prompt)).catch(() => {}); }, []);
  useEffect(() => {
    const poll = () => api.coding().then((r) => setSeen(r.agents || [])).catch(() => {});
    poll();
    const t = window.setInterval(poll, 4000);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => { if (tab === 'plugin' && agent !== 'claude-code') setTab('terminal'); }, [agent, tab]);
  useEffect(() => {
    if (!wizard) return undefined;
    const poll = () => api.wizard().then(setWiz).catch(() => {});
    poll();
    const t = window.setInterval(poll, 2000);
    return () => window.clearInterval(t);
  }, [wizard]);
  // the onboard run's own detection wins; before it reports, use this machine's
  const wizFound = (wiz?.agents || []).filter((a) => a.found).map((a) => a.key);
  useEffect(() => {
    if (picked === null && wiz && (wizFound.length || detected.length)) setPicked(wizFound.length ? wizFound : detected);
  }, [wiz, picked, wizFound, detected]);

  const spec = agents.find((a) => a.key === agent);
  const connected = useMemo(() => seen.find((s) => s.agent === agent), [seen, agent]);
  const settings = data?.settings || {};
  const keysReady = Boolean(settings.jev_enabled && settings.neatlogs_enabled);
  const found = wizard && wizFound.length ? wizFound : detected;
  const steps = FLOW[wizard ? 'wizard' : 'manual'];
  const view = steps[step][0];
  const blocked = wizard && ((view === 'pick' && !picked?.length) || (view === 'keys' && !keysReady)
    || (view === 'install' && !installed?.installed?.length));

  async function installPicked() {
    setInstalling(true);
    try {
      const r = await api.wizardSelect(picked);
      setInstalled(r);
      setToast({ kind: r.errors && Object.keys(r.errors).length ? 'error' : 'ok', text: 'Hooks installed.', at: Date.now() });
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setInstalling(false);
    }
  }

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

  const last = step === steps.length - 1;

  return (
    <div className="su">
      <PaperGrain opacity={0.3} />
      <header className="su-top">
        <Link to="/" className="su-brand"><Logo size={18} /> Solo License</Link>
        <Link to="/app" className="btn btn-ghost btn-sm">Skip to the dashboard</Link>
      </header>

      <ol className="su-progress" aria-label="Setup steps">
        {steps.map(([key, label], i) => (
          <li key={key} className={i === step ? 'is-on' : i < step ? 'is-done' : ''}>
            <button type="button" onClick={() => setStep(i)}>
              <span className="su-n">{i < step ? '✓' : i + 1}</span>
              <span className="su-step-label">{label}</span>
            </button>
          </li>
        ))}
      </ol>

      <section className="pl-card su-panel">
        {view === 'pick' && (
          <>
            <h1 className="su-h">{wizard ? 'Which agents should get hooks?' : 'Which coding agent do you use?'}</h1>
            <div className="su-agents" role={wizard ? 'group' : 'radiogroup'} aria-label={wizard ? 'Agents to install' : 'Coding agent'}>
              {agents.map((a) => {
                const on = wizard ? Boolean(picked?.includes(a.key)) : a.key === agent;
                const toggle = () => (wizard
                  ? setPicked((p) => ((p || []).includes(a.key) ? p.filter((k) => k !== a.key) : [...(p || []), a.key]))
                  : setAgent(a.key));
                return (
                  <button
                    key={a.key}
                    type="button"
                    role={wizard ? 'checkbox' : 'radio'}
                    aria-checked={on}
                    className={`su-agent ${on ? 'is-on' : ''} ${found.length && !found.includes(a.key) ? 'is-absent' : ''}`}
                    onClick={toggle}
                    title={found.includes(a.key) ? 'Installed on this machine' : 'Not found on this machine'}
                  >
                    <b>{a.label}</b>
                    {seen.some((s) => s.agent === a.key) && <i className="su-dot" aria-label="connected" />}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {view === 'install' && wizard && (
          <>
            <h1 className="su-h">Install the hooks</h1>
            <p>
              <b>{picked?.length || 0} agent{picked?.length === 1 ? '' : 's'} selected.</b> Each gets its own hook settings and a
              small shim in <code>.solo-license/</code>. Undo any time with <code>solo-license init --remove</code>.
            </p>
            <div className="su-actions">
              <button type="button" className="btn btn-ink" disabled={installing || !picked?.length || !keysReady} onClick={installPicked}>
                {installing ? 'Installing…' : `Install hooks for ${picked?.length || 0} agent${picked?.length === 1 ? '' : 's'}`}
              </button>
              {!keysReady && <span className="pl-test-bad" role="status">Add the neatlogs and Jev keys first.</span>}
            </div>
            {installed?.installed?.length > 0 && (
              <p className="su-ok"><b>Installed for:</b> {installed.installed.map((k) => (agents.find((a) => a.key === k) || {}).label || k).join(', ')}. Your terminal is continuing.</p>
            )}
            {Object.entries(installed?.errors || {}).map(([k, e]) => (
              <p key={k} className="pl-test-bad">{(agents.find((a) => a.key === k) || {}).label || k}: {e}</p>
            ))}
          </>
        )}

        {view === 'install' && !wizard && (
          <>
            <h1 className="su-h">Install it for {spec?.label || agent}</h1>
            <div className="su-tabs" role="tablist">
              {TABS.filter((t) => !t.only || t.only === agent).map((t) => (
                <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
                  className={`su-tab ${tab === t.key ? 'is-on' : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
              ))}
            </div>
            {install && tab === 'terminal' && (
              <div className="su-body">
                <p>Run this in your terminal. It adds the hooks and starts Solo License in the background.</p>
                {install.global_one_liner && <Copy text={install.global_one_liner} />}
                <details className="pl-more">
                  <summary>Only this repository, or step by step</summary>
                  <p className="su-label">Only this repository (run in its root)</p>
                  <Copy text={install.one_liner} />
                  {install.global_steps && (
                    <>
                      <p className="su-label">Or step by step</p>
                      <CopyList lines={install.global_steps} />
                    </>
                  )}
                  <p className="pl-small pl-muted">Undo any time: <code>solo-license init --global --remove</code></p>
                </details>
              </div>
            )}
            {anyAgentPrompt && tab === 'agent' && (
              <div className="su-body">
                <p>Paste this into any coding agent. It sets Solo License up for itself.</p>
                <Copy text={anyAgentPrompt} block />
              </div>
            )}
            {install && tab === 'plugin' && (
              <div className="su-body">
                <p>Inside Claude Code:</p>
                <CopyList lines={install.claude_plugin} />
              </div>
            )}
          </>
        )}

        {view === 'keys' && (
          <>
            <h1 className="su-h">Add keys {!wizard && <span className="su-opt">optional</span>}</h1>
            <p className="pl-small pl-muted">
              {wizard ? 'neatlogs and Jev are required before the install unlocks. Keys are stored encrypted on this machine.'
                : 'Skip this if you don’t have them. Built-in rules work without any key.'}
            </p>
            <div className="pl-fields su-keys">
              <SecretInput label="TypeSafe API key (Jev)" field="typesafe_api_key" values={keys} settings={settings}
                onChange={(p) => setKeys((k) => ({ ...k, ...p }))} placeholder="ts_…" />
              <SecretInput label="neatlogs API key" field="neatlogs_api_key" values={keys} settings={settings}
                onChange={(p) => setKeys((k) => ({ ...k, ...p }))} placeholder="Paste your neatlogs key" />
            </div>
            <div className="su-actions">
              <button type="button" className="btn btn-line btn-sm" disabled={saving || !Object.values(keys).some((v) => String(v).trim())} onClick={saveKeys}>
                {saving ? 'Saving…' : 'Save keys'}
              </button>
              <TestRow label="Test Jev" okText="Jev answered" disabled={!settings.jev_enabled}
                onTest={async () => { const r = await api.testJev(); return { ok: r.ok, message: '' }; }} />
              <TestRow label="Test neatlogs" okText="Trace sent and read back" disabled={!settings.neatlogs_enabled && !keys.neatlogs_api_key.trim()}
                onTest={() => api.testNeatlogs({ neatlogs_api_key: keys.neatlogs_api_key, neatlogs_project: keys.neatlogs_project })}
                translate={plainNeatlogsError} />
            </div>
          </>
        )}

        {view === 'connect' && (
          <>
            <h1 className="su-h">{connected ? `${spec?.label} is connected` : `Waiting for ${spec?.label || 'your agent'}…`}</h1>
            {connected ? (
              <p className="su-ok">
                {connected.decisions} decision{connected.decisions === 1 ? '' : 's'} so far, last {when(connected.last_seen)}.
              </p>
            ) : (
              <p className="su-wait">
                Open {spec?.label || 'your agent'} in your repository and ask it to <b>“run the tests”</b>. It shows up here
                as soon as it does.
              </p>
            )}
          </>
        )}
      </section>

      <nav className="su-nav">
        <button type="button" className="btn btn-ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
        {last ? (
          <Link to="/app" className="btn btn-ink">Open the dashboard →</Link>
        ) : (
          <button type="button" className="btn btn-ink" disabled={blocked} onClick={() => setStep(step + 1)}>
            {view === 'keys' && !wizard ? 'Skip or continue →' : 'Next →'}
          </button>
        )}
      </nav>
    </div>
  );
}
