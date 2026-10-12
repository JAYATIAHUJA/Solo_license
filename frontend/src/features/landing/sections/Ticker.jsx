import { useRef } from 'react';
import { motion, useAnimationFrame, useMotionValue, useScroll, useSpring, useTransform, useVelocity } from 'motion/react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const WORDS = [
  'Hooks, not hope',
  'Earned per action class',
  'Over-editing gets sent back',
  'One failure → L0',
  'Subagents earn their own license',
  'MCP servers earn per tool',
  'Budget caps stop the spend',
  'Flag it, and the agent is told',
  'Every change is a commit',
  'Asks you → Runs what you approved → Runs alone',
];

const wrap = (min, max, v) => ((((v - min) % (max - min)) + (max - min)) % (max - min)) + min;

/** Marquee whose speed and direction follow your scroll
 *  (reactbits' ScrollVelocity idea). */
export function Ticker({ baseVelocity = -2.2 }) {
  const x = useMotionValue(0);
  const { scrollY } = useScroll();
  const velocity = useSpring(useVelocity(scrollY), { damping: 50, stiffness: 400 });
  const factor = useTransform(velocity, [0, 1000], [0, 5], { clamp: false });
  const direction = useRef(1);
  const translate = useTransform(x, (v) => `${wrap(-50, 0, v)}%`);

  useAnimationFrame((_, delta) => {
    let move = direction.current * baseVelocity * (delta / 1000);
    if (factor.get() < 0) direction.current = -1;
    else if (factor.get() > 0) direction.current = 1;
    move += direction.current * move * factor.get();
    x.set(x.get() + move);
  });

  const row = WORDS.map((w) => (
    <span key={w} className="lp-tick-item">{w} <HandIcon name="spark" size={16} /></span>
  ));
  return (
    <div className="lp-ticker" aria-hidden="true">
      <motion.div className="lp-ticker-track" style={{ x: translate }}>{row}{row}</motion.div>
    </div>
  );
}
