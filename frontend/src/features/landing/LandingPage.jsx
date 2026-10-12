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
import { Detections } from './sections/Detections.jsx';
import { Remedies } from './sections/Remedies.jsx';
import { ProductTour } from './scenes/ProductTour.jsx';
import { Altimeter } from './scenes/Altimeter.jsx';
import { Facts } from './sections/Facts.jsx';
import { Faq } from './sections/Faq.jsx';
import { Closing } from './sections/Closing.jsx';
import { Footer } from './sections/Footer.jsx';
import { useSmoothScroll } from './useSmoothScroll.js';
import { usePhone } from './usePhone.js';
import { PhoneLanding } from './PhoneLanding.jsx';
import './landing.css';
import './scenes/scenes.css';

/** Marketing site, told as one coding agent's story. Static sections live in
 *  ./sections, scroll-driven pinned scenes in ./scenes, the intro in ./gate. */
export function LandingPage() {
  const phone = usePhone();
  const [intro, setIntro] = useState(() => !phone && introPending());
  useSmoothScroll(!phone);

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
      <AnimatePresence>{intro && !phone && <Gate onDone={() => setIntro(false)} />}</AnimatePresence>
      {!phone && <PaperGrain opacity={0.35} />}
      <Nav />
      {!phone && <Altimeter />}
      {phone ? (
        <main className="lp-phone">
          <Hero />
          <PhoneLanding />
          <Faq />
          <Closing />
        </main>
      ) : (
      <main>
        <Hero />
        <Ticker />
        <Terminal />
        <Problem />
        <Journey />
        <AgentGraph />
        <Crash />
        <Detections />
        <Remedies />
        <ProductTour />
        <LedgerTrack />
        <Facts />
        <Faq />
        <Closing />
      </main>
      )}
      <Footer onReplayIntro={phone ? undefined : () => { window.scrollTo(0, 0); setIntro(true); }} />
    </div>
  );
}
