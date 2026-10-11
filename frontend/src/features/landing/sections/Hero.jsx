import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { SketchArrow, SketchCircle } from '../../../components/sketch/Sketch.jsx';
import { DitherField } from '../../../components/shader/PaperBackdrop.jsx';
import { MaskWords } from '../Reveal.jsx';
import { HeroSpecimen } from './HeroSpecimen.jsx';
import { AskBar } from './AskBar.jsx';
import { Magnetic } from '../../../components/fx/Magnetic.jsx';

const META = [
  ['For', 'Developers who approve the same npm test forty times a day'],
  ['Proves', 'Every turn: the diff against your request, then the tests'],
  ['Earns', 'Auto-approval per action class, only when the evidence beats the cost of a mistake'],
];

export function Hero() {
  return (
    <section className="lp-hero" id="top">
      <div className="lp-hero-grid">
        <div className="lp-hero-copy">
          <motion.p className="mono lp-kicker" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
            (001) - Earned autonomy for coding agents
          </motion.p>
          <h1 className="lp-h1 serif">
            <MaskWords text="Autonomy" animateOnMount />
            <br />
            <MaskWords text="is" animateOnMount delay={0.12} />{' '}
            <SketchCircle delay={1.1}><em className="italic"><MaskWords text="earned," animateOnMount delay={0.18} /></em></SketchCircle>
            <br />
            <MaskWords text="not assumed." animateOnMount delay={0.26} />
          </h1>
          <motion.p
            className="lp-lede"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, duration: 0.8 }}
          >
            Your coding agent has to <b>earn</b> the right to act without asking - one kind of action at a
            time, in each repo, from verified results. One failure, or one over-edit, drops it back to asking you.
          </motion.p>
          <motion.div className="lp-hero-cta" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.75, duration: 0.8 }}>
            <AskBar />
            <Magnetic><Link to="/app" className="btn btn-ink">Open the dashboard <HandIcon name="arrow-right" size={16} /></Link></Magnetic>
            <Magnetic><a href="#journey" className="btn btn-line">See how it earns</a></Magnetic>
          </motion.div>
        </div>

        <motion.div
          className="lp-hero-visual"
          initial={{ opacity: 0, clipPath: 'inset(0 0 100% 0)' }}
          animate={{ opacity: 1, clipPath: 'inset(0 0 0% 0)' }}
          transition={{ duration: 1.3, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
        >
          <DitherField className="lp-hero-shader" shape="warp" speed={0.25} size={2.4} />
          <HeroSpecimen />
          <div className="lp-note lp-note-b hand">
            <SketchArrow width={70} height={46} d="M64 42 C 44 40, 20 30, 8 6" end={[8, 6, -2.1]} delay={2} />
            one failed turn → L0
          </div>
        </motion.div>
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
