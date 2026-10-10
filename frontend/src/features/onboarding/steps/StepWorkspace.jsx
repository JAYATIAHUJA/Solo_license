export function StepWorkspace({ form, set }) {
  return (
    <>
      <h1 className="ob-title">What's your business called?</h1>
      <p className="ob-sub">We'll use it in the app and in any alert messages.</p>
      <label className="field">
        <span>Business name</span>
        <input
          className="input ob-big-input"
          autoFocus
          placeholder="e.g. Northwind Gifts"
          value={form.business_name}
          onChange={(e) => set({ business_name: e.target.value })}
          maxLength={60}
        />
        <small>At least two letters.</small>
      </label>
    </>
  );
}
