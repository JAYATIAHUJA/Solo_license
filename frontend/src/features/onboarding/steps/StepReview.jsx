import { LEVELS, money } from '../../../lib/format.js';
import { savedHint } from '../../app/components/ModelFields.jsx';
import { CEILING_FIELD } from '../../app/components/IntegrationFields.jsx';

const filled = (form, settings, field) => Boolean(String(form[field] || '').trim() || savedHint(settings, field));

export function StepReview({ form, data, goTo }) {
  const { settings, providers, task_classes: taskClasses } = data;
  const provider = providers.find((p) => p.key === form.llm_provider);
  const model = provider?.model_field ? form[provider.model_field] || provider.default_model : '';
  const existing = (data.orders || []).length;
  const orderParts = [];
  if (existing) orderParts.push(`${existing} existing`);
  else if (form.load_sample_orders) orderParts.push('Sample set');
  if (form.orders.length) orderParts.push(`${form.orders.length} added by you`);

  const rows = [
    ['Workspace', form.business_name, 0],
    ['Model', provider ? `${provider.label}${model ? ` · ${model}` : ''}` : form.llm_provider, 1],
    ['neatlogs', filled(form, settings, 'neatlogs_api_key') ? `Traces on · ${form.neatlogs_project || 'default project'}` : 'Skipped — local traces only', 2],
    ['Alerts', filled(form, settings, 'alert_webhook_url') ? 'Webhook set' : 'Skipped', 2],
    ...taskClasses.map((tc) => {
      const lv = LEVELS[form.starting_levels[tc.key] ?? 0];
      const field = CEILING_FIELD[tc.key];
      return [tc.label, `Starts ${lv.code} — ${lv.name}${field ? ` · L2 ceiling ${money(form[field])}` : ''}`, 3];
    }),
    ['Promotion', `${form.promotion_clean_runs} clean run${Number(form.promotion_clean_runs) === 1 ? '' : 's'} per rung`, 3],
    ['Orders', orderParts.join(' + ') || 'None', 4],
  ];

  return (
    <>
      <h1 className="ob-title serif">Ready to <em className="italic">earn.</em></h1>
      <dl className="ob-review">
        {rows.map(([k, v, stepIndex]) => (
          <div key={k}>
            <dt className="mono">{k}</dt>
            <dd>{v}</dd>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => goTo(stepIndex)} aria-label={`Edit ${k}`}>Edit</button>
          </div>
        ))}
      </dl>
      <p className="ob-sub hand ob-hint">Next: paste a customer message into the Agent desk and watch it work.</p>
    </>
  );
}
