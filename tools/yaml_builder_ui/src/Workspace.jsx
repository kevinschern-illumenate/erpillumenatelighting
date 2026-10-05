import React from 'react';
import App from './App.jsx';
import CatalogApp from './CatalogApp.jsx';

export default function Workspace({ loadReference, fetchRecord, mode = 'vercel', csrfToken }) {
  const [legacy, setLegacy] = React.useState(false);
  return <>
    <div hidden={legacy}><CatalogApp onLegacy={() => setLegacy(true)} loadReference={loadReference} fetchRecord={fetchRecord} mode={mode} csrfToken={csrfToken} /></div>
    {legacy && <button style={{ margin: 16, padding: 10 }} onClick={() => setLegacy(false)}>← Full product catalog editor</button>}
    <div hidden={!legacy}><App /></div>
  </>;
}
