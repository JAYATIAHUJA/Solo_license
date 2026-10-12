/** Only the phone menu button lives here; on desktop the sidebar is enough. */
export function Topbar({ onMenu }) {
  return (
    <header className="app-top">
      <button className="app-menu btn btn-ghost btn-sm" onClick={onMenu} aria-label="Open menu">Menu</button>
    </header>
  );
}
