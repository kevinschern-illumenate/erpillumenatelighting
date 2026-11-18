import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import { createErpApi } from './erp-api.js';
import './index.css';

/** `embedded` is set when the page is opened as /catalog-builder?embed=1 (the Command Center's Catalog tab). */
export function mount(elementId, { csrfToken, embedded = false }) {
  const api = createErpApi({ csrfToken });
  ReactDOM.createRoot(document.getElementById(elementId)).render(
    <React.StrictMode><Workspace api={api} mode="erp" embedded={Boolean(embedded)} /></React.StrictMode>
  );
}
