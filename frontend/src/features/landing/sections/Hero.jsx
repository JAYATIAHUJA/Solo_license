import { motion } from 'motion/react';
import { SketchCircle } from '../../../components/sketch/Sketch.jsx';
import { MaskWords } from '../Reveal.jsx';
import { AskBar } from './AskBar.jsx';

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
          <motion.p
            className="lp-lede"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, duration: 0.8 }}
          >
            Install one local control layer. Your agent earns autonomy from verified work and loses it when a turn fails.
          </motion.p>
          <motion.div className="lp-hero-cta" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.75, duration: 0.8 }}>
            <AskBar />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
