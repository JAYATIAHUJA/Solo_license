import { useEffect, useRef, useState } from 'react';
import { animate, useInView } from 'motion/react';
import { SectionHead } from '../Reveal.jsx';

const FACTS = [
  { n: 0, label: 'Prompts for npm test once it is earned in a repo' },
  { n: 1, label: 'Failure it takes to lose a license' },
  { n: 1, label: 'Check per turn - never one per edit' },
  { n: 0, label: 'Actions allowed silently if the gate is down' },
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
      <SectionHead index="011" label="By the numbers" />
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
