import { useEffect, useMemo, useRef, useState, useId } from 'react';
import { parse, stringify } from 'yaml';
import schema from './catalog-schema.json';
import examples from './catalog-examples.json';
import { blankRecord, emptyCatalog, recordName, catalogIssues, parseCatalog, unresolvedLinks, makeItemRecords } from './catalog-model.js';
import './catalog.css';

const STORAGE = 'illumenate-product-catalog-v2';
const parentTypes = Object.keys(schema.doctypes).filter(name => !schema.doctypes[name].istable);
const shortName = name => name.replace(/^ilL-/, '');

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

function download(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/yaml;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function RecordFields({ doctype, row, onChange, catalog, filter = '', depth = 0 }) {
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
            <RecordFields doctype={field.options} row={child && typeof child === 'object' ? child : {}} catalog={catalog} depth={depth + 1}
              onChange={next => edit(key, children.map((item, index) => index === i ? next : item))} />
            <button className="catalog-danger" onClick={() => edit(key, children.filter((_, index) => index !== i))}>Remove row {i + 1}</button>
          </fieldset>)}
          <button onClick={() => edit(key, [...children, blankRecord(field.options, schema)])}>+ Add {field.label} row</button>
        </details>;
      }
      const target = field.fieldtype === 'Dynamic Link' ? row[field.options] : field.options;
      const suggestions = ['Link', 'Dynamic Link'].includes(field.fieldtype)
        ? [...new Set([...(catalog.records[target] || []).map(item => recordName(target, item, schema)), ...(catalog.external_links[target] || [])])].filter(Boolean) : [];
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
          {suggestions.length > 0 && <datalist id={`${inputId}-choices`}>{suggestions.map(option => <option key={option} value={option} />)}</datalist>}</>;
      }
      return <div className={`catalog-field ${field.fieldtype === 'Check' ? 'catalog-check' : ''}`} key={key}>
        <label htmlFor={inputId}>{field.label || key}{field.reqd ? ' *' : ''}</label>
        {input}
        {['Link', 'Dynamic Link'].includes(field.fieldtype) && <small>Links to {target || 'the selected attribute DocType'}</small>}
        {field.description && <small>{field.description.replace(/<[^>]*>/g, '')}</small>}
      </div>;
    })}
  </div>;
}

export default function CatalogApp({ onLegacy }) {
  const [workspace, setWorkspace] = useState(restore);
  const [selected, setSelected] = useState('Item');
  const [search, setSearch] = useState('');
  const [fieldSearch, setFieldSearch] = useState('');
  const [message, setMessage] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [undo, setUndo] = useState(null);
  const fileInput = useRef(null);
  const catalog = workspace.drafts[workspace.active] || emptyCatalog(workspace.active);
  const product = schema.products[workspace.active];
  const setCatalog = next => setWorkspace(previous => ({ ...previous, drafts: { ...previous.drafts, [previous.active]: next } }));
  useEffect(() => {
    try { localStorage.setItem(STORAGE, JSON.stringify(workspace)); }
    catch { setMessage('Browser storage is full or unavailable. Download YAML to save your work.'); }
  }, [workspace]);
  const yaml = useMemo(() => '# ilLumenate product catalog — validate and generate with tools.fixture_builder\n' + stringify(catalog, { lineWidth: 0 }), [catalog]);
  const issues = useMemo(() => catalogIssues(catalog, schema), [catalog]);
  const missing = useMemo(() => unresolvedLinks(catalog, schema), [catalog]);
  const total = Object.values(catalog.records).reduce((sum, rows) => sum + rows.length, 0);
  const orderedTypes = [...new Set(['Item', product.spec, product.template, 'ilL-Webflow-Product', ...Object.keys(catalog.records), ...parentTypes])]
    .filter(name => name.toLowerCase().includes(search.toLowerCase()));
  const rows = catalog.records[selected] || [];
  const filename = `${(catalog.series_name || workspace.active).toLowerCase().replace(/[^a-z0-9]+/g, '-')}-catalog.yaml`;
  const replaceRows = next => setCatalog({ ...catalog, records: { ...catalog.records, [selected]: next } });
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
        <button className="catalog-primary" disabled={issues.length > 0} onClick={() => { download(yaml, filename); setMessage('Catalog downloaded. Run the command below for engineering validation and CSV generation.'); }}>Download catalog</button>
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
        <input className="catalog-field-search" aria-label="Find a field" placeholder="Find a field by name…" value={fieldSearch} onChange={e => setFieldSearch(e.target.value)} />
        {!rows.length && <div className="catalog-empty"><h3>Add your first {shortName(selected)} record</h3><p>Use the current ERPNext fields below, or load an example to explore a complete product setup.</p></div>}
        {rows.map((row, index) => <section className="catalog-record" key={index}>
          <div className="catalog-record-title"><h3>{recordName(selected, row, schema) || `New record ${index + 1}`}</h3>
            <button onClick={() => replaceRows([...rows, { ...structuredClone(row), ...(schema.doctypes[selected].autoname?.startsWith('field:') ? { [schema.doctypes[selected].autoname.slice(6)]: '' } : { name: '' }) }])}>Duplicate</button>
            <button className="catalog-danger" onClick={() => { setUndo(structuredClone(catalog)); replaceRows(rows.filter((_, i) => i !== index)); }}>Remove</button></div>
          <RecordFields doctype={selected} row={row} catalog={catalog} filter={fieldSearch} onChange={next => replaceRows(rows.map((item, i) => i === index ? next : item))} />
        </section>)}
        {undo && <button onClick={() => { setCatalog(undo); setUndo(null); }}>Undo record removal</button>}
      </main>
      <aside className="catalog-review">
        <h2>Import readiness</h2><p>Each link must point to a record in this catalog or a record you confirm already exists in ERPNext.</p>
        {missing.some(link => link.doctype === 'Item') && <button onClick={() => { setCatalog(makeItemRecords(catalog, schema)); setSelected('Item'); }}>Create missing Item records</button>}
        {missing.length > 0 && <details open><summary>{missing.length} unresolved links</summary>{missing.map(link => <div className="catalog-link" key={JSON.stringify([link.doctype, link.name])}>
          <strong>{link.name}</strong><small>{link.doctype || 'Select the Dynamic Link DocType first'}</small>
          {link.doctype && <button onClick={() => setCatalog({ ...catalog, external_links: { ...catalog.external_links, [link.doctype]: [...(catalog.external_links[link.doctype] || []), link.name] } })}>Use existing ERPNext record</button>}
        </div>)}</details>}
        <details><summary>Existing ERPNext records ({Object.values(catalog.external_links).reduce((sum, names) => sum + names.length, 0)})</summary>
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
