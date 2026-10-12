import { Link } from 'react-router-dom';
import { Reveal } from './Reveal.jsx';
import { CHAPTERS } from './scenes/ProductTour.jsx';

/* The landing page on a phone: the same idea, told in a few light sections.
   No pinned scenes, shaders or smooth scrolling - just short fades. */
const STEPS = [
  ['Starts at zero', 'In a new repo every kind of action asks you first - run the tests, install a package, push.'],
  ['Earns from results', 'Approved and verified a few times, that kind of action runs without asking - in this repo only.'],
  ['Checked every turn', 'At the end of each turn the diff is compared with your request and the tests run. Over-edits are sent back.'],
  ['Loses it at once', 'One failure, one over-edit or one "This was wrong" drops it back to asking - and the agent is told what to undo.'],
  ['Never the dangerous stuff', 'Force-push to main, rm -rf, curl | sh, DROP DATABASE: denied at any level.'],
];

export function PhoneLanding() {
  return (
    <>
      <section className="lp-section ph-section" id="how">
        <p className="mono lp-kicker">How it works</p>
        <ol className="ph-steps">
          {STEPS.map(([title, text], i) => (
            <Reveal as="li" key={title} delay={i * 0.04} y={16}>
              <span className="mono">{String(i + 1).padStart(2, '0')}</span>
              <div><b>{title}</b><p>{text}</p></div>
            </Reveal>
          ))}
        </ol>
      </section>

      <section className="lp-section ph-section" id="tour">
        <p className="mono lp-kicker">The product</p>
        <div className="ph-cards">
          {CHAPTERS.map((c) => (
            <Reveal key={c.key} y={16} className="ph-card">
              <b>{c.title}</b>
              <code>{c.cmd}</code>
              <p>{c.text}</p>
            </Reveal>
          ))}
        </div>
        <Link to="/install" className="btn btn-ink ph-cta">Install in one command</Link>
      </section>
    </>
  );
}
