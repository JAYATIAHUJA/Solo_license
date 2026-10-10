import { ModelFields } from '../../app/components/ModelFields.jsx';

export function StepModel({ form, set }) {
  return (
    <>
      <h1 className="ob-title serif">Give the agent a <em className="italic">brain.</em></h1>
      <p className="ob-sub">The model turns messy customer messages into structured refund requests and explains its plan. Permissions still come from the license.</p>
      <ModelFields values={form} onChange={set} />
    </>
  );
}
