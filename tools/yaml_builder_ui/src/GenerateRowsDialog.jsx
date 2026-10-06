import { useEffect, useId, useMemo, useRef, useState } from 'react';
import schema from './catalog-schema.json';
import {
  allowedOptions, availableNames, cleanRecipe, generateRows, patternColumns, presetsFor, recipeErrors, savedRecipes, MAX_COMBINATIONS,
} from './generator-model.js';

const SHOWN_ROWS = 150;
const SHOWN_VALUES = 150;
const shortName = name => name.replace(/^ilL-/, '');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const STATUS = { new: 'New', draft: 'Already in the draft', erpnext: 'Exists in ERPNext', repeat: 'Repeats an earlier row', unnamed: 'No record name' };
const sourceTypes = Object.keys(schema.doctypes).filter(name => !schema.doctypes[name].istable)
  .sort((a, b) => Number(!a.startsWith('ilL-Attribute-')) - Number(!b.startsWith('ilL-Attribute-')) || a.localeCompare(b));
const blankRecipe = doctype => ({ doctype, axes: [{ token: 'value', doctype: '', values: [], raw: '' }], fields: {} });
const editable = recipe => ({ ...structuredClone(recipe), axes: recipe.axes.map(axis => ({ doctype: '', ...structuredClone(axis), raw: axis.doctype ? '' : axis.values.join('\n') })) });

/** The values of one axis: typed one per line, or chosen from a DocType's draft and ERPNext records. */
function AxisValues({ axis, index, catalog, reference, onChange }) {
  const [query, setQuery] = useState('');
  if (!axis.doctype) {
    return <textarea aria-label={`Axis ${index + 1} values, one per line`} rows={3} value={axis.raw}
      placeholder={'One value per line, e.g.\n24V\n48V'}
      onChange={e => onChange({ ...axis, raw: e.target.value, values: [...new Set(e.target.value.split('\n').map(line => line.trim()).filter(Boolean))] })} />;
  }
  const names = availableNames(axis.doctype, catalog, reference, schema);
  const own = new Set(availableNames(axis.doctype, { records: { [axis.doctype]: catalog.records[axis.doctype] || [] } }, null, schema));
  const needle = query.trim().toLowerCase();
  const shown = names.filter(name => !needle || name.toLowerCase().includes(needle));
  const chosen = new Set(axis.values);
  const optionType = axis.doctype.startsWith('ilL-Attribute-') ? axis.doctype.slice(14) : null;
  const allowed = optionType ? allowedOptions(catalog, schema, optionType) : [];
  const set = values => onChange({ ...axis, values });
  return <div className="catalog-generate-values">
    <div className="catalog-generate-value-tools">
      <input aria-label={`Search axis ${index + 1} values`} placeholder={`Find ${shortName(axis.doctype)}…`} value={query} onChange={e => setQuery(e.target.value)} />
      <span>{axis.values.length} of {names.length} chosen</span>
      <button type="button" onClick={() => set([...new Set([...axis.values, ...shown])])}>Choose shown</button>
      <button type="button" onClick={() => set(axis.values.filter(value => !shown.includes(value)))}>Clear shown</button>
      {allowed.length > 0 && <button type="button" onClick={() => set(allowed)} title="The values the draft's templates allow">Allowed in templates ({allowed.length})</button>}
    </div>
    <div className="catalog-generate-checklist">
      {shown.slice(0, SHOWN_VALUES).map(name => <label key={name}>
        <input type="checkbox" checked={chosen.has(name)} onChange={e => set(e.target.checked ? [...axis.values, name] : axis.values.filter(value => value !== name))} />
        {name}{own.has(name) && <small> · draft</small>}</label>)}
      {!names.length && <p>No {shortName(axis.doctype)} records in the draft or ERPNext.</p>}
    </div>
    {shown.length > SHOWN_VALUES && <p><small>Showing {SHOWN_VALUES} of {shown.length}. Search to find more.</small></p>}
  </div>;
}

/**
 * Generate rows for one DocType from every combination of axis values, filling fields from
 * patterns. Presets start from the draft's templates and options; recipes save in the draft.
 */
