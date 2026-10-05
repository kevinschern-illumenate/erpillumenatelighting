import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import './index.css';

export function mount(elementId, { referenceUrl, csrfToken }) {
  // Created once per mount, so Workspace rerenders keep the same loader identity.
  const get = url => fetch(url, {
    credentials: 'same-origin', headers: { Accept: 'application/json' },
  }).then(response => {
    if (response.status === 401 || response.status === 403) {
      throw new Error('Your ERPNext session has expired or you lack access. Reload the page to log in again.');
    }
    if (!response.ok) throw new Error(`ERPNext returned ${response.status}`);
    return response.json();
  }).then(body => body.message);
  const loadReference = ({ refresh = false } = {}) => get(referenceUrl + (refresh ? '?refresh=1' : ''));
  const fetchRecord = (doctype, name) => get('/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.record?'
    + new URLSearchParams({ doctype, name }));
  ReactDOM.createRoot(document.getElementById(elementId)).render(
    <React.StrictMode><Workspace loadReference={loadReference} fetchRecord={fetchRecord} mode="erp" csrfToken={csrfToken} /></React.StrictMode>
  );
}
