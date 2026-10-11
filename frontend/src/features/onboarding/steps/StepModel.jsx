import { ModelFields } from '../../app/components/ModelFields.jsx';

export function StepModel({ form, set, data }) {
  return (
    <>
      <h1 className="ob-title">Choose an AI model</h1>
      <p className="ob-sub">
        It reads customer messages and writes a short plan. It never decides what the agent is allowed to do — you do.
        No key? Pick “No AI model (simple rules)” and add one later.
      </p>
      <ModelFields providers={data.providers} values={form} onChange={set} settings={data.settings} />
    </>
  );
}
