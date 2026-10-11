import { levelCopy } from '../../../lib/copy.js';
import { savedHint, providerLabel } from '../../app/components/ModelFields.jsx';
import { CEILING_FIELD } from '../../app/components/IntegrationFields.jsx';
import { jobsName, shortMoney } from '../../app/components/words.js';

const filled = (form, settings, field) => Boolean(String(form[field] || '').trim() || savedHint(settings, field));

/** Step indexes in Onboarding.jsx's STEPS order. */
const STEP = { workspace: 0, model: 1, rules: 2, signals: 3, data: 4 };

export function StepReview({ form, data, goTo }) {
  const { settings, providers, task_classes: taskClasses } = data;
  const provider = providers.find((p) => p.key === form.llm_provider);
  const existing = (data.orders || []).length;
  const orderParts = [];
  if (existing) orderParts.push(`${existing} already here`);
  else if (form.load_sample_orders) orderParts.push('Sample orders');
  if (form.orders.length) orderParts.push(`${form.orders.length} of your own`);
  const runs = Number(form.promotion_clean_runs) || 1;

  const rows = [
    ['Business', form.business_name, STEP.workspace],
    ['AI model', provider ? providerLabel(provider) : form.llm_provider, STEP.model],
    ...taskClasses.map((tc) => {
      const field = CEILING_FIELD[tc.key];
      const limit = shortMoney(field ? form[field] : tc.ceiling);
      return [jobsName(data, tc.key), `Starts at “${levelCopy(form.starting_levels[tc.key] ?? 1, limit).short}” · on its own up to ${limit}`, STEP.rules];
    }),
    ['More freedom after', `${runs} correct job${runs === 1 ? '' : 's'} in a row`, STEP.rules],
    ['Activity recording', filled(form, settings, 'neatlogs_api_key') ? 'On (neatlogs)' : 'Off — kept in the app only', STEP.signals],
    ['Pause alerts', filled(form, settings, 'alert_webhook_url') ? 'On' : 'Off', STEP.signals],
    ['Orders', orderParts.join(' + ') || 'None', STEP.data],
  ];

  return (
    <>
      <h1 className="ob-title">Ready to go</h1>
      <p className="ob-sub">Check the details below. Next, you'll give the agent its first job.</p>
      <dl className="ob-review">
        {rows.map(([k, v, stepIndex]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => goTo(stepIndex)} aria-label={`Change ${k}`}>Change</button>
          </div>
        ))}
      </dl>
    </>
  );
}
