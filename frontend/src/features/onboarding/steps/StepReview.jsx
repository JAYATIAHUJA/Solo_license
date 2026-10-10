import { LEVELS, money } from '../../../lib/format.js';

export function StepReview({ form }) {
  const provider = { deterministic: 'Built-in parser', anthropic: `Anthropic · ${form.anthropic_model}`, openai: `OpenAI · ${form.openai_model}` }[form.llm_provider];
  const orders = (form.load_sample_orders ? 5 : 0) + form.custom_orders.length;
  const rows = [
    ['Workspace', form.business_name],
    ['Model', provider],
    ['Starts at', `${LEVELS[form.starting_level].code} — ${LEVELS[form.starting_level].name}`],
    ['Promotion', `${form.promotion_clean_runs} clean runs per rung`],
    ['L2 ceiling', money(form.l2_auto_refund_ceiling)],
    ['Orders', `${orders} order${orders === 1 ? '' : 's'}`],
  ];
  return (
    <>
      <h1 className="ob-title serif">Ready to <em className="italic">earn.</em></h1>
      <dl className="ob-review">
        {rows.map(([k, v]) => (
          <div key={k}><dt className="mono">{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
      <p className="ob-sub hand ob-hint">Next: paste a customer message into the Agent desk and watch it work.</p>
    </>
  );
}
