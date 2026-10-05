import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { parse, stringify } from 'yaml';
import schema from './catalog-schema.json';
import examples from './catalog-examples.json';
import ImportResults, { ApiError } from './ImportResults.jsx';
import ImportHistory from './ImportHistory.jsx';
import ConfirmDialog from './ConfirmDialog.jsx';
import { recordCounts } from './erp-api.js';
import {
  blankRecord, emptyCatalog, recordName, catalogIssues, parseCatalog, unresolvedLinks, makeItemRecords,
  referenceSummary, withReferenceLinks, unconfirmedLinks, isComplete,
  catalogAddition, mergeAdditions, excludeCatalog, referenceOrigin, catalogKey,
} from './catalog-model.js';
import { issueIndex } from './grid-model.js';
import { RecordFields } from './RecordFields.jsx';
import { RecordGrid, GridData } from './RecordGrid.jsx';
import './catalog.css';

export { RecordFields };

const STORAGE = 'illumenate-product-catalog-v2';
// Catalogs downloaded with "Add to ERPNext reference", until the checked-in reference includes them.
const PENDING = 'illumenate-erp-reference-pending';
const VIEW = 'illumenate-catalog-view';
const parentTypes = Object.keys(schema.doctypes).filter(name => !schema.doctypes[name].istable);
const shortName = name => name.replace(/^ilL-/, '');
// The server timestamp is already in the site's timezone; keep that clock time.
const loadedTime = timestamp => timestamp?.slice(11, 16) || 'unknown';
const recordPrefix = doctype => `catalog-record-${encodeURIComponent(doctype)}-`;
const recordId = (doctype, index) => `${recordPrefix(doctype)}${index}`;

function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE));
    if (saved && schema.products[saved.active]) {
      for (const draft of Object.values(saved.drafts)) parseCatalog(JSON.stringify(draft), JSON.parse, schema);
      return saved;
    }
  } catch { /* An unreadable draft never prevents opening the editor. */ }
  return { active: 'fixture', drafts: { fixture: emptyCatalog('fixture') } };
}

/** Copy a record for editing as a new one; its naming field is cleared. */
function asNewRecord(doctype, row) {
  const rule = schema.doctypes[doctype].autoname || '';
  const copy = structuredClone(row);
  if (rule.startsWith('field:')) copy[rule.slice(6)] = '';
  else if (!rule.startsWith('format:')) copy.name = '';
  return copy;
}

function restoreView() {
  try { return { table: true, wide: false, ...JSON.parse(localStorage.getItem(VIEW)) }; } catch { return { table: true, wide: false }; }
}

function restorePending() {
  try {
    const saved = JSON.parse(localStorage.getItem(PENDING));
    return Array.isArray(saved) ? saved.filter(row => row && typeof row.catalog === 'string' && row.records) : [];
  } catch { return []; }
}

