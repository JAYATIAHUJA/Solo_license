import { levelCopy } from '../../../lib/copy.js';
import { CEILING_FIELD } from '../../app/components/IntegrationFields.jsx';
import { jobsName, limitVerb, shortMoney } from '../../app/components/words.js';

const RECOMMENDED = 1;

export function StepRules({ form, set, data }) {
  const pickLevel = (key, id) => set({ starting_levels: { ...form.starting_levels, [key]: id } });
  const threshold = Number(form.promotion_clean_runs) || 1;
  return (
    <>
      <h1 className="ob-title">Where should the agent start?</h1>
      <p className="ob-sub">
        Each job type earns freedom on its own. After {threshold} correct job{threshold === 1 ? '' : 's'} in a row it moves up one step;
        if anything goes wrong it is paused until you check.
      </p>

      {data.task_classes.map((tc) => {
        const level = form.starting_levels[tc.key] ?? RECOMMENDED;
        const field = CEILING_FIELD[tc.key];
        const limit = shortMoney(field ? form[field] : tc.ceiling);
        return (
          <section key={tc.key} className="ob-section">
            <h2>{jobsName(data, tc.key)}</h2>
            <div className="pl-choices" role="radiogroup" aria-label={`${jobsName(data, tc.key)}: starting point`}>
              {[0, 1, 2, 3].map((id) => {
                const words = levelCopy(id, limit);
                return (
                  <label key={id} className={`pl-choice ${level === id ? 'is-on' : ''}`}>
                    <input type="radio" name={`start-${tc.key}`} checked={level === id} onChange={() => pickLevel(tc.key, id)} />
                    <span>
                      <b>{words.short}</b>
                      {id === RECOMMENDED && <span className="pl-tag">Recommended</span>}
                      <small>{words.long}</small>
                    </span>
                  </label>
                );
              })}
            </div>
            {field && (
              <label className="field ob-narrow">
                <span>Most the agent may {limitVerb(tc.key)} on its own ($)</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  step="5"
                  value={form[field]}
                  onChange={(e) => set({ [field]: Math.max(0, Number(e.target.value) || 0) })}
                />
                <small>Anything bigger always waits for your OK.</small>
              </label>
            )}
          </section>
        );
      })}

      <section className="ob-section">
        <label className="field ob-narrow">
          <span>Correct jobs needed before more freedom</span>
          <input
            className="input"
            type="number"
            min={1}
            max={20}
            value={form.promotion_clean_runs}
            onChange={(e) => set({ promotion_clean_runs: Math.max(1, Number(e.target.value) || 1) })}
          />
          <small>In a row, double-checked. 3 is a good start.</small>
        </label>
      </section>
    </>
  );
}
