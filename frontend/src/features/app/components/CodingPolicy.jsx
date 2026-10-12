import { useEffect, useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { classLabel, formatToolRules, isMcpClass, parseToolRules } from '../../../lib/action-classes.js';
import { CopyCommand } from '../../../components/CopyCommand.jsx';

const LEVEL_LABEL = ['L0 · asks every time', 'L1 · approved commands only', 'L2 · whole class'];
const LEVEL_SHORT = ['L0 · Ask', 'L1 · Approved', 'L2 · Alone'];
const CLASS_NAME = {
  read: 'Read files', 'test-run': 'Run tests', 'lint-format': 'Lint & format', build: 'Build',
  'file-edit': 'Edit files', 'git-local': 'Local git', 'install-dep': 'Install packages',
  'network-fetch': 'Network requests', 'git-remote': 'Push / pull',
};
const lines = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean);

function toolRule(r) {
  if (r.forbidden) return 'never allowed';
  return [r.risk, r.ceiling != null ? `at most L${r.ceiling}` : ''].filter(Boolean).join(', ');
}

function Rules({ rules }) {
  if (!rules) return null;
  const caps = Object.entries(rules.ceilings || {});
  const tools = Object.entries(rules.tools || {});
  return (
    <ul className="cp-rules">
      {rules.freeze && <li><b>Frozen</b>: every action asks.</li>}
      {caps.map(([k, v]) => <li key={k}>{isMcpClass(k) ? classLabel(k) : <code>{k}</code>} at most L{v}</li>)}
      {tools.map(([p, r]) => <li key={`t-${p}`}>tool <code>{p}</code>: {toolRule(r)}</li>)}
      {(rules.deny_commands || []).map((c) => <li key={`c-${c}`}>never run <code>{c}</code></li>)}
      {(rules.deny_paths || []).map((p) => <li key={`p-${p}`}>never touch <code>{p}</code></li>)}
      {!rules.freeze && !caps.length && !tools.length && !(rules.deny_commands || []).length && !(rules.deny_paths || []).length && <li>No extra rules.</li>}
    </ul>
  );
}

