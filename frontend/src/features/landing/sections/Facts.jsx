import { useEffect, useRef, useState } from 'react';
import { animate, useInView } from 'motion/react';
import { SectionHead } from '../Reveal.jsx';

const FACTS = [
  { n: 4, label: 'Rungs of autonomy, per task class' },
  { n: 3, label: 'Detection rules that can demote' },
  { n: 1, label: 'Evidence packet to restore' },
  { n: 0, label: 'Tool responses taken on trust' },
];

function Count({ to }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [value, setValue] = useState(to === 0 ? 9 : 0);
  useEffect(() => {
    if (!inView) return undefined;
    const controls = animate(to === 0 ? 9 : 0, to, { duration: 1.4, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setValue(Math.round(v)) });
    return () => controls.stop();
  }, [inView, to]);
  return <span ref={ref}>{value}</span>;
}

export function Facts() {
  return (
    <section className="lp-section">
      <SectionHead index="009" label="By the numbers" />
      <div className="lp-facts">
        {FACTS.map((f) => (
          <div key={f.label} className="lp-fact">
            <b className="serif"><Count to={f.n} /></b>
            <p>{f.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
