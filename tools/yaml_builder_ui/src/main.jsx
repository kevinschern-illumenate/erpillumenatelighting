import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import CatalogApp from './CatalogApp.jsx';
import './index.css';

function Workspace() {
  const [legacy, setLegacy] = React.useState(false);
  return <>
    <div hidden={legacy}><CatalogApp onLegacy={() => setLegacy(true)} /></div>
    {legacy && <button style={{ margin: 16, padding: 10 }} onClick={() => setLegacy(false)}>← Full product catalog editor</button>}
    <div hidden={!legacy}><App /></div>
  </>;
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Workspace />
  </React.StrictMode>
);
