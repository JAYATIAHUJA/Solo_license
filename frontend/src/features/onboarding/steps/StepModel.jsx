import { ModelFields } from '../../app/components/ModelFields.jsx';

export function StepModel({ form, set, data }) {
  return (
    <>
      <h1 className="ob-title serif">Give the agent a <em className="italic">brain.</em></h1>
      <p className="ob-sub">
        The model turns messy customer messages into structured requests and explains its plan.
        Permissions still come from the license, never from the model. Keys are encrypted at rest and never shown back in full.
      </p>
      <ModelFields providers={data.providers} values={form} onChange={set} settings={data.settings} />
    </>
  );
}
