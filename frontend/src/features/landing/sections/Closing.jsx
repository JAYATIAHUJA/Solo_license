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
        <p className="mono">Start</p>
        <h2 className="lp-closing-title serif">
          <MaskWords text="Let it" /> <em className="italic"><MaskWords text="earn" delay={0.1} /></em> <MaskWords text="it." delay={0.16} />
        </h2>
        <p className="lp-copy">Two commands. Install the plugin, keep the API running, and work as usual. Every repo starts at zero trust - and the agent earns the rest.</p>
        <div className="lp-hero-cta">
          <Magnetic><Link to="/app" className="btn btn-ink">Open the dashboard <HandIcon name="arrow-right" size={16} /></Link></Magnetic>
          <Magnetic><a href="https://github.com/JAYATIAHUJA/Solo_license" className="btn btn-line">Read the code</a></Magnetic>
        </div>
      </div>
    </section>
  );
}
