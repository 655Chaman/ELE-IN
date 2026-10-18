import './catch_errors';
import { initFrontendTelemetry } from './lib/telemetry';

import { ErrorBoundary } from './ErrorBoundary';
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { registerNotificationServiceWorker } from './lib/desktopNotification';

// Initialize production observability & error tracking
initFrontendTelemetry();

// Register background Service Worker for persistent OS desktop notifications
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    registerNotificationServiceWorker();
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary><App /></ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)
