import { Ladder } from '../../../components/domain/Ladder.jsx';
import { LEVELS } from '../../../lib/format.js';

export function StepRules({ form, set }) {
  const picked = LEVELS[form.starting_level];
  return (
    <>
      <h1 className="ob-title serif">How much <em className="italic">trust</em> on day one?</h1>
      <p className="ob-sub">Tap a rung to choose the starting level. It is <b>{picked.code} — {picked.name}</b>: {picked.who.toLowerCase()}.</p>
      <Ladder level={form.starting_level} cleanRuns={0} threshold={form.promotion_clean_runs} compact onPick={(id) => set({ starting_level: id })} />
      <div className="ob-row">
        <label className="field">
          <span>Clean runs to promote</span>
          <input className="input" type="number" min={1} max={20} value={form.promotion_clean_runs} onChange={(e) => set({ promotion_clean_runs: Math.max(1, Number(e.target.value) || 1) })} />
          <small>Consecutive verified runs needed to climb one rung.</small>
        </label>
        <label className="field">
          <span>L2 auto-refund ceiling ($)</span>
          <input className="input" type="number" min={0} step="5" value={form.l2_auto_refund_ceiling} onChange={(e) => set({ l2_auto_refund_ceiling: Math.max(0, Number(e.target.value) || 0) })} />
          <small>At L2, refunds above this wait for a human.</small>
        </label>
      </div>
    </>
  );
}
