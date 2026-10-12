import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchCircle } from '../../../components/sketch/Sketch.jsx';
import { MaskWords } from '../Reveal.jsx';
import { AskBar } from './AskBar.jsx';
import { Magnetic } from '../../../components/fx/Magnetic.jsx';

const META = [
  ['For', 'Claude Code, Codex, Cursor, Gemini, Antigravity, Copilot, Grok, Windsurf and more'],
  ['Earns', 'Auto-approval per action class, from verified turns: the diff against your request, then the tests'],
  ['Controls', 'Subagents, MCP servers and spend: each earns its own license or stops at its cap'],
];

export function Hero() {
  return (
    <section className="lp-hero" id="top">
      <div className="lp-hero-grid">
        <div className="lp-hero-copy">
          <motion.p className="mono lp-kicker" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
            The control layer for coding agents
          </motion.p>
          <h1 className="lp-h1 serif">
            <MaskWords text="Autonomy" animateOnMount />{' '}
            <MaskWords text="is" animateOnMount delay={0.12} />{' '}
            <SketchCircle delay={1.1}><em className="italic"><MaskWords text="earned," animateOnMount delay={0.18} /></em></SketchCircle>
            <br />
            <MaskWords text="not assumed." animateOnMount delay={0.26} />
          </h1>
          <motion.div className="lp-hero-cta" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.75, duration: 0.8 }}>
            <AskBar />
            <Magnetic><Link to="/app" className="btn btn-ink lp-hero-open">Open dashboard <HandIcon name="arrow-right" size={16} /></Link></Magnetic>
          </motion.div>
        </div>
      </div>

      <div className="lp-hero-meta">
        {META.map(([k, v], i) => (
          <motion.div key={k} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9 + i * 0.1 }}>
            <span className="mono muted">{k}</span>
            <p>{v}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
