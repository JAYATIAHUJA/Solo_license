import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SectionHead } from '../Reveal.jsx';

const REPO = 'git+https://github.com/JAYATIAHUJA/Solo_license';

/* Kept in step with sololicense/coding/agents.py; static so the landing page
   works without the API. */
const AGENTS = [
  { key: 'claude-code', label: 'Claude Code', how: 'HTTP hooks, or the plugin', note: 'GLM via z.ai runs inside Claude Code: covered.' },
  { key: 'codex', label: 'Codex CLI', how: 'Command hooks', note: 'Trust the project hooks once with /hooks.' },
  { key: 'cursor', label: 'Cursor', how: 'Command hooks', note: 'IDE agent and cursor-agent.' },
  { key: 'gemini', label: 'Gemini CLI', how: 'Command hooks', note: '' },
  { key: 'antigravity', label: 'Antigravity', how: 'Command hooks', note: '' },
  { key: 'copilot', label: 'Copilot CLI', how: 'Command hooks', note: '' },
  { key: 'grok', label: 'Grok Build', how: 'HTTP hooks', note: 'Trust the hooks once with /hooks-trust.' },
  { key: 'windsurf', label: 'Windsurf', how: 'Command hooks', note: 'Blocks forbidden actions; Windsurf’s own settings decide the rest.' },
  { key: 'kiro', label: 'Kiro', how: 'Command hooks', note: '' },
  { key: 'cline', label: 'Cline', how: 'Hook scripts', note: 'Enable Hooks in Cline’s settings.' },
  { key: 'opencode', label: 'OpenCode', how: 'Plugin', note: 'How Groq models are usually used for coding.' },
];

function Copy({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(text)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
    .catch(() => {});
  return (
    <div className="lp-install-line">
      <code>{text}</code>
      <button type="button" className="btn btn-ink btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
    </div>
  );
}

export function Install() {
  const [agent, setAgent] = useState(AGENTS[0]);
  const prompt = `Install Solo License in this repo for ${agent.label}: run \`uv tool install ${REPO}\`, then \`solo-license init --agent ${agent.key}\`. Change nothing else, and tell me to keep \`solo-license serve\` running.`;
  return (
    <section className="lp-section lp-install" id="install">
      <SectionHead index="010" label="Install" />
      <div className="lp-split">
        <h2 className="lp-h2 serif">One line. <em className="italic">Any</em> agent.</h2>
        <p className="lp-copy">
          Solo License lives in your agent’s hooks, so it works with the agent you already use. Every repo starts at
          zero trust; if the gate is not running, your agent behaves exactly as before.
        </p>
      </div>

      <div className="lp-install-agents" role="tablist" aria-label="Your coding agent">
        {AGENTS.map((a) => (
          <button key={a.key} type="button" role="tab" aria-selected={a.key === agent.key}
            className={`lp-install-chip ${a.key === agent.key ? 'is-on' : ''}`} onClick={() => setAgent(a)}>
            {a.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={agent.key} className="lp-install-box" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
          <div>
            <span className="mono muted">1 · in your repo</span>
            <Copy text={`uvx --from ${REPO} solo-license init --agent ${agent.key}`} />
          </div>
          <div>
            <span className="mono muted">2 · keep the gate running</span>
            <Copy text={`uvx --from ${REPO} solo-license serve`} />
          </div>
          <div>
            <span className="mono muted">or · let {agent.label} do it</span>
            <Copy text={prompt} />
          </div>
          <p className="lp-install-note"><b>{agent.how}.</b> {agent.note}</p>
        </motion.div>
      </AnimatePresence>

      <div className="lp-hero-cta">
        <Link to="/onboarding" className="btn btn-ink">Open the setup guide <HandIcon name="arrow-right" size={16} /></Link>
        <Link to="/app" className="btn btn-line">See the dashboard</Link>
      </div>
    </section>
  );
}
