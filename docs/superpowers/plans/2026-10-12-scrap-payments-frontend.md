# Scrap payments frontend (PR 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The web app is only the coding agent: Coding, Permission history, Settings, Setup. Every payments page, component and API call is gone.

**Architecture:** Delete the payments screens first (backend untouched, so nothing that remains can call a missing route), then rewrite the five shared files that referenced them (`entry.jsx`, `AppShell`, `Sidebar`, `Topbar`, `Settings`), trim `IntegrationFields`, `Ledger` and `api.js`, and finally delete files nothing imports any more.

**Tech Stack:** React 19, react-router 7, Vite 7, `node --test`.

## Global Constraints

- PRD v3 F1b: remove `Overview`, `Inbox`, `AgentDesk`, `Orders`, `Runs`, `Reports`, `autopilot/`, `components/mission/`, `onboarding/` (payments wizard), `PolicyEditor`, `IntegrationFields` (Stripe/inbox parts), `/onboarding/payments`, sidebar "Payments agent".
- Contract with PR 3: from now on the app reads only `settings`, `events`, `observability` from `/api/dashboard`; `PUT /api/settings` returns the same shape.
- Landing page copy and README are PR 4, not here.
- Branch `chore/scrap-payments-frontend`; title `chore(web): remove the payments pages; coding is the whole app`.

## Verification commands (used by every task)

```powershell
cd frontend; npm test; npm run build; cd ..
```
Expected: tests pass, `vite build` prints `built in` with no unresolved import.

---

### Task 1: Delete the payments screens and rewire the shell

**Files:**
- Delete: `frontend/src/features/app/pages/{Overview,Inbox,AgentDesk,Orders,Runs,Reports}.jsx`, `pages/{inbox,reports}.css`
- Delete: `frontend/src/features/app/autopilot/`, `frontend/src/features/app/components/mission/`, `frontend/src/features/onboarding/`
- Delete: `frontend/src/features/app/components/{PolicyEditor.jsx,policy-editor.css,policyForm.js,FaultSwitch.jsx,ApproveBar.jsx,EvidencePacket.jsx,RestorePanel.jsx,ModelFields.jsx,model-fields.css}`, `frontend/test/policyForm.test.js`
- Modify: `frontend/src/entry.jsx`, `features/app/AppShell.jsx`, `components/Sidebar.jsx`, `components/Topbar.jsx`

- [ ] **Step 1:** delete the files above (`git rm -r`).
- [ ] **Step 2:** `entry.jsx` keeps routes `/`, `/landing`, `/access`, `/onboarding` (CodingSetup), `/setup`, `/app` with children index `Coding`, `ledger`, `settings`, and `*`. Imports only `Access`, `LandingPage`, `CodingSetup`, `AppShell`, `Coding`, `Ledger`, `Settings`.
- [ ] **Step 3:** `AppShell.jsx`: remove the `Autopilot` import and element, and the `/app/payments` onboarding redirect.
- [ ] **Step 4:** `Sidebar.jsx`: only `NAV` (Coding agent, Permission history, Settings); drop `PAYMENTS_NAV`, badges, business name and the "Payments agent levels" block; `useStore()` gives `session` only.
- [ ] **Step 5:** `Topbar.jsx`:

```jsx
import { Link, useLocation } from 'react-router-dom';

const TITLES = { '': 'Coding agent', ledger: 'Permission history', settings: 'Settings' };

export function Topbar({ onMenu }) {
  const { pathname } = useLocation();
  const [, , section = ''] = pathname.split('/');
  return (
    <header className="app-top">
      <button className="app-menu btn btn-ghost btn-sm" onClick={onMenu} aria-label="Open menu">Menu</button>
      <p className="app-top-title">{TITLES[section] ?? 'Coding agent'}</p>
      <div className="app-top-actions">
        {section !== '' && <Link to="/app" className="btn btn-ink btn-sm">Coding agent</Link>}
      </div>
    </header>
  );
}
```

- [ ] **Step 6:** run the verification commands. The build fails on `Settings.jsx` / `IntegrationFields.jsx` imports - expected, fixed in Task 2. Do not commit yet.

### Task 2: Settings, IntegrationFields, Ledger, api.js, store

**Files:** `features/app/pages/Settings.jsx`, `components/IntegrationFields.jsx`, `pages/Ledger.jsx`, `lib/api.js`, `lib/store.jsx`

- [ ] **Step 1: `IntegrationFields.jsx`** keeps `SecretInput`, `TestRow`, `NeatlogsFields`; `plainError` now comes from `lib/plain-errors.js` and `savedHint` is defined here:

```jsx
export function savedHint(settings, field) {
  return (field && settings?.[`${field}_hint`]) || '';
}
```
Remove `CEILING_FIELD`, `ECON_FIELDS`, `CONFIDENCE_CHOICES`, `SECRET_FIELDS`, `formFromSettings`, `validWebhook`, `AlertFields`, `StripeFields`, `InboxFields`, `TrustFields`.

- [ ] **Step 2: `Settings.jsx`** = `CodingAgentsCard` (unchanged), "Coding policy" section (unchanged), and a neatlogs card:

```jsx
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
```
`Settings()` renders a loading line until `data?.settings` exists, then the header, `CodingAgentsCard`, the policy section and `NeatlogsCard`.

- [ ] **Step 3: `Ledger.jsx`** shows coding events only (`task_class` contains `@`), no job-type select:

```jsx
const VERBS = { promote: 'earned', demote: 'lost', restore: 'was resumed at' };

function sentence(e) {
  const [cls, repo] = e.task_class.split('@');
  const why = (e.reason || '').split('\n')[0];
  if (e.kind === 'policy') {
    return <>Policy for <b>{repo === '*' ? 'all repositories' : repo}</b> changed{why ? <> - {why}</> : ''}</>;
  }
  const level = e.kind === 'demote' ? `L${e.from_level}` : `L${e.to_level}`;
  return <><code>{cls}</code> in <b>{repo}</b> {VERBS[e.kind] || 'changed to'} <b>{level}</b>{why ? <> - {why}</> : ''}</>;
}
```

- [ ] **Step 4: `api.js`** keeps `coding*`, `testJev`, `session`, `demoSession`, `me`, `dashboard: () => request('/api/dashboard')`, `saveSettings`, `testNeatlogs`. Remove the rest (and `requestText`/`saveText` if unused).
- [ ] **Step 5: `store.jsx`**: `load` takes no run id; `run` keeps a mutation result as the new data only when it is the dashboard shape: `if (result && result.settings) setData(result);`
- [ ] **Step 6:** run the verification commands -> green. Commit:

```powershell
git add -A frontend
git commit -m "chore(web): remove the payments pages; coding is the whole app"
```

### Task 3: Delete what nothing imports any more

- [ ] **Step 1:** for every file under `frontend/src`, check whether its basename is imported anywhere else; delete orphans (expected candidates: `components/words.js`, `components/Bits.jsx`, `lib/copy.js`, `components/domain/*`, `app/components/activity.css` if unused, `lib/format.js` exports only payments use).
- [ ] **Step 2:** `rg -i "refund|stripe|orders|inbox|payments" frontend/src/features/app frontend/src/lib frontend/src/entry.jsx` -> nothing.
- [ ] **Step 3:** verification commands -> green; manual: `make run-api` + `npm run dev`, open `/app`, `/app/ledger`, `/app/settings`, `/onboarding`. Commit `chore(web): drop helpers only the payments pages used`.
