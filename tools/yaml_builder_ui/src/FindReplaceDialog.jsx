import { useEffect, useId, useMemo, useRef, useState } from 'react';
import schema from './catalog-schema.json';
import { findReplace, renameConflicts } from './rename-model.js';

const SHOWN = 300;
const shortName = name => name.replace(/^ilL-/, '');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Find and replace across the draft, with a preview of every change. Renamed records keep their links. */
export default function FindReplaceDialog({ catalog, reference, doctype, onApply, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  const [options, setOptions] = useState({ find: '', replace: '', regex: false, matchCase: true, wholeValue: false, scope: 'names', where: 'all' });
  // Changes whose default (on, or off when they conflict) the user flipped.
  const [flipped, setFlipped] = useState(() => new Set());
  useEffect(() => { dialog.current.showModal(); }, []);
  const set = (field, value) => { setOptions(previous => ({ ...previous, [field]: value })); setFlipped(new Set()); };
  const plan = useMemo(() => {
    try {
      const changes = findReplace(catalog, schema, { ...options, doctypes: options.where === 'current' ? [doctype] : null });
      const names = changes.filter(change => change.kind === 'name');
      const found = renameConflicts(catalog, schema, reference, names);
      const conflicts = new Map(names.map((change, i) => [change.id, found.get(i)]).filter(([, reason]) => reason));
      return { changes, conflicts };
    } catch (error) { return { error: error.message, changes: [], conflicts: new Map() }; }
  }, [catalog, reference, doctype, options]);
  const isOn = change => !plan.conflicts.has(change.id) !== flipped.has(change.id);
  const chosen = plan.changes.filter(isOn);
  const toggle = id => setFlipped(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const records = new Set(plan.changes.map(change => `${change.doctype}|${change.index}`)).size;
  return <dialog ref={dialog} className="catalog-modal catalog-modal-wide" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>Find and replace</h2>
    <p>Renamed records keep their links: every field that links to a renamed record, and every record named from it, is updated too.</p>
    <div className="catalog-replace-form">
      <label>Find <input autoFocus value={options.find} onChange={e => set('find', e.target.value)} placeholder={options.regex ? 'Regular expression, e.g. CH-(\\w+)' : 'Text to find, e.g. CA01'} /></label>
      <label>Replace with <input value={options.replace} onChange={e => set('replace', e.target.value)} placeholder={options.regex ? 'Use $1 for groups' : 'New text'} /></label>
      <fieldset><legend>Search in</legend>
        <label><input type="radio" name={`${title}-scope`} checked={options.scope === 'names'} onChange={() => set('scope', 'names')} /> Record names</label>
        <label><input type="radio" name={`${title}-scope`} checked={options.scope === 'text'} onChange={() => set('scope', 'text')} /> Names and all text fields</label>
      </fieldset>
      <fieldset><legend>DocTypes</legend>
        <label><input type="radio" name={`${title}-where`} checked={options.where === 'all'} onChange={() => set('where', 'all')} /> All</label>
        <label><input type="radio" name={`${title}-where`} checked={options.where === 'current'} onChange={() => set('where', 'current')} /> Only {shortName(doctype)}</label>
      </fieldset>
      <fieldset><legend>Match</legend>
        <label><input type="checkbox" checked={options.matchCase} onChange={e => set('matchCase', e.target.checked)} /> Match case</label>
        <label><input type="checkbox" checked={options.wholeValue} onChange={e => set('wholeValue', e.target.checked)} /> Whole value</label>
        <label><input type="checkbox" checked={options.regex} onChange={e => set('regex', e.target.checked)} /> Regular expression</label>
      </fieldset>
    </div>
    {plan.error ? <p className="catalog-run-errors" role="alert">{plan.error}</p>
      : options.find && <p role="status">{plural(plan.changes.length, 'change')} in {plural(records, 'record')}
        {plan.conflicts.size ? ` · ${plural(plan.conflicts.size, 'rename')} would collide and ${plan.conflicts.size === 1 ? 'is' : 'are'} unchecked` : ''}</p>}
    {plan.changes.length > 0 && <div className="catalog-result-table catalog-replace-preview"><table>
      <thead><tr><th scope="col"><span className="catalog-sr">Include</span></th><th scope="col">Record</th><th scope="col">Field</th><th scope="col">Before → after</th></tr></thead>
      <tbody>{plan.changes.slice(0, SHOWN).map(change => <tr key={change.id} className={plan.conflicts.has(change.id) ? 'has-conflict' : undefined}>
        <td><input type="checkbox" aria-label={`Include ${change.record} ${change.label}`} checked={isOn(change)} onChange={() => toggle(change.id)} /></td>
        <td><small>{shortName(change.doctype)}</small><br />{change.record || `Row ${change.index + 1}`}</td>
        <td>{change.kind === 'name' ? <strong>Name</strong> : change.path}</td>
        <td><del>{change.from}</del> → <ins>{change.to}</ins>{plan.conflicts.has(change.id) && <small className="catalog-replace-conflict">{plan.conflicts.get(change.id)}</small>}</td>
      </tr>)}</tbody>
    </table></div>}
    {plan.changes.length > SHOWN && <p>Showing {SHOWN} of {plan.changes.length}. All checked changes are applied.</p>}
    <button onClick={onClose}>Cancel</button>
    <button className="catalog-primary" disabled={!chosen.length} onClick={() => { onClose(); onApply(chosen); }}>Replace {chosen.length || ''}</button>
  </dialog>;
}
