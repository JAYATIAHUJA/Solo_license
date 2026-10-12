import { useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useTransform } from 'motion/react';
import { ScrambleText } from '../../../components/fx/ScrambleText.jsx';
import { Pinned } from '../Pinned.jsx';

/* Scene - the product, end to end. One chapter per surface: the CLI that
   sets it up, the dashboard, the budget, the neatlogs trace, the Entire trail,
   and the CLI that ties a turn's story together. As you scroll through a
   chapter the screen zooms onto the part that matters and marks it.
   Illustrative mockups of the real screens and commands. */
const CHAPTERS = [
  { key: 'onboard', kind: 'term', title: 'One command to set up', cmd: 'solo-license onboard',
    text: 'Finds your agents, writes their hooks, makes a local admin, starts the gate and opens the dashboard signed in.' },
  { key: 'levels', kind: 'app', title: 'Watch trust move, live', cmd: 'Dashboard · Coding agent',
    text: 'Each kind of action earns its level from verified results. One click on "This was wrong" drops it to L0 and tells the agent.' },
  { key: 'budget', kind: 'app', title: 'Caps on the spend', cmd: 'Dashboard · Budget  ·  solo-license budget',
    text: 'Per session and per day. Past a cap only reading is allowed until you resume.' },
  { key: 'neatlogs', kind: 'web', title: 'Every turn is a trace', cmd: 'neatlogs',
    text: 'Allow, ask, deny, the tool result, what the agent was told and the license change - one trace per turn.' },
  { key: 'entire', kind: 'web', title: 'Every change has a history', cmd: 'Entire',
    text: 'A failed turn points at its Entire checkpoint; promotions and demotions are commits; every PR goes through Entire Gates.' },
  { key: 'explain', kind: 'term', title: 'One turn, the whole story', cmd: 'solo-license explain',
    text: 'Decisions, what the agent was told, the license change, the trace and the checkpoint - in your terminal.' },
];

export function ProductTour() {
  return (
    <Pinned id="tour" length={CHAPTERS.length} className="sc-tour">
      {(p) => <Scene p={p} />}
    </Pinned>
  );
}

/** 0 → 1 → 0 across one chapter: zoom in, hold, zoom out. */
function zoomAt(v) {
  const x = Math.min(0.999, Math.max(0, v)) * CHAPTERS.length;
  const t = x - Math.floor(x);
  if (t < 0.2) return 0;
  if (t < 0.45) return (t - 0.2) / 0.25;
  if (t < 0.78) return 1;
  if (t < 0.95) return 1 - (t - 0.78) / 0.17;
  return 0;
}

