export function StepWorkspace({ form, set }) {
  return (
    <>
      <h1 className="ob-title serif">What should we <em className="italic">call</em> this workspace?</h1>
      <label className="field">
        <span>Business or team name</span>
        <input
          className="input ob-big-input"
          autoFocus
          placeholder="e.g. Northwind Support"
          value={form.business_name}
          onChange={(e) => set({ business_name: e.target.value })}
          maxLength={60}
        />
        <small>At least two characters.</small>
      </label>
    </>
  );
}
