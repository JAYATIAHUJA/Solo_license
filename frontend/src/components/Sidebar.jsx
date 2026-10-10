import React from 'react';

export function Sidebar({ activeSection, onSectionChange, busy, onReseed, theme, onThemeChange }) {
  return <aside className="side-rail">
    <div className="app-brand"><span className="brand-glyph"><i /><i /></span><strong>Solo</strong></div>
    <nav className="rail-nav">
      <button className={activeSection === 'control' ? 'selected' : ''} onClick={() => onSectionChange('control')}><span>◉</span> Control room</button>
      <button className={activeSection === 'evidence' ? 'selected' : ''} onClick={() => onSectionChange('evidence')}><span>◎</span> Evidence</button>
      <button className={activeSection === 'runs' ? 'selected' : ''} onClick={() => onSectionChange('runs')}><span>⌇</span> Recent runs</button>
    </nav>
    <div className="rail-section"><span>My workspace</span></div>
    <div className="workspace-name"><i /> Refund class</div>
    <p className="rail-note">Earned autonomy for refunds. Evidence decides the level.</p>
    <div className="rail-bottom"><button onClick={onReseed} disabled={busy}>↻ Reseed demo</button><button onClick={onThemeChange}>{theme === 'light' ? '◐ Dark view' : '◑ Light view'}</button></div>
  </aside>;
}
