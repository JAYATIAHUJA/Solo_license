import { useEffect, useState } from 'react';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';

const LEVEL_LABEL = ['L0 · asks every time', 'L1 · approved commands only', 'L2 · whole class'];
const lines = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean);

function Rules({ rules }) {
  if (!rules) return null;
  const caps = Object.entries(rules.ceilings || {});
  return (
    <ul className="cp-rules pl-small">
      {rules.freeze && <li><b>Frozen</b>: every action asks.</li>}
      {caps.map(([k, v]) => <li key={k}><code>{k}</code> at most L{v}</li>)}
      {(rules.deny_commands || []).map((c) => <li key={`c-${c}`}>never run <code>{c}</code></li>)}
      {(rules.deny_paths || []).map((p) => <li key={`p-${p}`}>never touch <code>{p}</code></li>)}
      {!rules.freeze && !caps.length && !(rules.deny_commands || []).length && !(rules.deny_paths || []).length && <li>No extra rules.</li>}
    </ul>
  );
}

/** This machine's coding policy (per repo or all), next to the team's file. */
export function CodingPolicy() {
  const { setToast } = useStore();
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState('*');
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ classes: {}, commands: '', paths: '', freeze: false });
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
        freeze: Boolean(mine?.freeze),
      });
    }).catch(() => {});
  }, [repo]);

  async function save() {
    setSaving(true);
    try {
      const body = await api.saveCodingPolicy({
        repo, classes: form.classes, deny_commands: lines(form.commands), deny_paths: lines(form.paths), freeze: form.freeze,
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
  return (
    <div className="cp">
      <label className="field cp-repo">
        <span>Applies to</span>
        <select className="input" value={repo} onChange={(e) => setRepo(e.target.value)}>
          <option value="*">All repositories on this machine</option>
          {repos.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>

      <div className="cp-cols">
        <div className="cp-col">
          <h3>Team policy <small className="pl-muted">({data.file_path} in the repo)</small></h3>
          {repo === '*' ? (
            <p className="pl-small pl-muted">Each repository can commit its own file. Pick a repository to see it.</p>
          ) : data.file ? <Rules rules={data.file} /> : (
            <p className="pl-small pl-muted">None yet. Create one with <code>solo-license policy init</code> and commit it, so privilege changes are reviewed like code.</p>
          )}
          <h3>In effect now</h3>
          <Rules rules={{ ...data.effective, ceilings: Object.fromEntries(Object.entries(data.effective.ceilings || {}).filter(([k, v]) => v < (builtIn[k] ?? 0))) }} />
          <p className="pl-small pl-muted">Policy <code>{data.effective.digest}</code> · recorded with every decision.</p>
        </div>

        <div className="cp-col">
          <h3>This machine</h3>
          <div className="cp-classes">
            {Object.entries(builtIn).filter(([, max]) => max > 0).map(([key, max]) => (
              <label key={key} className="cp-class">
                <code>{key}</code>
                <select className="input" value={form.classes[key] ?? ''} onChange={(e) => {
                  const v = e.target.value;
                  setForm((f) => {
                    const classes = { ...f.classes };
                    if (v === '') delete classes[key]; else classes[key] = Number(v);
                    return { ...f, classes };
                  });
                }}>
                  <option value="">Built-in (up to L{max})</option>
                  {[0, 1, 2].filter((l) => l < max).map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
                </select>
              </label>
            ))}
          </div>
          <label className="field">
            <span>Never run (one per line, * allowed)</span>
            <textarea className="input" rows={3} value={form.commands} onChange={(e) => setForm((f) => ({ ...f, commands: e.target.value }))} placeholder={'terraform destroy\nkubectl delete *'} />
          </label>
          <label className="field">
            <span>Never touch these files (globs)</span>
            <textarea className="input" rows={3} value={form.paths} onChange={(e) => setForm((f) => ({ ...f, paths: e.target.value }))} placeholder={'.env\ninfra/prod/**'} />
          </label>
          <label className="cp-freeze">
            <input type="checkbox" checked={form.freeze} onChange={(e) => setForm((f) => ({ ...f, freeze: e.target.checked }))} />
            <span><b>Freeze</b> - every action asks, whatever has been earned</span>
          </label>
          <div className="pl-actions">
            <button type="button" className="btn btn-ink btn-sm" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save policy'}</button>
          </div>
          <p className="pl-small pl-muted">These settings can only make the agent ask more: the strictest of the built-in rules, the team file and this machine always wins.</p>
        </div>
      </div>
    </div>
  );
}
