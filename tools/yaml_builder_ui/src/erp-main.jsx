import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import { createErpApi } from './erp-api.js';
import './index.css';

export function mount(elementId, { csrfToken }) {
  const api = createErpApi({ csrfToken });
  ReactDOM.createRoot(document.getElementById(elementId)).render(
    <React.StrictMode><Workspace api={api} mode="erp" /></React.StrictMode>
  );
}
