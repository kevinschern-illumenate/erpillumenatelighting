import { useCallback, useEffect, useMemo, useRef, useState, useId } from 'react';
import { parse, stringify } from 'yaml';
import schema from './catalog-schema.json';
import examples from './catalog-examples.json';
import {
  blankRecord, emptyCatalog, recordName, catalogIssues, parseCatalog, unresolvedLinks, makeItemRecords,
  inReference, referenceSummary, withReferenceLinks, unconfirmedLinks, isComplete,
  catalogAddition, mergeAdditions, excludeCatalog, referenceOrigin, catalogKey,
} from './catalog-model.js';
import './catalog.css';

const STORAGE = 'illumenate-product-catalog-v2';
// Catalogs downloaded with "Add to ERPNext reference", until the checked-in reference includes them.
const PENDING = 'illumenate-erp-reference-pending';
const parentTypes = Object.keys(schema.doctypes).filter(name => !schema.doctypes[name].istable);
const shortName = name => name.replace(/^ilL-/, '');
// The server timestamp is already in the site's timezone; keep that clock time.
const loadedTime = timestamp => timestamp?.slice(11, 16) || 'unknown';

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

export function RecordFields({ doctype, row, onChange, catalog, reference = null, filter = '', depth = 0 }) {
  const id = useId();
  const meta = schema.doctypes[doctype];
  const edit = (key, value) => {
    const next = { ...row };
    if (value === '') delete next[key]; else next[key] = value;
    onChange(next);
  };
  const fields = meta.fields.filter(field => !field.read_only || Object.hasOwn(row, field.fieldname));
  if (!depth && (!meta.autoname || meta.autoname === 'prompt')) {
    fields.unshift({ fieldname: 'name', label: 'Record ID', fieldtype: 'Data', reqd: meta.autoname === 'prompt' });
  }
  return <div className="catalog-fields">
    {fields.filter(field => !filter || `${field.label} ${field.fieldname}`.toLowerCase().includes(filter.toLowerCase())).map(field => {
      const key = field.fieldname;
      const value = row[key] ?? '';
      const inputId = `${id}-${key}`;
      if (['Table', 'Table MultiSelect'].includes(field.fieldtype)) {
        const children = Array.isArray(value) ? value : [];
        return <details className="catalog-table" key={key} open={children.length > 0 || undefined}>
          <summary>{field.label} {field.reqd ? '*' : ''} <span>{children.length} rows</span></summary>
          {value && !Array.isArray(value) && <p role="alert">Invalid child table. Replace it with rows below.</p>}
          {children.map((child, i) => <fieldset key={i}>
            <legend>{field.label} · {i + 1}</legend>
            <RecordFields doctype={field.options} row={child && typeof child === 'object' ? child : {}} catalog={catalog} reference={reference} depth={depth + 1}
              onChange={next => edit(key, children.map((item, index) => index === i ? next : item))} />
            <button className="catalog-danger" onClick={() => edit(key, children.filter((_, index) => index !== i))}>Remove row {i + 1}</button>
          </fieldset>)}
          <button onClick={() => edit(key, [...children, blankRecord(field.options, schema)])}>+ Add {field.label} row</button>
        </details>;
      }
      const target = field.fieldtype === 'Dynamic Link' ? row[field.options] : field.options;
      const isLink = ['Link', 'Dynamic Link'].includes(field.fieldtype);
      const existing = isLink ? reference?.doctypes?.[target]?.records || {} : {};
      const suggestions = isLink
        ? [...new Set([...(catalog.records[target] || []).map(item => recordName(target, item, schema)), ...(catalog.external_links[target] || []),
          ...Object.keys(existing)])].filter(Boolean) : [];
      const numeric = ['Int', 'Float', 'Currency', 'Percent'].includes(field.fieldtype);
      let input;
      if (field.fieldtype === 'Check') {
        input = <input id={inputId} type="checkbox" checked={Boolean(value)} onChange={e => edit(key, e.target.checked ? 1 : 0)} />;
      } else if (field.fieldtype === 'Select') {
        input = <select id={inputId} value={value} onChange={e => edit(key, e.target.value)}>
          <option value="">Select…</option>
          {(field.options || '').split('\n').filter(Boolean).map(option => <option key={option}>{option}</option>)}
        </select>;
      } else if (['Small Text', 'Text', 'Long Text', 'Text Editor', 'JSON', 'Code'].includes(field.fieldtype)) {
        input = <textarea id={inputId} rows={3} value={typeof value === 'object' ? JSON.stringify(value, null, 2) : value} onChange={e => edit(key, e.target.value)} />;
      } else {
        input = <><input id={inputId} type={numeric ? 'number' : 'text'} step={field.fieldtype === 'Int' ? '1' : 'any'} value={value}
          list={suggestions.length ? `${inputId}-choices` : undefined}
          onChange={e => edit(key, numeric && e.target.value !== '' ? Number(e.target.value) : e.target.value)} />
          {suggestions.length > 0 && <datalist id={`${inputId}-choices`}>{suggestions.map(option => <option key={option} value={option}
            label={Object.hasOwn(existing, option) ? `ERPNext · ${referenceSummary(target, existing[option], schema, 3)}` : undefined} />)}</datalist>}</>;
      }
      return <div className={`catalog-field ${field.fieldtype === 'Check' ? 'catalog-check' : ''}`} key={key}>
        <label htmlFor={inputId}>{field.label || key}{field.reqd ? ' *' : ''}</label>
        {input}
        {isLink && <small>Links to {target || 'the selected attribute DocType'}</small>}
        {isLink && value !== '' && inReference(reference, target, String(value)) && <small className="catalog-ok">
          Existing ERPNext record{referenceSummary(target, existing[String(value)], schema) ? ` · ${referenceSummary(target, existing[String(value)], schema)}` : ''}</small>}
        {field.description && <small>{field.description.replace(/<[^>]*>/g, '')}</small>}
      </div>;
    })}
  </div>;
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

export default function CatalogApp({ onLegacy, loadReference, fetchRecord, mode = 'vercel' }) {
  const [workspace, setWorkspace] = useState(restore);
  const [selected, setSelected] = useState('Item');
  const [search, setSearch] = useState('');
  const [fieldSearch, setFieldSearch] = useState('');
  const [message, setMessage] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [undo, setUndo] = useState(null);
  const [exported, setExported] = useState(null);
  const [pending, setPending] = useState(restorePending);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [referenceError, setReferenceError] = useState('');
  const [copying, setCopying] = useState(null);
  const fileInput = useRef(null);
  const referenceRequest = useRef(0);
  const loadExisting = useCallback(async (options) => {
    const request = ++referenceRequest.current;
    setReferenceLoading(true);
    setReferenceError('');
    try {
      const data = await loadReference(options);
      if (request !== referenceRequest.current) return;
      if (data?.unavailable) throw new Error('Existing ERPNext records are unavailable. Declare existing records manually.');
      setExported(data);
    } catch (error) {
      if (request === referenceRequest.current) setReferenceError(error.message || 'Existing ERPNext records could not be loaded.');
    } finally {
      if (request === referenceRequest.current) setReferenceLoading(false);
    }
  }, [loadReference]);
  useEffect(() => {
    loadExisting();
    return () => { referenceRequest.current += 1; };
  }, [loadExisting]);
  const catalog = useMemo(() => workspace.drafts[workspace.active] || emptyCatalog(workspace.active), [workspace]);
  const currentDraft = useRef(null);
  currentDraft.current = { catalog, active: workspace.active, selected };
  const product = schema.products[workspace.active];
  const setCatalog = next => setWorkspace(previous => ({ ...previous, drafts: { ...previous.drafts, [previous.active]: next } }));
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
  const yaml = useMemo(() => '# ilLumenate product catalog — validate and generate with tools.fixture_builder\n' + stringify(resolved, { lineWidth: 0 }), [resolved]);
  const issues = useMemo(() => catalogIssues(mode === 'erp' ? { ...catalog, add_to_reference: false } : catalog, schema, reference), [catalog, reference, mode]);
  const missing = useMemo(() => unresolvedLinks(catalog, schema, reference), [catalog, reference]);
  const unconfirmed = useMemo(() => unconfirmedLinks(catalog, reference), [catalog, reference]);
  const fromErp = Object.values(resolved.external_links).reduce((sum, names) => sum + names.length, 0)
    - Object.values(catalog.external_links).reduce((sum, names) => sum + names.length, 0);
  const total = Object.values(catalog.records).reduce((sum, rows) => sum + rows.length, 0);
  const orderedTypes = [...new Set(['Item', product.spec, product.template, 'ilL-Webflow-Product', ...Object.keys(catalog.records), ...parentTypes])]
    .filter(name => name.toLowerCase().includes(search.toLowerCase()));
  const rows = catalog.records[selected] || [];
  const filename = `${(catalog.series_name || workspace.active).toLowerCase().replace(/[^a-z0-9]+/g, '-')}-catalog.yaml`;
  const replaceRows = next => setCatalog({ ...catalog, records: { ...catalog.records, [selected]: next } });
  const copyRecord = async (name, summary) => {
    const target = currentDraft.current;
    setCopying(name);
    try {
      const record = fetchRecord ? await fetchRecord(selected, name) : summary;
      const latest = currentDraft.current;
      if (latest.catalog !== target.catalog || latest.active !== target.active || latest.selected !== target.selected) {
        setMessage('The draft changed while the record was loading. Copy again to add it to the current draft.');
        return;
      }
      replaceRows([...rows, asNewRecord(selected, record)]);
      setMessage(`Copied into a new ${shortName(selected)} record. Give it a new name before importing.`);
    } catch (error) { setMessage(error.message || 'The ERPNext record could not be copied.'); }
    finally { setCopying(null); }
  };
  const importFile = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const incoming = parseCatalog(await file.text(), text => parse(text, { maxAliasCount: 50, uniqueKeys: true }), schema);
      setConfirm({ title: 'Replace this product draft with the imported catalog?', run: () => {
        setWorkspace(previous => ({ active: incoming.product_type, drafts: { ...previous.drafts, [incoming.product_type]: incoming } }));
        setSelected(schema.products[incoming.product_type].template); setUndo(null);
        setMessage(`Loaded ${file.name}`);
      } });
    } catch (error) { setMessage(error.message); }
  };
  return <div className="catalog-app">
    <header className="catalog-header">
      <div><span className="catalog-eyebrow">ilLumenate · Product tools</span><h1>YAML Builder</h1><p>Author the product records your ERPNext configurators need.</p></div>
      <div className="catalog-actions">
        <button onClick={onLegacy}>Family expansion editor</button>
        <button onClick={() => fileInput.current.click()}>Open YAML</button>
        <button onClick={() => download(yaml, filename)}>Save draft</button>
        <button className="catalog-primary" disabled={issues.length > 0} onClick={() => {
          download(yaml, filename);
          if (mode !== 'erp' && catalog.add_to_reference) {
            const addition = catalogAddition(catalog, schema, new Date().toISOString().slice(0, 10));
            setPending(previous => [...previous.filter(row => row.catalog !== addition.catalog), addition]);
          }
          setMessage(mode !== 'erp' && catalog.add_to_reference
            ? 'Catalog downloaded and added to the ERPNext reference in this browser. The CLI adds it to the shared reference when it generates the import package.'
            : 'Catalog downloaded. Run the command below for engineering validation and CSV generation.');
        }}>Download catalog</button>
        <input ref={fileInput} type="file" accept=".yaml,.yml,.json" hidden onChange={importFile} />
      </div>
    </header>
    <nav className="catalog-products" aria-label="Product families">
      {Object.entries(schema.products).map(([key, value]) => <button key={key} aria-pressed={workspace.active === key}
        onClick={() => { setWorkspace(previous => ({ ...previous, active: key })); setSelected(value.template); setUndo(null); setMessage(''); setFieldSearch(''); }}>
        {value.label}
      </button>)}
    </nav>
    {message && <div className="catalog-notice" role="status">{message}<button onClick={() => setMessage('')} aria-label="Dismiss message">×</button></div>}
    <div className="catalog-toolbar">
      <label>Catalog name <input value={catalog.series_name} onChange={e => setCatalog({ ...catalog, series_name: e.target.value })} placeholder="Your product family" /></label>
      {mode !== 'erp' && <label className="catalog-add-reference" title="Use this when you will import the package, so later catalogs can link to these records">
        <input type="checkbox" checked={Boolean(catalog.add_to_reference)} onChange={e => {
          const next = { ...catalog };
          if (e.target.checked) next.add_to_reference = true; else delete next.add_to_reference;
          setCatalog(next);
        }} /> Add to ERPNext reference after import</label>}
      <span>{total} records · {issues.length} checks to resolve</span>
      <button onClick={() => setConfirm({ title: 'Replace this draft with an illustrative example? Review engineering values before using it.', run: () => {
        setCatalog(structuredClone(examples[workspace.active])); setSelected(product.template); setUndo(null);
      } })}>Load example</button>
      <button onClick={() => setConfirm({ title: 'Clear this product draft?', run: () => { setCatalog(emptyCatalog(workspace.active)); setUndo(null); } })}>Clear draft</button>
    </div>
    <div className="catalog-layout">
      <aside className="catalog-sidebar">
        <h2>ERPNext records</h2><input aria-label="Find a DocType" placeholder="Find a DocType…" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="catalog-type-list">{orderedTypes.map(doctype => <button key={doctype} aria-pressed={selected === doctype}
          onClick={() => { setSelected(doctype); setFieldSearch(''); }}>{shortName(doctype)} <span>{catalog.records[doctype]?.length || ''}</span></button>)}</div>
      </aside>
      <main className="catalog-editor">
        <div className="catalog-section-title"><div><h2>{shortName(selected)}</h2><p>{rows.length} records in this catalog</p></div>
          <button className="catalog-primary" onClick={() => replaceRows([...rows, blankRecord(selected, schema)])}>+ Add record</button></div>
        <ReferencePanel key={selected} doctype={selected} reference={reference}
          onCopy={copyRecord} copying={copying} />
        <input className="catalog-field-search" aria-label="Find a field" placeholder="Find a field by name…" value={fieldSearch} onChange={e => setFieldSearch(e.target.value)} />
        {!rows.length && <div className="catalog-empty"><h3>Add your first {shortName(selected)} record</h3><p>Use the current ERPNext fields below, or load an example to explore a complete product setup.</p></div>}
        {rows.map((row, index) => <section className="catalog-record" key={index}>
          <div className="catalog-record-title"><h3>{recordName(selected, row, schema) || `New record ${index + 1}`}</h3>
            <button onClick={() => replaceRows([...rows, asNewRecord(selected, row)])}>Duplicate</button>
            <button className="catalog-danger" onClick={() => { setUndo(structuredClone(catalog)); replaceRows(rows.filter((_, i) => i !== index)); }}>Remove</button></div>
          <RecordFields doctype={selected} row={row} catalog={catalog} reference={reference} filter={fieldSearch} onChange={next => replaceRows(rows.map((item, i) => i === index ? next : item))} />
        </section>)}
        {undo && <button onClick={() => { setCatalog(undo); setUndo(null); }}>Undo record removal</button>}
      </main>
      <aside className="catalog-review">
        <h2>Import readiness</h2><p>Each link must point to a record in this catalog, a record in {mode === 'erp' ? 'the live ERPNext list' : 'the ERPNext export'}, or a record you confirm already exists in ERPNext.</p>
        <p>{reference ? `${fromErp} links resolve to existing ERPNext records (${reference.source === 'live' ? `live from ERPNext, loaded ${loadedTime(reference.exported_on)}` : `export of ${reference.exported_on}`}).` : referenceLoading ? 'Loading existing ERPNext records…' : 'Existing ERPNext records have not loaded.'}</p>
        {referenceError && <p role="alert">{referenceError}</p>}
        {mode === 'erp' && <button disabled={referenceLoading} onClick={() => loadExisting({ refresh: true })}>{referenceLoading ? 'Loading ERPNext records…' : 'Refresh ERPNext records'}</button>}
        {reference?.skipped?.length > 0 && <details><summary>No read access to {reference.skipped.length} DocTypes</summary><p>No read access to: {reference.skipped.join(', ')}</p></details>}
        {mode !== 'erp' && catalog.add_to_reference && <p className="catalog-ok">On download, this catalog's records become existing ERPNext records for your other catalogs. Import the package into ERPNext and commit the reference file the CLI updates.</p>}
        {mode !== 'erp' && ownPending.length > 0 && <details><summary>{ownPending.length} {ownPending.length === 1 ? 'catalog' : 'catalogs'} pending in this browser</summary>
          <p>These count as existing until the shared reference includes them.</p>
          {ownPending.map(row => <div className="catalog-link" key={row.catalog}><strong>{row.catalog}</strong>
            <small>{Object.values(row.records).reduce((sum, names) => sum + names.length, 0)} records · {row.added_on}{row.catalog === catalogKey(catalog) ? ' · this catalog' : ''}</small>
            <button onClick={() => setPending(previous => previous.filter(item => item.catalog !== row.catalog))}>Remove from this browser</button></div>)}</details>}
        {missing.some(link => link.doctype === 'Item') && <button onClick={() => { setCatalog(makeItemRecords(catalog, schema, reference)); setSelected('Item'); }}>Create missing Item records</button>}
        {missing.length > 0 && <details open><summary>{missing.length} unresolved links</summary>{missing.map(link => <div className="catalog-link" key={JSON.stringify([link.doctype, link.name])}>
          <strong>{link.name}</strong><small>{link.doctype || 'Select the Dynamic Link DocType first'}</small>
          {link.doctype && <button onClick={() => setCatalog({ ...catalog, external_links: { ...catalog.external_links, [link.doctype]: [...(catalog.external_links[link.doctype] || []), link.name] } })}>Use existing ERPNext record</button>}
        </div>)}</details>}
        {unconfirmed.length > 0 && <details open><summary>{unconfirmed.length} declared records not in {mode === 'erp' ? 'the live ERPNext list' : 'the ERPNext export'}</summary>
          <p>{mode === 'erp' ? 'Check for a typo, refresh the list, or confirm you have read access to the record.' : 'Check for a typo, or confirm the record was created after the export.'}</p>
          {unconfirmed.map(link => <div className="catalog-link" key={`${link.doctype}/${link.name}`}><strong>{link.name}</strong><small>{link.doctype}</small></div>)}</details>}
        <details><summary>Declared existing ERPNext records ({Object.values(catalog.external_links).reduce((sum, names) => sum + names.length, 0)})</summary>
          {Object.entries(catalog.external_links).flatMap(([doctype, names]) => names.map(name => <div className="catalog-link" key={`${doctype}/${name}`}><strong>{name}</strong><small>{doctype}</small>
            <button onClick={() => setCatalog({ ...catalog, external_links: { ...catalog.external_links, [doctype]: names.filter(value => value !== name) } })}>Remove declaration</button></div>))}</details>
        {issues.length > 0 ? <details><summary>{issues.length} validation findings</summary><ul>{issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></details> : <p className="catalog-ok">Structure and references are ready for CLI engineering validation.</p>}
        <h3>Generate the import package</h3><code>python -m tools.fixture_builder --config "{filename}" --output ./output/{workspace.active}/</code>
        <p>The CLI validates engineering values and creates ordered CSVs plus an import manifest. Run it from the repository root.</p>
        <button onClick={() => setShowPreview(!showPreview)}>{showPreview ? 'Hide YAML' : 'Preview YAML'}</button>
        {showPreview && <pre>{yaml}</pre>}
      </aside>
    </div>
    {confirm && <div className="catalog-modal-backdrop"><div className="catalog-modal" role="dialog" aria-modal="true" aria-label="Replace draft">
      <h2>{confirm.title}</h2><p>Download your current draft first if you want to keep a copy.</p>
      <button autoFocus onClick={() => setConfirm(null)}>Cancel</button><button className="catalog-primary" onClick={() => { confirm.run(); setConfirm(null); }}>Replace draft</button>
    </div></div>}
  </div>;
}
