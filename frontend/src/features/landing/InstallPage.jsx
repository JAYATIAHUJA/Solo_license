import { useEffect } from 'react';
import { PaperGrain } from '../../components/shader/PaperBackdrop.jsx';
import { Nav } from './sections/Nav.jsx';
import { Install } from './sections/Install.jsx';
import { Footer } from './sections/Footer.jsx';
import './landing.css';
import './scenes/scenes.css';

/** Install on its own page, so the landing page stays a story. */
export function InstallPage() {
  useEffect(() => { window.scrollTo(0, 0); }, []);
  return (
    <div className="lp lp-install-page">
      <PaperGrain opacity={0.35} />
      <Nav />
      <main>
        <section className="lp-section lp-install-lead">
          <p className="mono lp-kicker">Install</p>
          <h1 className="lp-h2 serif">One command sets it all up.</h1>
          <pre className="lp-install-onboard">uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license onboard</pre>
          <p className="lp-copy">
            Finds your agents, shows and writes their hooks, makes this machine&rsquo;s admin key, starts the gate and
            opens the dashboard signed in. neatlogs, Jev and Entire are optional steps after that. Prefer to wire one
            agent by hand? Pick it below.
          </p>
        </section>
        <Install />
      </main>
      <Footer />
    </div>
  );
}