function Scene({ p }) {
  const [active, setActive] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const [origin, setOrigin] = useState('50% 50%');
  const screenRef = useRef(null);
  useMotionValueEvent(p, 'change', (v) => {
    setActive(Math.min(CHAPTERS.length - 1, Math.floor(Math.max(0, v) * CHAPTERS.length)));
    setZoomed(zoomAt(v) > 0.6);
  });
  const scale = useTransform(p, (v) => 1 + 0.25 * zoomAt(v));
  const chapter = CHAPTERS[active];

  // Zoom toward the element this chapter marks, measured from the live layout.
  useLayoutEffect(() => {
    const screen = screenRef.current;
    const id = window.setTimeout(() => {
      const focus = screen?.querySelector('.pt-focus');
      if (!screen || !focus) return;
      const s = screen.getBoundingClientRect();
      const f = focus.getBoundingClientRect();
      const x = ((f.left + f.width / 2 - s.left) / s.width) * 100;
      const y = ((f.top + f.height / 2 - s.top) / s.height) * 100;
      setOrigin(`${Math.max(10, Math.min(90, x))}% ${Math.max(10, Math.min(90, y))}%`);
    }, 380);
    return () => window.clearTimeout(id);
  }, [active]);

  return (
    <div className="pt-wrap">
      <div className="pt-copy">
        <div className="lp-head pt-head">
          <span className="mono">(tour)</span>
          <ScrambleText className="mono" text="The product, end to end" />
        </div>
        <ol className="pt-list">
          {CHAPTERS.map((c, i) => (
            <li key={c.key} className={i === active ? 'is-active' : i < active ? 'is-done' : ''}>
              <span className="mono pt-num">{String(i + 1).padStart(2, '0')}</span>
              <div>
                <b>{c.title}</b>
                <code className="pt-cmd">{c.cmd}</code>
                <p className="pt-text" aria-hidden={i !== active}>{c.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className={`pt-device is-${chapter.kind}`}>
        <div className="pt-chrome">
          <i /><i /><i />
          <span className="mono">{chapter.kind === 'term' ? 'zsh - shop-api' : chapter.kind === 'web'
            ? (chapter.key === 'neatlogs' ? 'app.neatlogs.com/traces/98951fde' : 'entire.io/gh/acme/shop-api/trails/58')
            : '127.0.0.1:8000/app'}</span>
        </div>
        <div className="pt-screen" ref={screenRef}>
          <motion.div className={`pt-zoom ${zoomed ? 'is-zoomed' : ''}`} style={{ scale, transformOrigin: origin }}>
            <AnimatePresence mode="wait">
              <motion.div key={chapter.key} className="pt-page" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -18 }} transition={{ duration: 0.3 }}>
                {MOCKS[chapter.key]()}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
        <span className="pt-caption mono">illustrative</span>
      </div>
    </div>
  );
}

const MOCKS = {
  onboard: () => (
    <pre className="pt-term">
      <span className="pt-dim">$ </span>solo-license onboard{'\n'}
      <span className="pt-dim">[1/6]</span> Agents: Claude Code, Codex, OpenCode{'\n'}
      <span className="pt-dim">[2/6]</span> Hooks for ~/code/shop-api: <span className="pt-ok">+ .claude/settings.local.json</span>{'\n'}
      {'      '}<span className="pt-ok">+ .codex/hooks.json  + .opencode/plugins/solo-license.ts</span>{'\n'}
      <span className="pt-dim">[3/6]</span> Local admin kept in macOS Keychain{'\n'}
      <span className="pt-dim">[4/6]</span> Gate running at http://127.0.0.1:8000{'\n'}
      <span className="pt-focus pt-mark"><span className="pt-dim">[5/6]</span> OK: the gate answered a read in shop-api</span>{'\n'}
      <span className="pt-dim">[6/6]</span> Dashboard: http://127.0.0.1:8000/onboarding{'\n'}
      {'      '}- neatlogs: optional  - Jev: optional  - Entire: found{'\n'}
      {'      '}Opened your browser, signed in as the local admin.
    </pre>
  ),
  levels: () => (
    <div className="pt-app">
      <p className="pt-app-h">What your agent may do alone in <b>shop-api</b></p>
      <div className="pt-cards">
        {[['Run the tests', 'L2', 'ok', 'runs on its own'], ['Edit files', 'L1', 'ok', 'approved patterns'],
          ['Install dependencies', 'L0', 'bad', 'flagged by Jayati']].map(([n, l, tone, s], i) => (
          <div key={n} className={`pt-card ${i === 2 ? 'pt-focus' : ''}`}>
            <span className="pt-small">{n}</span>
            <b className="serif">{l}</b>
            <span className={`pt-chip ${tone}`}>{s}</span>
          </div>
        ))}
      </div>
      <div className="pt-row">
        <code>npm install left-pad</code>
        <span className="pt-chip bad">Failed</span>
        <span className="pt-btn pt-mark">This was wrong</span>
      </div>
      <div className="pt-row"><code>npm test</code><span className="pt-chip ok">Allowed · L2</span><span className="pt-chip ok">Verified</span></div>
      <div className="pt-row"><code>git push --force origin main</code><span className="pt-chip bad">Denied</span></div>
    </div>
  ),
  budget: () => (
    <div className="pt-app">
      <div className="pt-stats">
        <div><b>$2.01</b><span>spent today</span></div>
        <div><b>$41.50</b><span>developer time saved</span></div>
        <div><b>1</b><span>session stopped at a cap</span></div>
      </div>
      <div className="pt-meter"><span>shop-api today</span><i style={{ width: '34%' }} /><span>$1.70 of $5.00</span></div>
      <div className="pt-row pt-focus pt-mark">
        <span><b>$1.24</b> claude-code (sonnet) · session cap $1.00</span>
        <span className="pt-chip bad">Stopped: session cap</span>
        <span className="pt-btn">Resume</span>
      </div>
      <div className="pt-row"><span><b>$0.46</b> codex (gpt-5) · estimated from tokens</span><span className="pt-chip ok">Under the cap</span></div>
    </div>
  ),
  neatlogs: () => (
    <div className="pt-trace">
      <p className="pt-app-h">coding.turn · <b>“add left-pad”</b> · 9 spans</p>
      {[['turn.start', 0, 8, ''], ['gate.ask', 6, 10, ''], ['gate.approved_by_person', 14, 10, ''],
        ['tool.failed', 22, 22, 'err'], ['remediation.sent', 42, 12, 'err'], ['license.demote', 52, 12, 'err focus'],
        ['gate.deny  git push --force', 62, 12, 'err'], ['detection.forbidden_action', 72, 14, 'err'], ['turn.end', 86, 12, '']]
        .map(([n, x, w, k]) => (
          <div key={n} className={`pt-span ${k.includes('err') ? 'is-err' : ''} ${k.includes('focus') ? 'pt-focus pt-mark' : ''}`}>
            <span className="mono">{n}</span>
            <i style={{ marginLeft: `${x}%`, width: `${w}%` }} />
          </div>
        ))}
    </div>
  ),
  entire: () => (
    <div className="pt-app">
      <p className="pt-app-h">Trail #58 · <b>feat(coding): MCP tools earn a license per server</b></p>
      <div className="pt-gates">
        {['Checks passed', 'Findings: no blocking issues', 'Up to date', 'Approved'].map((g) => <span key={g} className="pt-chip ok">{g}</span>)}
      </div>
      <div className="pt-row pt-focus pt-mark">
        <span>Failed turn → checkpoint <code>a1b2c3d4e5f6</code></span>
        <code>entire checkpoint explain a1b2c3d4e5f6</code>
      </div>
      <div className="pt-row"><code>3f9c2a1</code><span>license: demote(install-dep@shop-api) L2 → L0</span></div>
      <div className="pt-row"><code>8d41b07</code><span>license: promote(test-run@shop-api) L1 → L2</span></div>
    </div>
  ),
  explain: () => (
    <pre className="pt-term">
      <span className="pt-dim">$ </span>solo-license explain{'\n'}
      Turn 41 in shop-api: “add left-pad”  status: failed{'\n'}
      Decisions{'\n'}
      {'  '}ask   npm install left-pad | install-dep at L2 | person | <span className="pt-bad">failed</span>{'\n'}
      {'  '}deny  git push --force origin main | hard-deny{'\n'}
      Agent was told: undo the partial change (git checkout -- package.json package-lock.json){'\n'}
      License: install-dep demote L2 -&gt; L0 | ledger commit 3f9c2a1{'\n'}
      <span className="pt-focus pt-mark">neatlogs trace: https://app.neatlogs.com/traces/98951fde{'\n'}
      Entire checkpoint: entire checkpoint explain a1b2c3d4e5f6</span>{'\n'}
      Rewind: press Rewind on this turn - changes are stashed, never deleted
    </pre>
  ),
};
