import { useState } from 'react';
import { deskUrl, LOGIN_URL } from './erp-api.js';

export function ApiError({ error }) {
  return <div className="catalog-api-error" role="alert">{error.message || String(error)}
    {error.sessionExpired && <> <a href={LOGIN_URL}>Log in to ERPNext</a></>}
  </div>;
}

export function StatusPill({ status }) {
  const tone = { Passed: 'success', Imported: 'success', checked: 'success', created: 'success', Failed: 'error', 'Rolled Back': 'error', Error: 'error', error: 'error', Refused: 'warning', skipped: 'warning' }[status] || 'neutral';
  return <span className={`catalog-status catalog-tone-${tone}`}>{status}</span>;
}

export default function ImportResults({ response, onSelect }) {
  const [filter, setFilter] = useState('All');
  const { status, summary, errors = [], results = [], log } = response;
  const problems = summary.errors + summary.skipped;
  const banner = {
    Passed: `All ${summary.checked} records passed. Nothing was saved — Import to create them.`,
    Failed: `${problems} problems. Nothing was saved.`,
    'Rolled Back': `Import stopped: ${problems} problems. Everything was rolled back — nothing was saved.`,
    Imported: `Created ${summary.created} records in ERPNext.`,
    Refused: errors[0] || 'ERPNext refused this request. Run Check again.',
    Error: `ERPNext could not complete this run.${log ? ` See audit log ${log}.` : ' No audit log is available.'}`,
  }[status] || status;
  const shown = results.filter(row => filter === 'All' || (filter === 'Errors' && row.status === 'error')
    || (filter === 'Skipped' && row.status === 'skipped') || (filter === 'Warnings' && row.warnings?.length))
    .sort((a, b) => a.batch - b.batch);
  return <section className="catalog-results" aria-label="ERPNext results">
    <div className={`catalog-result-banner catalog-tone-${['Passed', 'Imported'].includes(status) ? 'success' : status === 'Refused' ? 'warning' : 'error'}`} role="status">
      <StatusPill status={status} /> <strong>{banner}</strong>
    </div>
    {errors.length > 0 && <ul className="catalog-run-errors">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}
    <p>{summary.records} records · {summary.checked} checked · {summary.created} created · {summary.errors} errors · {summary.skipped} skipped · {summary.warnings} warnings · {(summary.duration_ms / 1000).toFixed(2)} seconds
      {log && <> · <a href={deskUrl('ilL-Catalog-Import', log)} target="_blank" rel="noopener">Open audit log</a></>}</p>
    {results.length > 0 && <>
      <div className="catalog-result-filters" role="group" aria-label="Filter results">
        {['All', 'Errors', 'Skipped', 'Warnings'].map(value => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value}</button>)}
      </div>
      <div className="catalog-result-table" tabIndex={0} role="region" aria-label="Record results">
        <table><thead><tr>{['Batch', 'DocType', 'Record', 'Status', 'Message / warnings'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{shown.map((row, index) => <tr key={index}>
            <td>{row.batch}</td><td>{row.doctype.replace(/^ilL-/, '')}</td>
            <td>{status === 'Imported' && row.status === 'created' && row.name
              ? <a href={deskUrl(row.doctype, row.name)} target="_blank" rel="noopener">{row.name}</a>
              : ['error', 'skipped'].includes(row.status)
                ? <button className="catalog-result-select" onClick={() => onSelect(row.doctype, row.catalog_name)} aria-label={`Edit ${row.catalog_name}`}>{row.catalog_name}</button>
                : row.catalog_name || row.name}</td>
            <td><StatusPill status={row.status} /></td><td>{row.message}
              {row.warnings?.length > 0 && <ul>{row.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}</td>
          </tr>)}</tbody>
        </table>
        {!shown.length && <p>No records match this filter.</p>}
      </div>
    </>}
  </section>;
}
