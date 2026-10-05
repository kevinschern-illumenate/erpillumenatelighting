import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import './index.css';

export function mount(elementId, { referenceUrl, csrfToken }) {
  // Created once per mount, so Workspace rerenders keep the same loader identity.
  const loadReference = () => fetch(referenceUrl, {
    credentials: 'same-origin', headers: { Accept: 'application/json' },
  }).then(response => {
    if (response.status === 401 || response.status === 403) {
      throw new Error('Your ERPNext session has expired or you lack access. Reload the page to log in again.');
    }
    if (!response.ok) throw new Error(`ERPNext returned ${response.status}`);
    return response.json();
  }).then(body => body.message);
  ReactDOM.createRoot(document.getElementById(elementId)).render(
    <React.StrictMode><Workspace loadReference={loadReference} mode="erp" csrfToken={csrfToken} /></React.StrictMode>
  );
}
