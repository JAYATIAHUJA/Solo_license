import { AlertFields, InboxFields, NeatlogsFields } from '../../app/components/IntegrationFields.jsx';

export function StepSignals({ form, set, data }) {
  return (
    <>
      <h1 className="ob-title">Connections</h1>
      <p className="ob-sub">All optional - skip this step if you like. Everything the agent does is still recorded in the app.</p>
      <section className="ob-section">
        <h2>Customer messages</h2>
        <p className="ob-section-sub">Paste messages into the app any time. To have them arrive by themselves, send them from your helpdesk or email to this address.</p>
        <InboxFields />
      </section>
      <section className="ob-section">
        <h2>Activity recording (neatlogs)</h2>
        <p className="ob-section-sub">Sends a step-by-step record of every agent action to neatlogs so you or an auditor can replay it.</p>
        <NeatlogsFields values={form} onChange={set} settings={data.settings} />
      </section>
      <section className="ob-section">
        <h2>Get notified when the agent is paused</h2>
        <p className="ob-section-sub">Paste a Slack or Discord webhook link; we post a message when a job type is paused or resumed.</p>
        <AlertFields values={form} onChange={set} settings={data.settings} />
      </section>
    </>
  );
}
