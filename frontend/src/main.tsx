import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { getPosthog } from './utils/posthog';

if (import.meta.env.VITE_POSTHOG_KEY) {
  getPosthog().catch((err) => {
    console.warn('PostHog failed to initialise:', err);
  });
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
