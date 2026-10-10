import { AlertFields, NeatlogsFields } from '../../app/components/IntegrationFields.jsx';

export function StepSignals({ form, set, data }) {
  return (
    <>
      <h1 className="ob-title serif">Who <em className="italic">watches</em> the agent?</h1>
      <p className="ob-sub">
        Both are optional. Leave them blank to skip: every run is still recorded locally and shown in the evidence packet.
      </p>
      <section className="ob-section">
        <h2 className="ob-section-title">Observability <span className="mono muted">neatlogs</span></h2>
        <p className="ob-section-sub">Streams each run to neatlogs as a workflow trace: intake, plan, tool calls, verification.</p>
        <NeatlogsFields values={form} onChange={set} settings={data.settings} />
      </section>
      <section className="ob-section">
        <h2 className="ob-section-title">Alerts <span className="mono muted">Slack · Discord</span></h2>
        <p className="ob-section-sub">Paste an incoming-webhook URL so your team hears about promotions and demotions without watching a dashboard.</p>
        <AlertFields values={form} onChange={set} settings={data.settings} />
      </section>
    </>
  );
}