/** This machine's coding policy (per repo or all), next to the team's file. */
export function CodingPolicy() {
  const { setToast } = useStore();
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState('*');
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ classes: {}, commands: '', paths: '', tools: '', freeze: false });
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.coding().then((r) => setRepos((r.repos || []).map((x) => x.repo))).catch(() => {}); }, []);
  useEffect(() => {
    api.codingPolicy(repo).then((body) => {
      setData(body);
      const mine = repo === '*' ? body.local_all : body.local;
      setForm({
        classes: { ...(mine?.ceilings || {}) },
        commands: (mine?.deny_commands || []).join('\n'),
        paths: (mine?.deny_paths || []).join('\n'),
        tools: formatToolRules(mine?.tools),
        freeze: Boolean(mine?.freeze),
      });
    }).catch(() => {});
  }, [repo]);

  async function save() {
    setSaving(true);
    try {
      const body = await api.saveCodingPolicy({
        repo, classes: form.classes, deny_commands: lines(form.commands), deny_paths: lines(form.paths),
        tools: parseToolRules(form.tools), freeze: form.freeze,
      });
      setData(body);
      setToast({ kind: 'ok', text: 'Policy saved and recorded in the ledger.', at: Date.now() });
    } catch (cause) {
      setToast({ kind: 'error', text: cause.message, at: Date.now() });
    } finally {
      setSaving(false);
    }
  }

  if (!data) return <p className="pl-muted pl-small">Loading policy…</p>;
  const builtIn = data.built_in || {};
  const setLevel = (key, v) => setForm((f) => {
    const classes = { ...f.classes };
    if (v === '') delete classes[key]; else classes[key] = v;
    return { ...f, classes };
  });
  const effective = {
    ...data.effective,
    ceilings: Object.fromEntries(Object.entries(data.effective.ceilings || {})
      .filter(([k, v]) => v < (builtIn[k] ?? (isMcpClass(k) ? 2 : 0)))),
  };

  return (
    <div className="cp">
      <div className="cp-top">
        <label className="field cp-repo">
          <span>Applies to</span>
          <select className="input" value={repo} onChange={(e) => setRepo(e.target.value)}>
            <option value="*">All repositories on this machine</option>
            {repos.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label className={`cp-freeze ${form.freeze ? 'is-on' : ''}`}>
          <input type="checkbox" checked={form.freeze} onChange={(e) => setForm((f) => ({ ...f, freeze: e.target.checked }))} />
          <span className="cp-switch" aria-hidden="true" />
          <span><b>Freeze</b><small>Every action asks, whatever was earned</small></span>
        </label>
      </div>

      <div className="cp-grid">
        <div className="cp-main">
          <section className="cp-block">
            <header>
              <h3>How far each kind of action may go</h3>
              <p>Pick the most it may do on its own. “Default” keeps the built-in limit.</p>
            </header>
            <ul className="cp-levels">
              {Object.entries(builtIn).filter(([, max]) => max > 0).map(([key, max]) => {
                const value = form.classes[key] ?? '';
                return (
                  <li key={key}>
                    <span className="cp-level-name">
                      <b>{CLASS_NAME[key] || classLabel(key)}</b>
                      <code>{key}</code>
                    </span>
                    <span className="cp-seg" role="radiogroup" aria-label={`${key} limit`}>
                      {[0, 1, 2].filter((l) => l < max).map((l) => (
                        <button key={l} type="button" role="radio" aria-checked={value === l}
                          className={value === l ? 'is-on' : ''} onClick={() => setLevel(key, l)} title={LEVEL_LABEL[l]}>
                          {LEVEL_SHORT[l]}
                        </button>
                      ))}
                      <button type="button" role="radio" aria-checked={value === ''} className={value === '' ? 'is-on' : ''}
                        onClick={() => setLevel(key, '')} title={`Built-in: up to L${max}`}>
                        Default · L{max}
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="cp-block">
            <header>
              <h3>Never allowed</h3>
              <p>Blocked at every level. One per line, <code>*</code> matches anything.</p>
            </header>
            <div className="cp-never">
              <label className="field">
                <span>Commands</span>
                <textarea className="input" rows={4} value={form.commands} onChange={(e) => setForm((f) => ({ ...f, commands: e.target.value }))} placeholder={'terraform destroy\nkubectl delete *'} />
              </label>
              <label className="field">
                <span>Files</span>
                <textarea className="input" rows={4} value={form.paths} onChange={(e) => setForm((f) => ({ ...f, paths: e.target.value }))} placeholder={'.env\ninfra/prod/**'} />
              </label>
            </div>
            <details className="pl-more">
              <summary>MCP tool rules (advanced)</summary>
              <label className="field">
                <span>Glob, then read / write / destructive, forbidden or ceiling=0..2</span>
                <textarea className="input" rows={3} value={form.tools} onChange={(e) => setForm((f) => ({ ...f, tools: e.target.value }))} placeholder={'mcp__github__* write\nmcp__aws__* forbidden'} />
                <small className="pl-muted">Without a rule: list/get/search can reach L{data.tool_defaults?.read ?? 2}, create/update L{data.tool_defaults?.write ?? 1}, merge/delete/deploy always ask.</small>
              </label>
            </details>
          </section>

          <div className="cp-save">
            <span className="pl-small pl-muted">These can only make the agent ask more, never less.</span>
            <button type="button" className="btn btn-ink" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save policy'}</button>
          </div>
        </div>

        <aside className="cp-side">
          <section className="cp-block">
            <h3>In effect now</h3>
            <Rules rules={effective} />
            <p className="pl-small pl-muted">Version <code>{data.effective.digest}</code>, recorded with every decision.</p>
          </section>
          <section className="cp-block">
            <h3>Team file</h3>
            {repo === '*' ? (
              <p className="pl-small pl-muted">Pick a repository to see its <code>{data.file_path}</code>.</p>
            ) : data.file ? <Rules rules={data.file} /> : (
              <>
                <p className="pl-small pl-muted">None in this repository yet. Commit one so changes get reviewed like code:</p>
                <CopyCommand text="solo-license policy init" />
              </>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
