import { createRoot } from 'react-dom/client';
import { LandingPage } from './LandingPage';
import App from './main.jsx';

createRoot(document.getElementById('root')).render(window.location.pathname === '/landing' ? <LandingPage /> : <App />);