function download(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/yaml;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Existing ERPNext records of one DocType, from a snapshot or the live site. */
function ReferencePanel({ doctype, reference, onCopy, copying }) {
  const [query, setQuery] = useState('');
  const entry = reference?.doctypes?.[doctype];
  if (!entry) return null;
  const names = Object.keys(entry.records);
  const needle = query.trim().toLowerCase();
  const matches = names.filter(name => !needle || `${name} ${JSON.stringify(entry.records[name])}`.toLowerCase().includes(needle));
  const partial = !isComplete(entry);
  return <details className="catalog-reference">
    <summary>{names.length} existing in ERPNext <span>{entry.source === 'live' ? `Live from ERPNext · loaded ${loadedTime(entry.exported_on)}` : `export of ${entry.exported_on || reference.exported_on}`}{partial ? ' · only records that exported records link to' : ''}</span></summary>
    <p>Link to these from your new records instead of re-creating them; linked names count as existing ERPNext records.
      {partial ? '' : ' Copy one to start a new record from its values.'}</p>
    <input aria-label={`Search existing ${shortName(doctype)} records`} placeholder="Search existing records…" value={query} onChange={e => setQuery(e.target.value)} />
    <div className="catalog-reference-list">{matches.slice(0, 100).map(name => <div className="catalog-link" key={name}>
      <strong>{name}</strong><small>{referenceSummary(doctype, entry.records[name], schema)}</small>
      {referenceOrigin(reference, doctype, name) && <small className="catalog-origin">
        {referenceOrigin(reference, doctype, name).pending ? 'Pending import · ' : ''}added from catalog {referenceOrigin(reference, doctype, name).catalog}</small>}
      {!partial && <button disabled={Boolean(copying)} onClick={() => onCopy(name, entry.records[name])}>{copying === name ? 'Copying…' : 'Copy as new record'}</button>}
    </div>)}</div>
    {matches.length > 100 && <p>Showing 100 of {matches.length}. Refine the search to see more.</p>}
  </details>;
}

export default function CatalogApp({ onLegacy, loadReference, api, mode = 'vercel' }) {
  const [workspace, setWorkspace] = useState(restore);
  const [selected, setSelected] = useState('Item');
  const [search, setSearch] = useState('');
  const [fieldSearch, setFieldSearch] = useState('');
  const [message, setMessage] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  // Snapshots of the active product's draft; catalogs are never mutated, so snapshots share unchanged records.
  const [history, setHistory] = useState({ product: null, past: [], future: [] });
  const [view, setView] = useState(restoreView);
  const [exported, setExported] = useState(null);
  const [pending, setPending] = useState(restorePending);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [referenceError, setReferenceError] = useState('');
  const [copying, setCopying] = useState(null);
  const [opening, setOpening] = useState(false);
  const [run, setRun] = useState({ phase: 'idle' });
  const currentRun = useRef(run);
  currentRun.current = run;
  const [historyRevision, setHistoryRevision] = useState(0);
  const [selection, setSelection] = useState(null);
  const runBusy = useRef(false);
  const busy = ['checking', 'importing'].includes(run.phase);
  const fileInput = useRef(null);
  const referenceRequest = useRef(0);
  const loadExisting = useCallback(async (options) => {
    const request = ++referenceRequest.current;
    setReferenceLoading(true);
    setReferenceError('');
    try {
      const data = api ? await api.reference(Boolean(options?.refresh)) : await loadReference(options);
      if (request !== referenceRequest.current) return;
      if (data?.unavailable) throw new Error('Existing ERPNext records are unavailable. Declare existing records manually.');
      setExported(data);
    } catch (error) {
      if (request === referenceRequest.current) setReferenceError(error);
    } finally {
      if (request === referenceRequest.current) setReferenceLoading(false);
    }
  }, [loadReference, api]);
  useEffect(() => {
    loadExisting();
    return () => { referenceRequest.current += 1; };
  }, [loadExisting]);
  const catalog = useMemo(() => workspace.drafts[workspace.active] || emptyCatalog(workspace.active), [workspace]);
  const currentDraft = useRef(null);
  currentDraft.current = { catalog, active: workspace.active, selected };
  const product = schema.products[workspace.active];
  const writeCatalog = next => setWorkspace(previous => ({ ...previous, drafts: { ...previous.drafts, [previous.active]: next } }));
  const timeline = history.product === workspace.active ? history : { past: [], future: [] };
  /** Change the draft as one undo step; consecutive changes with the same `key` (typing in one cell) share a step. */
  const setCatalog = (next, change = {}) => {
    const top = timeline.past.at(-1);
    if (!(change.key && top?.key === change.key)) {
      setHistory({ product: workspace.active, past: [...timeline.past, { catalog, label: change.label || 'Edit', key: change.key }].slice(-100), future: [] });
    } else if (timeline.future.length) setHistory({ ...timeline, product: workspace.active, future: [] });
    writeCatalog(next);
  };
  const undo = () => {
    const entry = timeline.past.at(-1);
    if (!entry || busy) return;
    // The step before it is closed, so typing again starts a new step.
    const past = timeline.past.slice(0, -1).map((step, i, steps) => i === steps.length - 1 ? { ...step, key: undefined } : step);
    setHistory({ product: workspace.active, past, future: [...timeline.future, { catalog, label: entry.label }] });
    writeCatalog(entry.catalog);
  };
  const redo = () => {
    const entry = timeline.future.at(-1);
    if (!entry || busy) return;
    setHistory({ product: workspace.active, past: [...timeline.past, { catalog, label: entry.label }], future: timeline.future.slice(0, -1) });
    writeCatalog(entry.catalog);
  };
  const clearHistory = () => setHistory({ product: null, past: [], future: [] });
  const saveView = next => {
    setView(next);
    try { localStorage.setItem(VIEW, JSON.stringify(next)); } catch { /* The view choice is a convenience. */ }
  };
  useEffect(() => {
    try { localStorage.setItem(STORAGE, JSON.stringify(workspace)); }
    catch { setMessage('Browser storage is full or unavailable. Download YAML to save your work.'); }
  }, [workspace]);
  useEffect(() => {
    if (mode === 'erp') return;
    try { localStorage.setItem(PENDING, JSON.stringify(pending)); } catch { /* Pending additions are a convenience. */ }
  }, [pending, mode]);
  const known = useMemo(() => mergeAdditions(exported, mode === 'erp' ? [] : pending, schema), [exported, pending, mode]);
  // This catalog's own earlier additions must not count as existing records while it is edited.
  const reference = useMemo(() => excludeCatalog(known, catalog), [known, catalog]);
  const ownPending = known?.catalog_additions?.filter(row => row.pending) || [];
  const resolved = useMemo(() => withReferenceLinks(catalog, schema, reference), [catalog, reference]);
  const payload = useMemo(() => {
    const next = { ...resolved };
    if (mode === 'erp') delete next.add_to_reference;
    return next;
  }, [resolved, mode]);
  const payloadKey = JSON.stringify(payload);
  const currentPayloadKey = useRef(payloadKey);
  currentPayloadKey.current = payloadKey;
  // Once changed, even undoing an edit requires another Check.
  useEffect(() => {
    if (run.phase === 'checked' && run.payloadKey !== payloadKey && !run.stale) {
      setRun(previous => ({ ...previous, stale: true }));
    }
  }, [payloadKey, run]);
  const canImport = run.phase === 'checked' && run.response?.status === 'Passed' && !run.stale && run.payloadKey === payloadKey;
  // Serializing a large catalog is slow, so it happens only for the preview and downloads.
  const toYaml = () => '# ilLumenate product catalog — validate and generate with tools.fixture_builder\n' + stringify(resolved, { lineWidth: 0 });
  const yaml = useMemo(() => (showPreview ? toYaml() : ''), [resolved, showPreview]); // eslint-disable-line react-hooks/exhaustive-deps
  const issues = useMemo(() => catalogIssues(mode === 'erp' ? { ...catalog, add_to_reference: false } : catalog, schema, reference), [catalog, reference, mode]);
  const missing = useMemo(() => unresolvedLinks(catalog, schema, reference), [catalog, reference]);
  const unconfirmed = useMemo(() => unconfirmedLinks(catalog, reference), [catalog, reference]);
  const cellIssues = useMemo(() => issueIndex(issues, missing, catalog, schema), [issues, missing, catalog]);
  const fromErp = Object.values(resolved.external_links).reduce((sum, names) => sum + names.length, 0)
    - Object.values(catalog.external_links).reduce((sum, names) => sum + names.length, 0);
  const total = Object.values(catalog.records).reduce((sum, rows) => sum + rows.length, 0);
  const orderedTypes = [...new Set(['Item', product.spec, product.template, 'ilL-Webflow-Product', ...Object.keys(catalog.records), ...parentTypes])]
    .filter(name => name.toLowerCase().includes(search.toLowerCase()));
  const rows = catalog.records[selected] || [];
  const filename = `${(catalog.series_name || workspace.active).toLowerCase().replace(/[^a-z0-9]+/g, '-')}-catalog.yaml`;
  const replaceRows = (next, change) => setCatalog({ ...catalog, records: { ...catalog.records, [selected]: next } }, change);
  const executeRun = async (importing, checked = null) => {
    if (runBusy.current) return;
    if (importing && (!canImport || checked.payloadKey !== currentPayloadKey.current || checked !== currentRun.current)) {
      setMessage('Catalog changed since the last check — run Check again');
      return;
    }
    runBusy.current = true;
    const submitted = { payload, payloadKey };
    setRun({ ...submitted, phase: importing ? 'importing' : 'checking' });
    try {
      const response = importing ? await api.importCatalog(checked.payload, checked.response.catalog_hash) : await api.check(payload);
      setRun({ ...submitted, response, phase: response.status === 'Imported' ? 'imported' : importing ? 'idle' : 'checked', stale: submitted.payloadKey !== currentPayloadKey.current });
      // A failed reference refresh must never obscure an already committed import.
      if (response.status === 'Imported') await loadExisting({ refresh: true });
    } catch (error) {
      setRun({ ...submitted, phase: 'error', error, uncertainImport: importing });
    } finally {
      runBusy.current = false;
      setHistoryRevision(value => value + 1);
    }
  };
  const confirmImport = () => {
    if (!canImport || runBusy.current) return;
    const checked = run;
    setConfirm({ title: 'Create these records in ERPNext?', label: 'Import to ERPNext', body: <>
      <ul>{recordCounts(checked.payload).map(({ doctype, count }) => <li key={doctype}>{count} {shortName(doctype)}</li>)}</ul>
      <p>This cannot be undone from the builder.</p>
    </>, run: () => executeRun(true, checked) });
  };
  const selectResult = (doctype, name) => {
    const index = (catalog.records[doctype] || []).findIndex(row => recordName(doctype, row, schema) === name);
    if (index < 0) { setMessage('This record is no longer in the current draft.'); return; }
    setSelected(doctype); setFieldSearch(''); setSelection({ doctype, index });
  };
  useEffect(() => {
    if (!selection) return;
    const element = document.getElementById(recordId(selection.doctype, selection.index));
    element?.focus({ preventScroll: true });
    element?.scrollIntoView({ block: 'center' });
  }, [selection]);
  const copyRecord = async (name, summary) => {
    const target = currentDraft.current;
    setCopying(name);
    try {
      const record = api ? await api.record(selected, name) : summary;
      const latest = currentDraft.current;
      if (runBusy.current || latest.catalog !== target.catalog || latest.active !== target.active || latest.selected !== target.selected) {
        setMessage('The draft changed while the record was loading. Copy again to add it to the current draft.');
        return;
      }
      replaceRows([...rows, asNewRecord(selected, record)], { label: 'Copy existing record' });
      setMessage(`Copied into a new ${shortName(selected)} record. Give it a new name before importing.`);
    } catch (error) { setMessage(error); }
    finally { setCopying(null); }
  };
  const importFile = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setOpening(true);
    try {
      const incoming = parseCatalog(await file.text(), text => parse(text, { maxAliasCount: 50, uniqueKeys: true }), schema);
      setConfirm({ title: 'Replace this product draft with the imported catalog?', run: () => {
        setWorkspace(previous => ({ active: incoming.product_type, drafts: { ...previous.drafts, [incoming.product_type]: incoming } }));
        setSelected(schema.products[incoming.product_type].template); clearHistory(); setRun({ phase: 'idle' });
        setMessage(`Loaded ${file.name}`);
      } });
    } catch (error) { setMessage(error.message); }
    finally { setOpening(false); }
  };
  const onShortcut = event => {
    // Cells handle their own shortcuts; this covers focus on buttons and the page.
    if (event.defaultPrevented || !(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (event.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    const letter = event.key.toLowerCase();
    if (letter === 'z') { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
    if (letter === 'y') { event.preventDefault(); redo(); }
  };
  return <div className="catalog-app" onKeyDown={onShortcut}>
    <fieldset className="catalog-controls" disabled={busy} aria-busy={busy}>
    <header className="catalog-header">
      <div><span className="catalog-eyebrow">ilLumenate · Product tools</span><h1>YAML Builder</h1><p>Author the product records your ERPNext configurators need.</p></div>
      <div className="catalog-actions">
        <button onClick={onLegacy}>Family expansion editor</button>
        <button onClick={() => fileInput.current.click()}>Open YAML</button>
        <button onClick={() => download(toYaml(), filename)}>Save draft</button>
        <button className="catalog-primary" disabled={issues.length > 0} onClick={() => {
          download(toYaml(), filename);
          if (mode !== 'erp' && catalog.add_to_reference) {
            const addition = catalogAddition(catalog, schema, new Date().toISOString().slice(0, 10));
            setPending(previous => [...previous.filter(row => row.catalog !== addition.catalog), addition]);
          }
          setMessage(mode !== 'erp' && catalog.add_to_reference
            ? 'Catalog downloaded and added to the ERPNext reference in this browser. The CLI adds it to the shared reference when it generates the import package.'
            : mode === 'erp' ? 'Catalog downloaded. Use Check in ERPNext to validate it before importing.'
              : 'Catalog downloaded. Run the command below for engineering validation and CSV generation.');
        }}>Download catalog</button>
        {mode === 'erp' && <>
          <button disabled={issues.length > 0 || busy || copying !== null || opening || referenceLoading} onClick={() => executeRun(false)}>Check in ERPNext</button>
          <button className="catalog-primary" disabled={!canImport || busy || referenceLoading || copying !== null || opening} onClick={confirmImport}>Import to ERPNext</button>
        </>}
        <input ref={fileInput} type="file" accept=".yaml,.yml,.json" hidden onChange={importFile} />
      </div>
    </header>
    {mode !== 'erp' && <div className="catalog-offline-notice">
      To check and import, use the builder in ERPNext: <a href="https://illumenatelighting.v.frappe.cloud/catalog-builder" target="_blank" rel="noopener">Open ERPNext Catalog Builder</a>.
      {' '}Save draft here, then Open YAML there to move your work.
    </div>}
    <nav className="catalog-products" aria-label="Product families">
      {Object.entries(schema.products).map(([key, value]) => <button key={key} aria-pressed={workspace.active === key}
        onClick={() => { setWorkspace(previous => ({ ...previous, active: key })); setSelected(value.template); setMessage(''); setFieldSearch(''); setRun({ phase: 'idle' }); }}>
        {value.label}
      </button>)}
    </nav>
    {message && <div className="catalog-notice" role="status">{typeof message === 'string' ? message : <ApiError error={message} />}<button onClick={() => setMessage('')} aria-label="Dismiss message">×</button></div>}
    <div className="catalog-toolbar">
      <label>Catalog name <input value={catalog.series_name} onChange={e => setCatalog({ ...catalog, series_name: e.target.value }, { label: 'Rename catalog', key: 'series_name' })} placeholder="Your product family" /></label>
      {mode !== 'erp' && <label className="catalog-add-reference" title="Use this when you will import the package, so later catalogs can link to these records">
        <input type="checkbox" checked={Boolean(catalog.add_to_reference)} onChange={e => {
          const next = { ...catalog };
          if (e.target.checked) next.add_to_reference = true; else delete next.add_to_reference;
          setCatalog(next, { label: 'Add to reference setting' });
        }} /> Add to ERPNext reference after import</label>}
      <span>{total} records · {issues.length} checks to resolve</span>
      <button onClick={() => setConfirm({ title: 'Replace this draft with an illustrative example? Review engineering values before using it.', run: () => {
        setCatalog(structuredClone(examples[workspace.active]), { label: 'Load example' }); setSelected(product.template); setRun({ phase: 'idle' });
      } })}>Load example</button>
      <button onClick={() => setConfirm({ title: 'Clear this product draft?', run: () => { setCatalog(emptyCatalog(workspace.active), { label: 'Clear draft' }); setRun({ phase: 'idle' }); } })}>Clear draft</button>
    </div>
    {mode === 'erp' && <div className="catalog-run">
      {busy && <p className="catalog-progress" role="status"><span className="catalog-spinner" aria-hidden="true" />{run.phase === 'checking' ? 'Checking' : 'Importing'} {total} records…</p>}
      {(run.stale || (run.phase === 'checked' && run.payloadKey !== payloadKey)) && <p className="catalog-stale" role="status">Catalog changed since the last check — run Check again</p>}
      {run.error && <><ApiError error={run.error} />{run.uncertainImport && <p>Import confirmation was not received. Records may have been saved. Review recent checks and imports and refresh ERPNext records before checking again.</p>}</>}
      {run.response && <ImportResults key={historyRevision} response={run.response} onSelect={selectResult} />}
      {run.phase === 'imported' && <div className="catalog-imported" role="status">
        <p>Import complete. Re-checking this draft will report duplicates for the records just created. Start a new draft for your next catalog.</p>
        <button onClick={() => setConfirm({ title: 'Start a new draft for this product?', label: 'Start a new draft', run: () => {
          setCatalog(emptyCatalog(workspace.active)); clearHistory(); setRun({ phase: 'idle' });
        } })}>Start a new draft</button>
      </div>}
    </div>}
    <div className={`catalog-layout ${view.wide ? 'is-wide' : ''}`}>
      <aside className="catalog-sidebar">
        <h2>ERPNext records</h2><input aria-label="Find a DocType" placeholder="Find a DocType…" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="catalog-type-list">{orderedTypes.map(doctype => <button key={doctype} aria-pressed={selected === doctype}
          onClick={() => { setSelected(doctype); setFieldSearch(''); }}>{shortName(doctype)} <span>{catalog.records[doctype]?.length || ''}</span></button>)}</div>
      </aside>
      <main className="catalog-editor">
        <div className="catalog-section-title"><div><h2>{shortName(selected)}</h2><p>{rows.length} records in this catalog</p></div>
          <div className="catalog-segmented" role="group" aria-label="Record view">
            <button aria-pressed={view.table} onClick={() => saveView({ ...view, table: true })} title="One row per record, one column per field">Table</button>
            <button aria-pressed={!view.table} onClick={() => saveView({ ...view, table: false })} title="One card per record, with field descriptions">Cards</button>
          </div>
          <button aria-pressed={view.wide} onClick={() => saveView({ ...view, wide: !view.wide })} title="Give the editor the full width and show import readiness below it">Wide</button>
          <button disabled={!timeline.past.length} onClick={undo} title={timeline.past.length ? `Undo ${timeline.past.at(-1).label.toLowerCase()} (Ctrl+Z)` : 'Nothing to undo'}>↶ Undo</button>
          <button disabled={!timeline.future.length} onClick={redo} title={timeline.future.length ? `Redo ${timeline.future.at(-1).label.toLowerCase()} (Ctrl+Y)` : 'Nothing to redo'}>↷ Redo</button>
          {!view.table && <button className="catalog-primary" onClick={() => replaceRows([...rows, blankRecord(selected, schema)], { label: 'Add record' })}>+ Add record</button>}</div>
        <ReferencePanel key={selected} doctype={selected} reference={reference}
          onCopy={copyRecord} copying={copying} />
        <input className="catalog-field-search" aria-label="Find a field" placeholder={view.table ? 'Show columns matching…' : 'Find a field by name…'} value={fieldSearch} onChange={e => setFieldSearch(e.target.value)} />
        {view.table ? <GridData.Provider value={{ catalog, reference, issues: cellIssues, undo, redo }}>
          <RecordGrid key={selected} doctype={selected} rows={rows} columnFilter={fieldSearch} onChange={replaceRows}
            copyRow={row => asNewRecord(selected, row)} rowIdPrefix={recordPrefix(selected)} />
        </GridData.Provider> : <>
          {!rows.length && <div className="catalog-empty"><h3>Add your first {shortName(selected)} record</h3><p>Use the current ERPNext fields below, or load an example to explore a complete product setup.</p></div>}
          {rows.map((row, index) => <section className="catalog-record" id={recordId(selected, index)} tabIndex={-1} key={index}>
            <div className="catalog-record-title"><h3>{recordName(selected, row, schema) || `New record ${index + 1}`}</h3>
              <button onClick={() => replaceRows([...rows, asNewRecord(selected, row)], { label: 'Duplicate record' })}>Duplicate</button>
              <button className="catalog-danger" onClick={() => replaceRows(rows.filter((_, i) => i !== index), { label: 'Remove record' })}>Remove</button></div>
            <RecordFields doctype={selected} row={row} catalog={catalog} reference={reference} filter={fieldSearch}
              onChange={next => replaceRows(rows.map((item, i) => i === index ? next : item), { label: 'Edit record', key: `form:${selected}[${index}]` })} />
          </section>)}
        </>}
      </main>
      <aside className="catalog-review">
        <h2>Import readiness</h2><p>Each link must point to a record in this catalog, a record in {mode === 'erp' ? 'the live ERPNext list' : 'the ERPNext export'}, or a record you confirm already exists in ERPNext.</p>
        <p>{reference ? `${fromErp} links resolve to existing ERPNext records (${reference.source === 'live' ? `live from ERPNext, loaded ${loadedTime(reference.exported_on)}` : `export of ${reference.exported_on}`}).` : referenceLoading ? 'Loading existing ERPNext records…' : 'Existing ERPNext records have not loaded.'}</p>
        {referenceError && <ApiError error={referenceError} />}
        {mode === 'erp' && <button disabled={referenceLoading} onClick={() => loadExisting({ refresh: true })}>{referenceLoading ? 'Loading ERPNext records…' : 'Refresh ERPNext records'}</button>}
        {reference?.skipped?.length > 0 && <details><summary>No read access to {reference.skipped.length} DocTypes</summary><p>No read access to: {reference.skipped.join(', ')}</p></details>}
        {mode !== 'erp' && catalog.add_to_reference && <p className="catalog-ok">On download, this catalog's records become existing ERPNext records for your other catalogs. Import the package into ERPNext and commit the reference file the CLI updates.</p>}
        {mode !== 'erp' && ownPending.length > 0 && <details><summary>{ownPending.length} {ownPending.length === 1 ? 'catalog' : 'catalogs'} pending in this browser</summary>
          <p>These count as existing until the shared reference includes them.</p>
          {ownPending.map(row => <div className="catalog-link" key={row.catalog}><strong>{row.catalog}</strong>
            <small>{Object.values(row.records).reduce((sum, names) => sum + names.length, 0)} records · {row.added_on}{row.catalog === catalogKey(catalog) ? ' · this catalog' : ''}</small>
            <button onClick={() => setPending(previous => previous.filter(item => item.catalog !== row.catalog))}>Remove from this browser</button></div>)}</details>}
        {missing.some(link => link.doctype === 'Item') && <button onClick={() => { setCatalog(makeItemRecords(catalog, schema, reference), { label: 'Create missing Items' }); setSelected('Item'); }}>Create missing Item records</button>}
        {missing.length > 0 && <details open><summary>{missing.length} unresolved links</summary>{missing.map(link => <div className="catalog-link" key={JSON.stringify([link.doctype, link.name])}>
          <strong>{link.name}</strong><small>{link.doctype || 'Select the Dynamic Link DocType first'}</small>
          {link.doctype && <button onClick={() => setCatalog({ ...catalog, external_links: { ...catalog.external_links, [link.doctype]: [...(catalog.external_links[link.doctype] || []), link.name] } }, { label: 'Declare existing record' })}>Use existing ERPNext record</button>}
        </div>)}</details>}
        {unconfirmed.length > 0 && <details open><summary>{unconfirmed.length} declared records not in {mode === 'erp' ? 'the live ERPNext list' : 'the ERPNext export'}</summary>
          <p>{mode === 'erp' ? 'Check for a typo, refresh the list, or confirm you have read access to the record.' : 'Check for a typo, or confirm the record was created after the export.'}</p>
          {unconfirmed.map(link => <div className="catalog-link" key={`${link.doctype}/${link.name}`}><strong>{link.name}</strong><small>{link.doctype}</small></div>)}</details>}
        <details><summary>Declared existing ERPNext records ({Object.values(catalog.external_links).reduce((sum, names) => sum + names.length, 0)})</summary>
          {Object.entries(catalog.external_links).flatMap(([doctype, names]) => names.map(name => <div className="catalog-link" key={`${doctype}/${name}`}><strong>{name}</strong><small>{doctype}</small>
            <button onClick={() => setCatalog({ ...catalog, external_links: { ...catalog.external_links, [doctype]: names.filter(value => value !== name) } }, { label: 'Remove declaration' })}>Remove declaration</button></div>))}</details>
        {issues.length > 0 ? <details><summary>{issues.length} validation findings</summary><ul>{issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></details> : <p className="catalog-ok">Structure and references are ready for {mode === 'erp' ? 'Check in ERPNext' : 'CLI engineering validation'}.</p>}
        {mode === 'erp' ? <>
          <h3>Check and import in ERPNext</h3>
          <p>Check is a full dry run with ERPNext validation. Import is all-or-nothing. Publication remains separate, through Readiness and Publication.</p>
          <ImportHistory api={api} revision={historyRevision} />
        </> : <>
          <h3>Generate the import package</h3><code>python -m tools.fixture_builder --config "{filename}" --output ./output/{workspace.active}/</code>
          <p>The CLI validates engineering values and creates ordered CSVs plus an import manifest. Run it from the repository root.</p>
        </>}
        <button onClick={() => setShowPreview(!showPreview)}>{showPreview ? 'Hide YAML' : 'Preview YAML'}</button>
        {showPreview && <pre>{yaml}</pre>}
      </aside>
    </div>
    </fieldset>
    {confirm && <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />}
  </div>;
}
