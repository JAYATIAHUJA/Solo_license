import { Link } from 'react-router-dom';
import { Logo } from '../../../components/brand/Logo.jsx';

export function Footer({ onReplayIntro }) {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-top">
        <Link to="/" className="lp-logo"><Logo /> Solo License<sup>®</sup></Link>
        <nav>
          <a href="/#terminal">In your agent</a>
          <a href="/#journey">How it earns</a>
          <a href="/#agent">The loop</a>
          <a href="/#crash">The crash</a>
          <a href="/#tour">Product</a>
          <Link to="/install">Install</Link>
          {onReplayIntro && <button className="lp-footer-link" onClick={onReplayIntro}>Replay intro</button>}
        </nav>
        <nav>
          <Link to="/app">Dashboard</Link>
          <Link to="/app/settings">Settings</Link>
        </nav>
      </div>
      <p className="lp-footer-word serif" aria-hidden="true">Solo License</p>
      <div className="lp-footer-bottom mono">
        <span>Built for the neatHack agent hackathon</span>
        <span>Earned autonomy for coding agents</span>
      </div>
    </footer>
  );
}
