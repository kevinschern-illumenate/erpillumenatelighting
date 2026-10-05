import { useEffect, useState } from 'react';
import { deskUrl } from './erp-api.js';
import { ApiError, StatusPill } from './ImportResults.jsx';

export default function ImportHistory({ api, revision }) {
  const [open, setOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState({ loading: true, rows: [], error: null });
  useEffect(() => {
    if (!open) return;
    let current = true;
    setState(previous => ({ ...previous, loading: true, error: null }));
    api.history().then(rows => {
      if (current) setState({ loading: false, rows, error: null });
    }).catch(error => {
      if (current) setState({ loading: false, rows: [], error });
    });
    return () => { current = false; };
  }, [api, open, revision, retry]);
  return <details className="catalog-history" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Recent checks and imports</summary>
    {state.loading ? <p role="status">Loading recent runs…</p> : state.error ? <>
      <ApiError error={state.error} /><button onClick={() => setRetry(value => value + 1)}>Retry history</button>
    </> : <>
      {!state.rows.length && <p>No recent checks or imports.</p>}
      <ol>{state.rows.map(row => <li key={row.name}>
        <a href={deskUrl('ilL-Catalog-Import', row.name)} target="_blank" rel="noopener">{row.mode} · <time dateTime={row.creation.replace(' ', 'T')}>{row.creation.slice(0, 19)}</time></a>
        <div><StatusPill status={row.status} /> {row.series_name}</div>
        <small>{row.record_count} records · {row.created_count} created · {row.error_count} errors · {row.skipped_count} skipped · {row.warning_count} warnings</small>
      </li>)}</ol>
    </>}
  </details>;
}
