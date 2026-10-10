import { Ladder } from '../../../components/domain/Ladder.jsx';
import { LEVELS } from '../../../lib/format.js';
import { CEILING_FIELD } from '../../app/components/IntegrationFields.jsx';

export function StepRules({ form, set, data }) {
  const pickLevel = (key, id) => set({ starting_levels: { ...form.starting_levels, [key]: id } });
  return (
    <>
      <h1 className="ob-title serif">How much <em className="italic">trust</em> on day one?</h1>
      <p className="ob-sub">Each kind of action earns its own license. Tap a rung to choose where it starts; clean, verified runs move it up.</p>

      <label className="field ob-narrow">
        <span>Clean runs to promote</span>
        <input
          className="input"
          type="number"
          min={1}
          max={20}
          value={form.promotion_clean_runs}
          onChange={(e) => set({ promotion_clean_runs: Math.max(1, Number(e.target.value) || 1) })}
        />
        <small>Consecutive verified runs needed to climb one rung. Shared by every action type.</small>
      </label>

      {data.task_classes.map((tc) => {
        const level = form.starting_levels[tc.key] ?? 0;
        const picked = LEVELS[level];
        const field = CEILING_FIELD[tc.key];
        return (
          <section key={tc.key} className="ob-section">
            <h2 className="ob-section-title">{tc.label}</h2>
            <p className="ob-section-sub">
              The agent may {tc.description}. Starts at <b>{picked.code} — {picked.name}</b>: {picked.who.toLowerCase()}.
            </p>
            <Ladder
              level={level}
              cleanRuns={0}
              threshold={Number(form.promotion_clean_runs) || 1}
              compact
              onPick={(id) => pickLevel(tc.key, id)}
            />
            {field && (
              <label className="field ob-narrow">
                <span>L2 auto-approve ceiling ($)</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  step="5"
                  value={form[field]}
                  onChange={(e) => set({ [field]: Math.max(0, Number(e.target.value) || 0) })}
                />
                <small>At L2, any {tc.label.toLowerCase()} above this waits for a human.</small>
              </label>
            )}
          </section>
        );
      })}
    </>
  );
}
