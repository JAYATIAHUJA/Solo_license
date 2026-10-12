import { useState } from 'react';
import { Link } from 'react-router-dom';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SectionHead } from '../Reveal.jsx';

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

export function Install() {
  const [agent, setAgent] = useState(AGENTS[0]);
  return (
    <section className="lp-section lp-install" id="install">
      <SectionHead label="Works with your agent" />
      <div className="lp-install-agents" role="tablist" aria-label="Your coding agent">
        {AGENTS.map((a) => (
          <button key={a.key} type="button" role="tab" aria-selected={a.key === agent.key}
            className={`lp-install-chip ${a.key === agent.key ? 'is-on' : ''}`} onClick={() => setAgent(a)}>
            {a.label}
          </button>
        ))}
      </div>

      <p className="lp-install-note"><b>{agent.how}.</b> {agent.note || 'Found and wired by the command above.'}</p>

      <div className="lp-hero-cta">
        <Link to="/onboarding" className="btn btn-ink">Open the setup guide <HandIcon name="arrow-right" size={16} /></Link>
        <Link to="/app" className="btn btn-line">See the dashboard</Link>
      </div>
    </section>
  );
}
