import React from 'react';
import ReactDOM from 'react-dom/client';
import Workspace from './Workspace.jsx';
import './index.css';

const loadSnapshot = () => import('./erp-reference.json').then(module => module.default);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Workspace loadReference={loadSnapshot} />
  </React.StrictMode>
);
