import { levelCopy } from '../../../lib/copy.js';
import { CEILING_FIELD, TrustFields } from '../../app/components/IntegrationFields.jsx';
import { jobsName, limitVerb, shortMoney } from '../../app/components/words.js';

const RECOMMENDED = 1;

export function StepRules({ form, set, data }) {
  const pickLevel = (key, id) => set({ starting_levels: { ...form.starting_levels, [key]: id } });
  return (
    <>
      <h1 className="ob-title">Your rules</h1>
      <p className="ob-sub">
        Each job type earns freedom on its own, from double-checked results — not from a fixed count.
        The more a mistake would cost you, the more proof the agent needs. One problem and it is paused until you check.
      </p>

      <section className="ob-section">
        <h2>How freedom is earned</h2>
        <TrustFields values={form} onChange={set} />
      </section>

      {data.task_classes.map((tc) => {
        const level = form.starting_levels[tc.key] ?? RECOMMENDED;
        const field = CEILING_FIELD[tc.key];
        const limit = shortMoney(field ? form[field] : tc.ceiling);
        return (
          <section key={tc.key} className="ob-section">
            <h2>{jobsName(data, tc.key)}: where to start</h2>
            <div className="pl-choices" role="radiogroup" aria-label={`${jobsName(data, tc.key)}: starting point`}>
              {[0, 1].map((id) => {
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
            <p className="pl-help pl-small">Working alone is earned, never set: the agent gets there once its double-checked track record proves it.</p>
            {field && (
              <label className="field ob-narrow">
                <span>Most the agent may ever {limitVerb(tc.key)} on its own ($)</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  step="5"
                  value={form[field]}
                  onChange={(e) => set({ [field]: Math.max(0, Number(e.target.value) || 0) })}
                />
                <small>Anything bigger always waits for your OK, however good the track record.</small>
              </label>
            )}
          </section>
        );
      })}
    </>
  );
}
