import { createRoot } from 'react-dom/client';
import { LandingPage } from './LandingPage';
import App from './main.jsx';

const root = createRoot(document.getElementById('root') as HTMLElement);

root.render(window.location.pathname === '/landing' ? <LandingPage /> : <App />);