export default function GenerateRowsDialog({ doctype, catalog, reference, onApply, onSaveRecipe, onDeleteRecipe, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  const presets = useMemo(() => presetsFor(doctype, catalog, reference, schema), [doctype]); // eslint-disable-line react-hooks/exhaustive-deps
  const saved = savedRecipes(catalog, doctype);
  const [source, setSource] = useState(() => (presets[0] ? `preset:${presets[0].id}` : 'blank'));
  const [recipe, setRecipe] = useState(() => (presets[0] ? editable(presets[0].recipe) : blankRecipe(doctype)));
  const [allFields, setAllFields] = useState(false);
  const [skipped, setSkipped] = useState(() => new Set());
  const [name, setName] = useState('');
  useEffect(() => { dialog.current.showModal(); }, []);
  const columns = useMemo(() => patternColumns(doctype, schema), [doctype]);
  const update = next => { setRecipe(next); setSkipped(new Set()); };
  const load = value => {
    setSource(value);
    const [kind, id] = [value.slice(0, value.indexOf(':')), value.slice(value.indexOf(':') + 1)];
    if (kind === 'preset') update(editable(presets.find(item => item.id === id).recipe));
    else if (kind === 'saved') { update(editable(saved.find(item => item.name === id))); setName(id); }
    else update(blankRecipe(doctype));
  };
  const setAxis = (i, axis) => update({ ...recipe, axes: recipe.axes.map((item, at) => at === i ? axis : item) });
  const errors = recipeErrors(recipe);
  const rows = useMemo(() => generateRows(recipe, { catalog, reference, schema }), [recipe, catalog, reference]);
  const counts = rows.reduce((total, row) => ({ ...total, [row.status]: (total[row.status] || 0) + 1 }), {});
  const unknown = [...new Set(rows.flatMap(row => row.unknown))];
  const missing = rows.filter(row => row.missing.length);
  const chosen = rows.map((row, i) => [row, i]).filter(([row, i]) => row.status === 'new' && !skipped.has(i)).map(([row]) => row.row);
  const shownColumns = columns.filter(column => allFields || column.reqd || column.pinned || String(recipe.fields[column.key] ?? '').trim());
  const previewColumns = columns.filter(column => String(recipe.fields[column.key] ?? '').trim()).slice(0, 5);
  const combinations = recipe.axes.reduce((total, axis) => total * axis.values.length, 1);
  const preset = source.startsWith('preset:') ? presets.find(item => `preset:${item.id}` === source) : null;
  const tokens = recipe.axes.filter(axis => axis.token).map(axis => `{${axis.token}}`);

  return <dialog ref={dialog} className="catalog-modal catalog-modal-wide catalog-generate" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>Generate {shortName(doctype)} rows</h2>
    <p>Every combination of the axes' values becomes one row. Fill fields with patterns: <code>{'{style}'}</code> is the style axis's value,
      and <code>{'{style.code}'}</code> reads that record's code. Dotted fields follow links, as in <code>{'{pair.endcap_color.code}'}</code>.</p>
    <label className="catalog-generate-source">Start from <select value={source} onChange={e => load(e.target.value)}>
      <option value="blank">Blank recipe</option>
      {presets.length > 0 && <optgroup label="Presets from this draft">{presets.map(item => <option key={item.id} value={`preset:${item.id}`}>{item.label}</option>)}</optgroup>}
      {saved.length > 0 && <optgroup label="Saved recipes">{saved.map(item => <option key={item.name} value={`saved:${item.name}`}>{item.name}</option>)}</optgroup>}
    </select></label>
    {preset && <p><small>{preset.description}</small></p>}

    <section className="catalog-clone-step" aria-label="Axes">
      <h3>Axes <small>{combinations} {combinations === 1 ? 'combination' : 'combinations'}</small></h3>
      {recipe.axes.map((axis, i) => <div className="catalog-generate-axis" key={i}>
        <div className="catalog-generate-axis-head">
          <label>Name <input aria-label={`Axis ${i + 1} name`} value={axis.token} onChange={e => setAxis(i, { ...axis, token: e.target.value.trim() })} /></label>
          <label>Values from <select aria-label={`Axis ${i + 1} source`} value={axis.doctype}
            onChange={e => setAxis(i, { ...axis, doctype: e.target.value, values: [], raw: '' })}>
            <option value="">Typed values</option>
            {sourceTypes.map(item => <option key={item} value={item}>{shortName(item)}</option>)}
          </select></label>
          <button type="button" aria-label={`Remove axis ${i + 1}`} onClick={() => update({ ...recipe, axes: recipe.axes.filter((_, at) => at !== i) })}>Remove</button>
        </div>
        <AxisValues axis={axis} index={i} catalog={catalog} reference={reference} onChange={next => setAxis(i, next)} />
      </div>)}
      <button type="button" onClick={() => update({ ...recipe, axes: [...recipe.axes, { token: `axis${recipe.axes.length + 1}`, doctype: '', values: [], raw: '' }] })}>+ Add axis</button>
    </section>

    <section className="catalog-clone-step" aria-label="Field patterns">
      <h3>Field patterns</h3>
      <p><small>Tokens: {tokens.join(' ') || 'add an axis first'}. Text without tokens is the same for every row; leave a field empty to use its default.</small></p>
      <div className="catalog-generate-fields">
        {shownColumns.map(column => <label key={column.key}>
          <span>{column.label}{column.reqd ? ' *' : ''} <small>{column.key}</small></span>
          <input value={recipe.fields[column.key] ?? ''} placeholder={column.fieldtype === 'Select' ? String(column.options || '').split('\n').filter(Boolean).slice(0, 3).join(' | ') : column.fieldtype === 'Check' ? '1 or 0' : ''}
            onChange={e => update({ ...recipe, fields: { ...recipe.fields, [column.key]: e.target.value } })} />
        </label>)}
      </div>
      <label className="catalog-clone-option"><input type="checkbox" checked={allFields} onChange={e => setAllFields(e.target.checked)} /> Show all {columns.length} fields</label>
    </section>

    <section className="catalog-clone-step" aria-label="Preview">
      <h3>Preview</h3>
      {errors.length > 0 ? <p className="catalog-run-errors" role="alert">{errors.join('. ')}.</p> : <p role="status">
        {plural(counts.new || 0, 'new row')}
        {['draft', 'erpnext', 'repeat', 'unnamed'].filter(status => counts[status]).map(status => ` · ${counts[status]} ${STATUS[status].toLowerCase()}`).join('')}
        {skipped.size ? ` · ${skipped.size} unchecked` : ''}</p>}
      {unknown.length > 0 && <p className="catalog-run-errors">No axis is named {unknown.map(token => `{${token}}`).join(', ')}.</p>}
      {missing.length > 0 && <p className="catalog-replace-conflict">{plural(missing.length, 'row')} had empty values for {[...new Set(missing.flatMap(row => row.missing))].map(path => `{${path}}`).join(', ')}.</p>}
      {rows.length > 0 && <div className="catalog-result-table catalog-replace-preview"><table>
        <thead><tr><th scope="col"><span className="catalog-sr">Add</span></th><th scope="col">Record</th><th scope="col">Status</th>
          {previewColumns.map(column => <th scope="col" key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>{rows.slice(0, SHOWN_ROWS).map((row, i) => <tr key={i} className={row.status === 'new' ? undefined : 'is-muted'}>
          <td>{row.status === 'new' && <input type="checkbox" aria-label={`Add ${row.name || `row ${i + 1}`}`} checked={!skipped.has(i)}
            onChange={() => setSkipped(previous => { const next = new Set(previous); if (next.has(i)) next.delete(i); else next.add(i); return next; })} />}</td>
          <td>{row.name || <small>Row {i + 1}</small>}</td>
          <td><small>{STATUS[row.status]}{row.missing.length ? ` · empty ${row.missing.map(path => `{${path}}`).join(', ')}` : ''}</small></td>
          {previewColumns.map(column => <td key={column.key}>{String(row.row[column.key] ?? '')}</td>)}
        </tr>)}</tbody>
      </table></div>}
      {rows.length > SHOWN_ROWS && <p>Showing {SHOWN_ROWS} of {rows.length}. Every checked new row is added.</p>}
      <p><small>Up to {MAX_COMBINATIONS} combinations. Rows whose names already exist are never added.</small></p>
    </section>

    <section className="catalog-clone-step catalog-generate-save" aria-label="Save recipe">
      <label>Save as recipe <input value={name} onChange={e => setName(e.target.value)} placeholder="Recipe name" /></label>
      <button type="button" disabled={!name.trim() || errors.length > 0} title="Saved in this draft, so Save draft and Open YAML carry it"
        onClick={() => { onSaveRecipe(cleanRecipe(recipe, name.trim())); setSource(`saved:${name.trim()}`); }}>Save recipe</button>
      {source.startsWith('saved:') && <button type="button" className="catalog-danger"
        onClick={() => { onDeleteRecipe(source.slice(6)); setSource('blank'); }}>Delete saved recipe</button>}
    </section>
    <div className="catalog-modal-actions">
      <button onClick={onClose}>Cancel</button>
      <button className="catalog-primary" disabled={!chosen.length || errors.length > 0 || unknown.length > 0} onClick={() => { onClose(); onApply(chosen, rows.length - chosen.length); }}>
        Add {plural(chosen.length, 'row')}</button>
    </div>
  </dialog>;
}
