import { Link } from 'react-router-dom';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';
import { DitherField } from '../../../components/shader/PaperBackdrop.jsx';
import { MaskWords } from '../Reveal.jsx';
import { Magnetic } from '../../../components/fx/Magnetic.jsx';

export function Closing() {
  return (
    <section className="lp-closing">
      <DitherField className="lp-closing-shader" shape="ripple" speed={0.3} size={2.6} />
      <div className="lp-closing-inner">
        <p className="mono">(011) — Start</p>
        <h2 className="lp-closing-title serif">
          <MaskWords text="Let it" /> <em className="italic"><MaskWords text="earn" delay={0.1} /></em> <MaskWords text="it." delay={0.16} />
        </h2>
        <p className="lp-copy">Three-minute setup. Bring your own orders or load samples, add a model key if you have one, and run your first refund.</p>
        <div className="lp-hero-cta">
          <Magnetic><Link to="/onboarding" className="btn btn-ink">Set up your agent <HandIcon name="arrow-right" size={16} /></Link></Magnetic>
          <Magnetic><Link to="/app" className="btn btn-line">Open the app</Link></Magnetic>
        </div>
      </div>
    </section>
  );
}
