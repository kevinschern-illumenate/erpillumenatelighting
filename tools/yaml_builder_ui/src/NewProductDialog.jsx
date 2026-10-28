import { useEffect, useId, useMemo, useRef, useState } from 'react';
import schema from './catalog-schema.json';
import { applyStarter, defaultName, placeholders, starterPreview, templateName } from './starter-model.js';

const shortName = name => name.replace(/^ilL-/, '');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const SHOWN = 12;

/**
 * Start a new product from a starter in one pass: every record the product needs, named from
 * the product code, series and name. Built-in starters are the examples; saved starters are
 * drafts saved in this browser with Save as starter.
 */
export default function NewProductDialog({ product, productType, starters, reference, onApply, onDelete, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  const seriesList = useId();
  useEffect(() => { dialog.current.showModal(); }, []);
  const choices = starters.filter(item => item.productType === productType);
  const [starterId, setStarterId] = useState(() => choices.find(item => !item.builtin)?.id || choices[0]?.id || '');
  const starter = choices.find(item => item.id === starterId) || choices[0];
  const [code, setCode] = useState('');
  const [series, setSeries] = useState('');
  const [name, setName] = useState('');
  const [picks, setPicks] = useState(() => new Map());
  const needed = useMemo(() => (starter ? placeholders(starter.catalog, reference) : []), [starter, reference]);
  const values = { code, series, name };
  const ready = Boolean(starter && code.trim() && series.trim());
  const result = useMemo(() => ready ? applyStarter(starter, values, { schema, reference, picks }) : null,
    [starter, code, series, name, reference, picks]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = useMemo(() => result ? starterPreview(result.catalog, schema, reference) : [], [result, reference]);
  const counts = preview.reduce((total, row) => ({ ...total, [row.doctype]: (total[row.doctype] || 0) + 1 }), {});
  const taken = preview.filter(row => row.exists);
  const existingSeries = Object.keys(reference?.doctypes?.['ilL-Attribute-Series']?.records || {});

  return <dialog ref={dialog} className="catalog-modal catalog-modal-wide catalog-new-product" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>New {product.label.toLowerCase()} product</h2>
    <p>Creates every record a {product.label.toLowerCase()} product needs in one pass, named from your product code: Items, specs, maps,
      the template with its options, and the Webflow product. Then fill in the engineering values; Import readiness lists what is left.</p>
    {!choices.length ? <p className="catalog-run-errors">No starters for this product type.</p> : <>
      <section className="catalog-clone-step" aria-label="Starter">
        <h3>1. Start from</h3>
        <div className="catalog-new-starters" role="radiogroup" aria-label="Starter">
          {choices.map(item => <label key={item.id}><input type="radio" name="starter" checked={item.id === starter.id}
            onChange={() => { setStarterId(item.id); setPicks(new Map()); }} />
            <span><strong>{item.label}</strong><small>{item.builtin ? 'Built-in starter with typical values to review'
              : `Saved ${item.saved_on || ''} · names from ${item.code}`} · {plural(Object.values(item.catalog.records).reduce((sum, rows) => sum + rows.length, 0), 'record')}</small></span>
            {!item.builtin && <button type="button" className="catalog-danger" onClick={() => onDelete(item.id)}>Delete</button>}
          </label>)}
        </div>
        <p><small>Save any finished draft as a starter with Save as starter. To start from a product already in ERPNext, use Clone existing family.</small></p>
      </section>
      <section className="catalog-clone-step" aria-label="Names">
        <h3>2. Name the product</h3>
        <div className="catalog-new-fields">
          <label>Product code * <input value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. LX20" autoFocus />
            <small>Replaces {starter.code} in every record name and link</small></label>
          <label>Series * <input value={series} onChange={e => setSeries(e.target.value)} list={seriesList} placeholder="e.g. Lumen" />
            <small>{existingSeries.includes(series.trim()) ? 'Existing series: linked, not re-created' : 'A new series record is created unless it exists'}</small></label>
          <label>Product name <input value={name} onChange={e => setName(e.target.value)} placeholder={starter ? defaultName(starter, series.trim() || 'Series') : ''} />
            <small>The template and product name</small></label>
        </div>
        <datalist id={seriesList}>{existingSeries.map(item => <option key={item} value={item} />)}</datalist>
      </section>
      {needed.length > 0 && <section className="catalog-clone-step" aria-label="Existing records">
        <h3>3. Choose existing records</h3>
        <p>The starter links to these placeholders. Pick the ERPNext record to use instead, or leave them to fix later.</p>
        <div className="catalog-new-fields">{needed.map(item => {
          const id = `${item.doctype}\n${item.name}`;
          return <label key={id}>{shortName(item.doctype)} <select value={picks.get(id) || ''}
            onChange={e => setPicks(previous => new Map(previous).set(id, e.target.value))}>
            <option value="">Keep {item.name} (fix later)</option>
            {item.choices.map(choice => <option key={choice}>{choice}</option>)}
          </select></label>;
        })}</div>
      </section>}
      <section className="catalog-clone-step" aria-label="Review">
        <h3>Review</h3>
        {!result ? <p>Enter a product code and series to see the records.</p> : <>
          <p role="status">{plural(result.count, 'record')} to create{result.reused.length ? ` · linking existing ${result.reused.map(row => row.name).join(', ')}` : ''}</p>
          <ul className="catalog-new-counts">{Object.entries(counts).map(([doctype, count]) => <li key={doctype}>{count} {shortName(doctype)}</li>)}</ul>
          {taken.length > 0 && <p className="catalog-replace-conflict">{plural(taken.length, 'name')} already {taken.length === 1 ? 'exists' : 'exist'} in ERPNext:{' '}
            {taken.slice(0, SHOWN).map(row => row.name).join(', ')}{taken.length > SHOWN ? '…' : ''}. Use another product code, or remove those records after creating.</p>}
        </>}
      </section>
    </>}
    <div className="catalog-modal-actions">
      <button onClick={onClose}>Cancel</button>
      <button className="catalog-primary" disabled={!result} onClick={() => { onClose(); onApply(result, values); }}>
        {result ? `Create ${plural(result.count, 'record')}` : 'Create records'}</button>
      <small> Replaces the current {product.label.toLowerCase()} draft; Undo brings it back.</small>
    </div>
  </dialog>;
}

/** Save the current draft as a starter for the next product of this type. */
export function SaveStarterDialog({ catalog, product, onSave, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  useEffect(() => { dialog.current.showModal(); }, []);
  const [label, setLabel] = useState(catalog.series_name ? `${catalog.series_name} ${product.label.toLowerCase()}` : '');
  const [code, setCode] = useState('');
  const [series, setSeries] = useState(catalog.series_name || '');
  const [name, setName] = useState(() => templateName(catalog, schema));
  const records = JSON.stringify(catalog.records);
  const found = code.trim() && records.includes(code.trim());
  const ready = label.trim() && found && series.trim();
  return <dialog ref={dialog} className="catalog-modal catalog-save-starter" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>Save as starter</h2>
    <p>Keep this draft as a starting point for the next {product.label.toLowerCase()} product. New product replaces the code, series
      and name below in every record. Starters are saved in this browser.</p>
    <div className="catalog-new-fields">
      <label>Starter name * <input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Recessed fixture with lens" autoFocus /></label>
      <label>Product code in this draft * <input value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. LX20" />
        <small>{!code.trim() ? 'The code your record names use' : found ? 'Found in this draft' : 'Not found in this draft'}</small></label>
      <label>Series in this draft * <input value={series} onChange={e => setSeries(e.target.value)} /></label>
      <label>Product name in this draft <input value={name} onChange={e => setName(e.target.value)} /></label>
    </div>
    <button onClick={onClose}>Cancel</button>
    <button className="catalog-primary" disabled={!ready} onClick={() => { onClose(); onSave({ label: label.trim(), code, series, name }); }}>Save starter</button>
  </dialog>;
}
