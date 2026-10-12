import { useEffect, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { introPending } from '../../lib/signature.js';
import { PaperGrain } from '../../components/shader/PaperBackdrop.jsx';
import { Gate } from './gate/Gate.jsx';
import { Nav } from './sections/Nav.jsx';
import { Hero } from './sections/Hero.jsx';
import { Ticker } from './sections/Ticker.jsx';
import { Terminal } from './scenes/Terminal.jsx';
import { Problem } from './scenes/Problem.jsx';
import { Journey } from './scenes/Journey.jsx';
import { AgentGraph } from './scenes/AgentGraph.jsx';
import { Crash } from './scenes/Crash.jsx';
import { LedgerTrack } from './scenes/LedgerTrack.jsx';
import { ProductTour } from './scenes/ProductTour.jsx';
import { Altimeter } from './scenes/Altimeter.jsx';
import { Facts } from './sections/Facts.jsx';
import { Faq } from './sections/Faq.jsx';
import { Closing } from './sections/Closing.jsx';
import { Footer } from './sections/Footer.jsx';
import { useSmoothScroll } from './useSmoothScroll.js';
import './landing.css';
import './scenes/scenes.css';

/** Marketing site, told as one coding agent's story. Static sections live in
 *  ./sections, scroll-driven pinned scenes in ./scenes, the intro in ./gate. */
export function LandingPage() {
  const [intro, setIntro] = useState(introPending);
  useSmoothScroll();

  // A reload starts at the top with the intro, not mid-story under it.
  useEffect(() => {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
    if (introPending()) window.scrollTo(0, 0);
  }, []);
  // Freeze smooth scrolling while the intro is up.
  useEffect(() => {
    if (intro) window.__lenis?.stop();
    else window.__lenis?.start();
  }, [intro]);

  return (
    <div className="lp">
      <AnimatePresence>{intro && <Gate onDone={() => setIntro(false)} />}</AnimatePresence>
      <PaperGrain opacity={0.35} />
      <Nav />
      <Altimeter />
      <main>
        <Hero />
        <Ticker />
        <Terminal />
        <Problem />
        <Journey />
        <AgentGraph />
        <Crash />
        <ProductTour />
        <LedgerTrack />
        <Facts />
        <Faq />
        <Closing />
      </main>
      <Footer onReplayIntro={() => { window.scrollTo(0, 0); setIntro(true); }} />
    </div>
  );
}
