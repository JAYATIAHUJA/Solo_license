import { AnimatePresence, motion } from 'motion/react';
import { moneyWhole, pct } from '../../../../lib/format.js';
import { HandIcon } from '../../../../components/icons/HandIcon.jsx';
import { useCountUp } from './useCountUp.js';

const EASE = [0.22, 1, 0.36, 1];

/** Live unit economics: what earned autonomy saves in human supervision each
 *  month versus keeping every class at L0, minus the measured cost of
 *  incidents. Demote a class and the headline visibly drops. */
export function SavingsMeter({ economics, classes }) {
  const econ = economics || { classes: [], net_saved_month: 0, supervision_saved_month: 0, risk_cost_month: 0, assumptions: {} };
  const { shown, delta } = useCountUp(econ.net_saved_month);
  const a = econ.assumptions || {};
  const minutes = a.minutes_per_action_by_level || {};
  const labelFor = (key) => classes.find((c) => c.key === key)?.meta.label || key;

  return (
    <section className={`mc-save ${delta.dir === 'down' ? 'is-drop' : ''}`} aria-label="Live unit economics">
      <header className="mc-save-head">
        <span className="app-kicker">Live unit economics · cfo model</span>
        <span className="mono muted">per month</span>
      </header>

      <div className="mc-save-hero">
        <div>
          <span className="app-kicker">Net saved vs. all-L0</span>
          <b className="serif mc-save-big" aria-live="polite">{moneyWhole(shown)}</b>
        </div>
        <AnimatePresence>
          {delta.dir && (
            <motion.span
              key={delta.at}
              className={`mc-save-delta mono ${delta.dir === 'down' ? 'is-alert' : ''}`}
              initial={{ opacity: 0, y: delta.dir === 'down' ? -10 : 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              {delta.dir === 'down' ? '▼' : '▲'} {moneyWhole(Math.abs(delta.by))}
              <small>{delta.dir === 'down' ? 'trust revoked' : 'trust earned'}</small>
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <dl className="mc-save-split">
        <div><dt className="app-kicker">Supervision saved</dt><dd>{moneyWhole(econ.supervision_saved_month)}</dd></div>
        <div className={econ.risk_cost_month > 0 ? 'is-alert' : ''}><dt className="app-kicker">Measured risk cost</dt><dd>−{moneyWhole(econ.risk_cost_month)}</dd></div>
        <div><dt className="app-kicker">Net</dt><dd><b>{moneyWhole(econ.net_saved_month)}</b></dd></div>
      </dl>

      <ul className="mc-save-bars">
        {econ.classes.map((c) => {
          const base = Math.max(1, c.supervision_cost_l0_month || 1);
          const risk = Math.min(c.risk_cost_month || 0, c.supervision_saved_month || 0);
          const kept = Math.max(0, (c.supervision_saved_month || 0) - risk);
          const w = (n) => `${Math.max(0, Math.min(100, (n / base) * 100))}%`;
          return (
            <li key={c.task_class}>
              <div className="mc-save-row">
                <span><b>{labelFor(c.task_class)}</b> <span className="mono muted">L{c.level}</span></span>
                <span className="mono">{moneyWhole(c.net_saved_month)}</span>
              </div>
              <div className="mc-bar" role="img" aria-label={`${labelFor(c.task_class)}: saves ${moneyWhole(c.supervision_saved_month)} of ${moneyWhole(base)} supervision`}>
                <motion.i className="mc-bar-saved" initial={false} animate={{ width: w(kept) }} transition={{ duration: 0.9, ease: EASE }} />
                <motion.i className="mc-bar-risk" initial={false} animate={{ width: w(risk) }} transition={{ duration: 0.9, ease: EASE }} />
                <motion.i className="mc-bar-cost" initial={false} animate={{ width: w(c.supervision_cost_month) }} transition={{ duration: 0.9, ease: EASE }} />
              </div>
              <div className="mc-save-meta app-small muted">
                <span>{moneyWhole(c.supervision_cost_month)} still supervised</span>
                <span>incident rate {pct(c.incident_rate)} ({c.incidents}/{c.runs})</span>
                <span>${Number(c.cost_per_action || 0).toFixed(2)}/action</span>
              </div>
              {c.blind_autonomy_risk_month > 0 && (
                <p className="mc-save-blind app-small">
                  <HandIcon name="warn" size={12} /> Same class at L3 with no verifier: <b>−{moneyWhole(c.blind_autonomy_risk_month)}/mo</b> in incidents.
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="mc-save-legend app-small">
        <span><i className="pat-solid" /> saved</span>
        <span><i className="mc-swatch-risk" /> risk cost</span>
        <span><i className="pat-dots" /> still supervised</span>
      </div>
      <p className="mc-save-note app-small muted">
        Assumes {moneyWhole(a.hourly_cost)}/h ops time · {Number(a.monthly_volume_per_class || 0).toLocaleString('en-US')} actions per class/mo · {moneyWhole(a.incident_cost)} per incident ·
        minutes per action {['0', '1', '2', '3'].map((l) => `L${l} ${minutes[l] ?? '—'}`).join(' / ')}.
        {' '}Recomputes from real runs; incident rate is measured.
      </p>
    </section>
  );
}
