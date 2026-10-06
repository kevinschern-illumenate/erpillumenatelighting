import { createContext, memo, useContext, useEffect, useId, useMemo, useRef, useState } from 'react';
import schema from './catalog-schema.json';
import { blankRecord, recordName, inReference, referenceSummary } from './catalog-model.js';
import { RecordFields } from './RecordFields.jsx';
import { namingField } from './rename-model.js';
import {
  gridColumns, visibleColumns, filledCount, defaultWidth, parseTSV, toTSV, parseNumber, rangeBounds, copyMatrix,
  pasteCells, rowsFromMatrix, fillDown, clearCells, insertAfter, duplicateRows, removeRows, moveRows, setField,
  NUMERIC_TYPES, LONG_TEXT_TYPES,
} from './grid-model.js';

/** Catalog-wide data every grid (including nested child-table grids) reads. */
export const GridData = createContext({ catalog: { records: {}, external_links: {} }, reference: null, issues: null, undo() {}, redo() {} });

const PREFS = 'illumenate-grid-columns-v1';
const ROW_HEAD = 92;
const count = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const EMPTY_ISSUES = { cells: new Map(), under: new Set(), rows: new Map() };

function readPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS));
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  } catch { return {}; }
}

/** Column choices per DocType, remembered in this browser. */
function useColumnPrefs(doctype) {
  const [prefs, setPrefs] = useState(() => readPrefs()[doctype] || {});
  const save = next => {
    setPrefs(next);
    try { localStorage.setItem(PREFS, JSON.stringify({ ...readPrefs(), [doctype]: next })); } catch { /* Column choices are a convenience. */ }
  };
  return [prefs, save, setPrefs];
}

// Existing ERPNext records can number in the thousands, so their picker options are built once per export.
const referenceOptions = new WeakMap();
function existingOptions(target, entry) {
  if (!entry) return new Map();
  if (!referenceOptions.has(entry)) {
    referenceOptions.set(entry, new Map(Object.entries(entry.records).map(([name, record]) =>
      [name, `ERPNext · ${referenceSummary(target, record, schema, 3)}`])));
  }
  return referenceOptions.get(entry);
}

/** One shared suggestion list per linked DocType, instead of one per cell. */
const LinkList = memo(function LinkList({ id, target, local, reference }) {
  const existing = existingOptions(target, reference?.doctypes?.[target]);
  const names = local ? local.split('\n') : [];
  const own = new Set(names);
  return <datalist id={id}>
    {names.map(name => <option key={name} value={name} label={existing.get(name)} />)}
    {[...existing].filter(([name]) => !own.has(name)).map(([name, label]) => <option key={name} value={name} label={label} />)}
  </datalist>;
});

/** Numbers keep what is typed ("1.50", "2.") while focused and store the parsed value. */
function NumberCell({ value, onEdit, ...props }) {
  const [draft, setDraft] = useState(null);
  const shown = draft && draft.value === value ? draft.text : (value ?? '');
  return <input {...props} type="text" inputMode="decimal" value={typeof shown === 'object' ? JSON.stringify(shown) : shown}
    onChange={e => { const parsed = parseNumber(e.target.value); setDraft({ text: e.target.value, value: parsed === '' ? undefined : parsed }); onEdit(parsed); }}
    onBlur={() => setDraft(null)} />;
}

function linkTarget(column, row) {
  return column.fieldtype === 'Dynamic Link' ? row?.[column.options] : column.options;
}

function Cell({ grid, doctype, row, index, r, c, column, selected, active, issues, path, lists, reference, open, actions }) {
  const key = column.key;
  const value = row?.[key];
  const label = `${column.label}, row ${index + 1}`;
  const location = `${path}[${index}].${key}`;
  const messages = issues.cells.get(location) || [];
  const classes = ['grid-cell'];
  if (column.pinned) classes.push('grid-pinned');
  if (selected) classes.push('is-selected');
  if (active) classes.push('is-active');
  let title = messages.join('\n');
  let control;
  if (column.kind === 'computed') {
    control = <input type="text" readOnly aria-label={label} value={recordName(doctype, row || {}, schema)} />;
    classes.push('is-computed');
  } else if (column.kind === 'table') {
    const size = Array.isArray(value) ? value.length : 0;
    const flagged = issues.under.has(location);
    if (flagged) title = title || 'Child rows have findings. Open the table to review them.';
    control = <button type="button" className={`grid-child ${flagged ? 'has-issue' : ''}`} aria-label={`${label}: ${count(size, 'row')}`}
      aria-expanded={open} onClick={() => actions.toggleOpen(index, key)}>
      {value !== undefined && !Array.isArray(value) ? 'Invalid' : count(size, 'row')} <span aria-hidden="true">{open ? '▾' : '▸'}</span>
    </button>;
  } else if (column.fieldtype === 'Check') {
    control = <input type="checkbox" aria-label={label} checked={Boolean(value) && value !== '0'} onChange={e => actions.edit(index, key, e.target.checked ? 1 : 0)} />;
    classes.push('is-check');
  } else if (column.fieldtype === 'Select') {
    const choices = String(column.options || '').split('\n').filter(Boolean);
    const text = value === undefined || value === null ? '' : String(value);
    control = <select aria-label={label} value={text} onChange={e => actions.edit(index, key, e.target.value)}>
      <option value="">—</option>
      {text && !choices.includes(text) && <option value={text}>{text} (unsupported)</option>}
      {choices.map(choice => <option key={choice}>{choice}</option>)}
    </select>;
  } else if (LONG_TEXT_TYPES.has(column.fieldtype)) {
    control = <textarea rows={1} aria-label={label} value={value && typeof value === 'object' ? JSON.stringify(value) : (value ?? '')}
      onChange={e => actions.edit(index, key, e.target.value)} />;
  } else if (NUMERIC_TYPES.has(column.fieldtype)) {
    control = <NumberCell aria-label={label} value={value} onEdit={next => actions.edit(index, key, next)} />;
    classes.push('is-number');
  } else {
    const target = ['Link', 'Dynamic Link'].includes(column.fieldtype) ? linkTarget(column, row) : null;
    if (target && value !== undefined && value !== '' && inReference(reference, target, String(value))) {
      classes.push('is-existing');
      const summary = referenceSummary(target, reference.doctypes[target].records[String(value)], schema);
      title = title || `Existing ERPNext record${summary ? ` · ${summary}` : ''}`;
    }
    control = <input type="text" aria-label={label} list={target && lists[target] ? lists[target] : undefined}
      value={value && typeof value === 'object' ? JSON.stringify(value) : (value ?? '')}
      onChange={e => actions.edit(index, key, e.target.value)} />;
  }
  if (messages.length) classes.push('has-issue');
  return <td data-grid={grid} data-r={r} data-c={c} className={classes.join(' ')} title={title || undefined}>{control}</td>;
}

function RowForm({ doctype, row, top, number, onChange, onClose }) {
  const { catalog, reference } = useContext(GridData);
  return <div className="grid-form">
    <div className="grid-expand-title"><strong>Row {number} · all fields with descriptions</strong><button type="button" onClick={onClose}>Close</button></div>
    <RecordFields doctype={doctype} row={row && typeof row === 'object' ? row : {}} catalog={catalog} reference={reference} depth={top ? 0 : 1} onChange={onChange} />
  </div>;
}

const GridRow = memo(function GridRow(props) {
  const { grid, doctype, row, index, r, columns, sel, active, checked, open, issues, path, top, actions, rowIdPrefix, childFocus } = props;
  const [left, right] = sel ? sel.split(':').map(Number) : [-1, -2];
  const openKeys = open ? open.split('|') : [];
  const findings = issues.rows.get(`${path}[${index}]`) || [];
  return <>
    <tr className={`${checked ? 'is-checked' : ''} ${findings.length ? 'has-issue' : ''}`}>
      <th scope="row" className="grid-rowhead" title={findings.join('\n') || undefined}
        id={rowIdPrefix ? `${rowIdPrefix}${index}` : undefined} tabIndex={rowIdPrefix ? -1 : undefined}>
        <input type="checkbox" tabIndex={-1} aria-label={`Select row ${index + 1}`} checked={checked}
          onChange={e => actions.toggleCheck(index, e.nativeEvent.shiftKey)} />
        <button type="button" tabIndex={-1} className="grid-rownum" title="Select the row's cells (Shift extends)"
          onClick={e => actions.selectRow(r, e.shiftKey)}>{index + 1}{findings.length ? <span className="grid-flag">{findings.length}</span> : null}</button>
        <button type="button" tabIndex={-1} className="grid-open" aria-pressed={openKeys.includes('__form')} title="Show this row as a form"
          aria-label={`Show row ${index + 1} as a form`} onClick={() => actions.toggleOpen(index, '__form')}>⤢</button>
      </th>
      {columns.map((column, c) => <Cell key={column.key} grid={grid} doctype={doctype} row={row} index={index} r={r} c={c} column={column}
        selected={c >= left && c <= right} active={c === active} issues={issues} path={path} lists={props.lists}
        reference={props.reference} open={openKeys.includes(column.key)} actions={actions} />)}
    </tr>
    {openKeys.map(key => {
      const column = columns.find(item => item.key === key);
      return <tr className="grid-expand" key={key}><td colSpan={columns.length + 1}><div className="grid-expand-inner">
        {key === '__form'
          ? <RowForm doctype={doctype} row={row} top={top} number={index + 1} onChange={next => actions.replaceRow(index, next)} onClose={() => actions.toggleOpen(index, key)} />
          : column && <>
            <div className="grid-expand-title"><strong>{column.label} · row {index + 1}</strong>
              <button type="button" onClick={() => actions.toggleOpen(index, key)}>Close</button></div>
            {row?.[key] !== undefined && !Array.isArray(row[key]) && <p role="alert">Invalid child table. Adding rows replaces it.</p>}
            <RecordGrid doctype={column.options} rows={Array.isArray(row?.[key]) ? row[key] : []} path={`${path}[${index}].${key}`} top={false}
              focus={childFocus?.key === key ? childFocus.focus : null}
              onChange={(rows, change) => actions.replaceRow(index, setField(row, key, rows.length ? rows : ''), change)} />
          </>}
      </div></td></tr>;
    })}
  </>;
}, (a, b) => Object.keys(b).every(key => key === 'issues' ? a.issueSig === b.issueSig : a[key] === b[key]));

/** Closes a <details> menu when the pointer goes down elsewhere. */
function Menu({ label, className = '', children }) {
  const ref = useRef(null);
  useEffect(() => {
    const close = event => { if (ref.current?.open && !ref.current.contains(event.target)) ref.current.open = false; };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);
  return <details ref={ref} className={`grid-menu ${className}`}><summary>{label}</summary><div className="grid-menu-panel">{children}</div></details>;
}

const SHORTCUTS = [
  ['Tab / Shift+Tab', 'Next / previous cell'], ['Arrows', 'Move between cells (inside text, at its start or end)'],
  ['Enter / Shift+Enter', 'Move down / up'], ['Shift+Arrows, Shift+click, drag', 'Select a block of cells'],
  ['Click a header or row number', 'Select a column or row'], ['Ctrl+C / Ctrl+X / Ctrl+V', 'Copy, cut and paste blocks (works with Excel and Google Sheets)'],
  ['Paste one value into a block', 'Fills every selected cell'], ['Ctrl+D', 'Fill down from the top selected row'],
  ['Delete', 'Clear the selected cells'], ['Ctrl+Z / Ctrl+Y', 'Undo / redo'], ['F2', 'Edit the text in a cell'],
  ['Alt+Enter', 'New line in a long text cell'], ['Esc', 'Select just the current cell'],
  ['Edit a record name', 'Links to it follow when you leave the cell'], ['Ctrl+H', 'Find and replace across the draft'],
];

/**
 * Spreadsheet view of records: one row per record, one column per field. Child
 * tables open as nested grids under their row. `onChange(rows, change)` receives
 * every edit; `change.label` names it for undo, `change.key` groups typing in one cell.
 */
/**
 * `focus` ({ index, rest, nonce }) moves to a row, or to the field `rest` names inside
 * it ("field" or "childTable[2].field"), opening child tables and hidden columns on the way.
 * `onRename(from, to, key)` runs when focus leaves an edited record name, so links can follow.
 */
export function RecordGrid({ doctype, rows, onChange, path = doctype, top = true, columnFilter = '', copyRow, rowIdPrefix = '', focus = null, onRename = null }) {
  const { reference, issues = EMPTY_ISSUES, undo, redo, catalog } = useContext(GridData);
  const grid = `g${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const wrap = useRef(null);
  const [prefs, savePrefs, setPrefs] = useColumnPrefs(doctype);
  const [sel, setSel] = useState(null);
  const [checked, setChecked] = useState(() => new Set());
  const [open, setOpen] = useState(() => new Set());
  const [rowFilter, setRowFilter] = useState('');
  const [status, setStatus] = useState('');
  const [width, setWidth] = useState(null);
  const pendingFocus = useRef(false);
  const drag = useRef(false);
  const lastChecked = useRef(null);
  const afterRender = useRef(null);
  const focusRequest = useRef(null);
  const seenFocus = useRef(null);
  const [childFocus, setChildFocus] = useState(null);
  if (focus && focus.nonce !== seenFocus.current) {
    seenFocus.current = focus.nonce;
    focusRequest.current = focus;
  }
  const actions = useRef({}).current;
  const index = issues || EMPTY_ISSUES;
  const naming = top && onRename ? namingField(doctype, schema) : null;
  // The record name when its cell gained focus, to rename links once editing ends.
  const nameEdit = useRef(null);

  const readOnlyPresent = schema.doctypes[doctype].fields
    .filter(field => field.read_only && rows.some(row => row && Object.hasOwn(row, field.fieldname))).map(field => field.fieldname).join();
  const all = useMemo(() => gridColumns(doctype, schema, rows, top), [doctype, top, readOnlyPresent]); // eslint-disable-line react-hooks/exhaustive-deps
  const hidden = Array.isArray(prefs.hidden) ? prefs.hidden : [];
  const visible = visibleColumns(all, rows, { dataOnly: Boolean(prefs.dataOnly), hidden, filter: columnFilter });
  // Keep the same column array while the visible set is unchanged, so unchanged rows skip rendering.
  const stable = useRef(null);
  const keys = visible.map(column => column.key).join('|');
  if (!stable.current || stable.current.keys !== keys || stable.current.all !== all) stable.current = { keys, all, columns: visible };
  const cols = stable.current.columns;
  const widthOf = column => prefs.widths?.[column.key] || defaultWidth(column);

  const needle = rowFilter.trim().toLowerCase();
  const order = useMemo(() => rows.map((_, i) => i).filter(i => !needle
    || `${top ? recordName(doctype, rows[i] || {}, schema) : ''} ${JSON.stringify(rows[i])}`.toLowerCase().includes(needle)), [rows, needle, doctype, top]);
  const clamped = sel && order.length && cols.length ? {
    ar: Math.min(sel.ar, order.length - 1), fr: Math.min(sel.fr, order.length - 1),
    ac: Math.min(sel.ac, cols.length - 1), fc: Math.min(sel.fc, cols.length - 1),
  } : null;
  const bounds = rangeBounds(clamped);
  const multi = Boolean(bounds && (bounds.top !== bounds.bottom || bounds.left !== bounds.right));
  const targetRows = checked.size ? [...checked].filter(i => i < rows.length).sort((a, b) => a - b)
    : bounds ? order.slice(bounds.top, bounds.bottom + 1) : [];

  // Suggestion lists for every linked DocType in view.
  const targets = new Set();
  for (const column of cols) {
    if (column.fieldtype === 'Link') targets.add(column.options);
    if (column.fieldtype === 'Dynamic Link') rows.forEach(row => row?.[column.options] && targets.add(row[column.options]));
  }
  const targetList = [...targets].filter(Boolean).sort();
  const lists = useMemo(() => Object.fromEntries(targetList.map((target, i) => [target, `${grid}-list-${i}`])), [grid, targetList.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps
  const localNames = target => [...new Set([...(catalog.records[target] || []).map(row => recordName(target, row, schema)),
    ...(catalog.external_links?.[target] || [])])].filter(Boolean).join('\n');

  useEffect(() => {
    if (!wrap.current || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => setWidth(wrap.current?.clientWidth || null));
    observer.observe(wrap.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const stop = () => { drag.current = false; };
    window.addEventListener('mouseup', stop);
    return () => window.removeEventListener('mouseup', stop);
  }, []);
  useEffect(() => {
    if (afterRender.current) {
      const { r, c } = afterRender.current;
      afterRender.current = null;
      move(r, c, false);
    }
    const request = focusRequest.current;
    if (!request) return;
    const r = order.indexOf(request.index);
    if (r < 0) {
      // A row filter may hide the row; clear it and try again after rendering.
      if (needle && request.index < rows.length) setRowFilter(''); else focusRequest.current = null;
      return;
    }
    const target = /^([^.[]+)(?:\[(\d+)\](?:\.(.*))?)?$/.exec(request.rest || '');
    const key = target?.[1];
    const c = key ? cols.findIndex(column => column.key === key) : -1;
    if (key && c < 0 && all.some(column => column.key === key) && (hidden.includes(key) || prefs.dataOnly)) {
      savePrefs({ ...prefs, hidden: hidden.filter(item => item !== key), dataOnly: false });
      setStatus(`Showing the ${all.find(column => column.key === key).label} column.`);
      return;
    }
    focusRequest.current = null;
    if (c < 0) {
      if (key && all.some(column => column.key === key)) setStatus(`Clear the column search to see ${all.find(column => column.key === key).label}.`);
      move(r, 0, false);
      return;
    }
    if (target[2] !== undefined && cols[c].kind === 'table') {
      setOpen(previous => new Set(previous).add(`${request.index}|${key}`));
      setChildFocus({ row: request.index, key, focus: { index: Number(target[2]), rest: target[3] || '', nonce: request.nonce } });
    }
    move(r, c, false);
  });

  const commit = (next, label, message = '') => {
    onChange(next, { label });
    setStatus(message);
  };
  const cellCount = b => (b.bottom - b.top + 1) * (b.right - b.left + 1);

  function focusCell(r, c, { selectText = true, scroll = true } = {}) {
    const td = wrap.current?.querySelector(`td[data-grid="${grid}"][data-r="${r}"][data-c="${c}"]`);
    const control = td?.querySelector('input, select, textarea, button');
    if (!control) return;
    pendingFocus.current = true;
    control.focus({ preventScroll: true });
    pendingFocus.current = false;
    if (selectText && control.select && control.type !== 'checkbox') control.select();
    if (scroll) td.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  function move(r, c, extend) {
    if (!order.length || !cols.length) return;
    const row = Math.max(0, Math.min(order.length - 1, r));
    const column = Math.max(0, Math.min(cols.length - 1, c));
    setSel(extend && clamped ? { ...clamped, fr: row, fc: column } : { ar: row, ac: column, fr: row, fc: column });
    focusCell(row, column, { selectText: !extend });
  }
  function ownCell(target) {
    const td = target?.closest?.('td[data-grid]');
    return td && td.dataset.grid === grid ? td : null;
  }

  Object.assign(actions, {
    edit(i, key, value) {
      onChange(rows.map((row, at) => at === i ? setField(row, key, value) : row), { label: 'Edit cell', key: `${path}[${i}].${key}` });
    },
    replaceRow(i, next, change = { label: 'Edit row', key: `${path}[${i}]` }) {
      onChange(rows.map((row, at) => at === i ? next : row), change);
    },
    toggleOpen(i, key) {
      setOpen(previous => {
        const next = new Set(previous);
        const id = `${i}|${key}`;
        if (next.has(id)) next.delete(id); else next.add(id);
        return next;
      });
    },
    toggleCheck(i, shift) {
      setChecked(previous => {
        const next = new Set(previous);
        const on = !previous.has(i);
        const from = shift && lastChecked.current !== null ? order.indexOf(lastChecked.current) : -1;
        const to = order.indexOf(i);
        const span = from >= 0 && to >= 0 ? order.slice(Math.min(from, to), Math.max(from, to) + 1) : [i];
        span.forEach(at => (on ? next.add(at) : next.delete(at)));
        return next;
      });
      lastChecked.current = i;
    },
    selectRow(r, shift) {
      setSel({ ar: shift && clamped ? clamped.ar : r, ac: 0, fr: r, fc: cols.length - 1 });
      focusCell(r, 0, { selectText: false, scroll: false });
    },
  });

  function selectColumn(c, shift) {
    if (!order.length) return;
    setSel({ ar: 0, ac: shift && clamped ? clamped.ac : c, fr: order.length - 1, fc: c });
    focusCell(0, c, { selectText: false, scroll: false });
  }
  function fill() {
    if (!bounds) return;
    const result = fillDown(rows, order, cols, bounds);
    if (!result.written) { setStatus('Select the row to copy and the rows below it, then fill down.'); return; }
    commit(result.rows, 'Fill down', `Filled ${count(result.written, 'cell')} down.`);
  }
  function clear() {
    if (!bounds) return;
    const result = clearCells(rows, order, cols, bounds);
    commit(result.rows, 'Clear cells', `Cleared ${count(result.written, 'cell')}.`);
  }
  function rowOp(kind, direction = 0) {
    const label = { duplicate: 'Duplicate rows', insert: 'Insert row', delete: 'Delete rows', move: 'Move rows' }[kind];
    let next;
    let selectAfter = [];
    if (kind === 'duplicate') {
      const result = duplicateRows(rows, targetRows, copyRow || structuredClone);
      next = result.rows; selectAfter = result.inserted;
      setStatus(`Duplicated ${count(targetRows.length, 'row')}${copyRow ? '; give each copy a new name' : ''}.`);
    } else if (kind === 'insert') {
      const result = insertAfter(rows, targetRows, [blankRecord(doctype, schema)]);
      next = result.rows; selectAfter = result.inserted;
      setStatus('Inserted a row.');
    } else if (kind === 'delete') {
      next = removeRows(rows, targetRows);
      setStatus(`Deleted ${count(targetRows.length, 'row')}. Ctrl+Z restores ${targetRows.length === 1 ? 'it' : 'them'}.`);
    } else {
      const result = moveRows(rows, targetRows, direction);
      next = result.rows; selectAfter = result.indexes;
      setStatus('');
    }
    onChange(next, { label });
    setChecked(new Set(selectAfter));
    setSel(null);
    setOpen(new Set());
  }
  function addRows(amount) {
    const result = insertAfter(rows, [], Array.from({ length: amount }, () => blankRecord(doctype, schema)));
    commit(result.rows, amount === 1 ? 'Add row' : `Add ${amount} rows`);
    if (!needle) afterRender.current = { r: result.inserted[0], c: 0 };
  }
  async function copyTable() {
    const matrix = [cols.map(column => column.label),
      ...copyMatrix(rows, order, cols, { top: 0, bottom: order.length - 1, left: 0, right: cols.length - 1 }, doctype, schema)];
    try {
      await navigator.clipboard.writeText(toTSV(matrix));
      setStatus(`Copied ${count(order.length, 'row')} with headers. Edit them in a spreadsheet and use Paste rows to add rows back.`);
    } catch { setStatus('The browser blocked clipboard access. Select cells and press Ctrl+C instead.'); }
  }
  async function pasteRows() {
    let text;
    try { text = await navigator.clipboard.readText(); } catch {
      setStatus('The browser blocked clipboard access. Add a row, click its first cell and press Ctrl+V instead.');
      return;
    }
    const result = rowsFromMatrix(parseTSV(text), all, cols, () => blankRecord(doctype, schema));
    if (!result.rows.length) { setStatus('The clipboard has no rows to add.'); return; }
    commit([...rows, ...result.rows], `Paste ${result.rows.length} rows`, `Added ${count(result.rows.length, 'row')}${result.header ? ', matching columns by header' : ' in the order of the visible columns'}`
      + `${result.skipped ? `; skipped ${count(result.skipped, 'value')} that did not fit their column` : ''}.`);
  }

  function onFocus(event) {
    const td = ownCell(event.target);
    if (!td) return;
    const r = Number(td.dataset.r);
    const c = Number(td.dataset.c);
    if (naming && cols[c]?.key === naming && nameEdit.current?.index !== order[r]) {
      nameEdit.current = { index: order[r], from: recordName(doctype, rows[order[r]] || {}, schema) };
    }
    if (pendingFocus.current) return;
    setSel(previous => previous && previous.ar === r && previous.ac === c && previous.fr === r && previous.fc === c
      ? previous : { ar: r, ac: c, fr: r, fc: c });
  }
  function onBlur(event) {
    const edit = nameEdit.current;
    const td = ownCell(event.target);
    if (!edit || !td || td.contains(event.relatedTarget)) return;
    nameEdit.current = null;
    const to = recordName(doctype, rows[edit.index] || {}, schema);
    if (edit.from && to && to !== edit.from) onRename(edit.from, to, `${path}[${edit.index}].${naming}`);
  }
  function onMouseDown(event) {
    const td = ownCell(event.target);
    if (!td || event.button !== 0) return;
    if (event.shiftKey && clamped) {
      event.preventDefault();
      setSel({ ...clamped, fr: Number(td.dataset.r), fc: Number(td.dataset.c) });
      return;
    }
    drag.current = true;
  }
  function onMouseOver(event) {
    if (!drag.current) return;
    if (!(event.buttons & 1)) { drag.current = false; return; }
    const td = ownCell(event.target);
    if (!td) return;
    const r = Number(td.dataset.r);
    const c = Number(td.dataset.c);
    setSel(previous => previous && (previous.fr !== r || previous.fc !== c) ? { ...previous, fr: r, fc: c } : previous);
  }
  function onKeyDown(event) {
    if (event.defaultPrevented) return;
    const td = ownCell(event.target);
    if (!td) return;
    const r = Number(td.dataset.r);
    const c = Number(td.dataset.c);
    const el = event.target;
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      const letter = key.toLowerCase();
      if (letter === 'z') { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      else if (letter === 'y') { event.preventDefault(); redo(); }
      else if (letter === 'd') { event.preventDefault(); fill(); }
      return;
    }
    const textual = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type === 'text');
    const text = textual ? el.value : '';
    const start = textual ? el.selectionStart : 0;
    const end = textual ? el.selectionEnd : 0;
    // Text that is empty or fully selected (as after arriving by keyboard) behaves like a spreadsheet cell.
    const whole = !textual || text === '' || (start === 0 && end === text.length);
    if (key === 'ArrowUp' || key === 'ArrowDown') {
      if (event.altKey || (!whole && el.list)) return; // Open or browse suggestions.
      if (el.tagName === 'TEXTAREA' && !whole && (key === 'ArrowUp' ? text.slice(0, start) : text.slice(end)).includes('\n')) return;
      event.preventDefault();
      move(r + (key === 'ArrowUp' ? -1 : 1), c, event.shiftKey);
    } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
      const back = key === 'ArrowLeft';
      const edge = whole || (start === end && (back ? start === 0 : end === text.length));
      if (!edge || (event.shiftKey && !whole)) return;
      event.preventDefault();
      move(r, c + (back ? -1 : 1), event.shiftKey);
    } else if (key === 'Enter') {
      if (el.tagName === 'BUTTON') return;
      if (el.tagName === 'TEXTAREA' && event.altKey) {
        event.preventDefault();
        actions.edit(order[r], cols[c].key, `${text.slice(0, start)}\n${text.slice(end)}`);
        requestAnimationFrame(() => el.setSelectionRange(start + 1, start + 1));
        return;
      }
      if (el.list) { setTimeout(() => move(r + (event.shiftKey ? -1 : 1), c, false)); return; } // Let a highlighted suggestion apply first.
      event.preventDefault();
      move(r + (event.shiftKey ? -1 : 1), c, false);
    } else if (key === 'Delete' || key === 'Backspace') {
      if (multi || (!textual && el.tagName !== 'BUTTON')) { event.preventDefault(); clear(); }
    } else if (key === 'Escape') {
      if (multi) setSel({ ar: r, ac: c, fr: r, fc: c });
    } else if (key === 'F2' && textual) {
      event.preventDefault();
      el.setSelectionRange(text.length, text.length);
    }
  }
  function onCopy(event, cut = false) {
    if (event.defaultPrevented) return;
    const td = ownCell(event.target);
    if (!td || !bounds) return;
    const el = event.target;
    const textual = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type === 'text');
    if (!multi && textual && el.selectionStart !== el.selectionEnd && !(el.selectionStart === 0 && el.selectionEnd === el.value.length)) return;
    event.preventDefault();
    event.clipboardData.setData('text/plain', toTSV(copyMatrix(rows, order, cols, bounds, doctype, schema)));
    const cells = count(cellCount(bounds), 'cell');
    if (cut) commit(clearCells(rows, order, cols, bounds).rows, 'Cut cells', `Cut ${cells}.`);
    else setStatus(`Copied ${cells}.`);
  }
  function onPaste(event) {
    if (event.defaultPrevented) return;
    const td = ownCell(event.target);
    if (!td || !bounds) return;
    const text = event.clipboardData.getData('text/plain');
    const el = event.target;
    const textual = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type === 'text');
    if (!multi && textual && !/[\t\n\r]/.test(text)) return; // Ordinary paste into the text.
    event.preventDefault();
    const matrix = parseTSV(text);
    const result = pasteCells(rows, order, cols, bounds, matrix, needle ? null : () => blankRecord(doctype, schema));
    const single = matrix.length === 1 && matrix[0].length === 1;
    const span = single ? bounds.right - bounds.left : Math.max(...matrix.map(line => line.length)) - 1;
    const last = Math.min(bounds.top + result.height, order.length + result.added) - 1;
    commit(result.rows, 'Paste', `Pasted ${count(result.written, 'cell')}`
      + `${result.added ? ` and added ${count(result.added, 'row')}` : ''}`
      + `${result.skipped ? `; skipped ${result.skipped} that did not fit (child tables take rows copied from another child-table cell)` : ''}.`);
    setSel({ ar: bounds.top, ac: bounds.left, fr: Math.max(bounds.top, last), fc: Math.min(cols.length - 1, bounds.left + span) });
  }
  function startResize(event, column) {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const start = widthOf(column);
    let latest = prefs;
    const follow = moved => {
      latest = { ...prefs, widths: { ...prefs.widths, [column.key]: Math.max(56, Math.round(start + moved.clientX - startX)) } };
      setPrefs(latest);
    };
    const finish = () => {
      window.removeEventListener('mousemove', follow);
      window.removeEventListener('mouseup', finish);
      savePrefs(latest);
    };
    window.addEventListener('mousemove', follow);
    window.addEventListener('mouseup', finish);
  }
  const toggleColumn = (key, show) => savePrefs({ ...prefs, hidden: show ? hidden.filter(item => item !== key) : [...hidden, key] });

  const tableWidth = ROW_HEAD + cols.reduce((sum, column) => sum + widthOf(column), 0);
  const pinned = cols[0]?.pinned ? widthOf(cols[0]) : 0;
  const allChecked = order.length > 0 && order.every(i => checked.has(i));
  const selection = bounds ? `${bounds.bottom - bounds.top + 1} × ${bounds.right - bounds.left + 1}` : '';
  return <div className={`grid ${top ? 'grid-top' : 'grid-nested'}`} style={{ '--rowhead': `${ROW_HEAD}px`, '--pinned': `${pinned}px`, ...(width ? { '--grid-w': `${width}px` } : {}) }}>
    <div className="grid-toolbar">
      <input className="grid-filter" aria-label="Filter rows" placeholder="Filter rows…" value={rowFilter} onChange={e => { setRowFilter(e.target.value); setSel(null); }} />
      <Menu label={`Columns ${cols.length}/${all.length}`}>
        <label className="grid-menu-option"><input type="checkbox" checked={Boolean(prefs.dataOnly)} onChange={e => savePrefs({ ...prefs, dataOnly: e.target.checked })} />
          Hide empty fields <small>(required fields stay)</small></label>
        <div className="grid-menu-actions">
          <button type="button" onClick={() => savePrefs({ ...prefs, hidden: [], dataOnly: false })}>Show all</button>
          <button type="button" onClick={() => savePrefs({ ...prefs, hidden: all.filter(column => !column.pinned && !column.reqd).map(column => column.key) })}>Required only</button>
        </div>
        <div className="grid-menu-list">{all.filter(column => !column.pinned).map(column => <label className="grid-menu-option" key={column.key}>
          <input type="checkbox" checked={!hidden.includes(column.key)} onChange={e => toggleColumn(column.key, e.target.checked)} />
          {column.label}{column.reqd ? ' *' : ''} <small>{filledCount(rows, column)}/{rows.length}</small></label>)}</div>
      </Menu>
      <div className="grid-actions" role="group" aria-label="Row actions">
        <button type="button" disabled={!targetRows.length} onClick={() => rowOp('duplicate')} title="Copy the selected rows below them">Duplicate</button>
        <button type="button" onClick={() => rowOp('insert')} title="Insert a blank row below the selection">Insert row</button>
        <button type="button" disabled={!targetRows.length} onClick={() => rowOp('move', -1)} aria-label="Move rows up" title="Move rows up">↑</button>
        <button type="button" disabled={!targetRows.length} onClick={() => rowOp('move', 1)} aria-label="Move rows down" title="Move rows down">↓</button>
        <button type="button" className="catalog-danger" disabled={!targetRows.length} onClick={() => rowOp('delete')}>Delete{targetRows.length ? ` ${targetRows.length}` : ''}</button>
      </div>
      <div className="grid-actions" role="group" aria-label="Cell actions">
        <button type="button" disabled={!bounds} onClick={fill} title="Ctrl+D">Fill down</button>
        <button type="button" disabled={!bounds} onClick={clear} title="Delete">Clear</button>
        <button type="button" disabled={!order.length} onClick={copyTable} title="Copy the visible rows and columns with headers">Copy table</button>
        <button type="button" onClick={pasteRows} title="Add rows from spreadsheet cells on the clipboard; a header row matches columns by name">Paste rows</button>
      </div>
      <Menu label="Shortcuts" className="grid-help">
        <dl>{SHORTCUTS.map(([keys, action]) => <div key={keys}><dt>{keys}</dt><dd>{action}</dd></div>)}</dl>
      </Menu>
    </div>
    <p className="grid-status" aria-live="polite">
      {checked.size ? `${count(checked.size, 'row')} checked · ` : ''}{selection ? `${selection} cells selected` : ''}
      {(checked.size || selection) && status ? ' · ' : ''}{status}
    </p>
    <div className="grid-wrap" ref={wrap} onKeyDown={onKeyDown} onFocus={onFocus} onBlur={onBlur} onMouseDown={onMouseDown} onMouseOver={onMouseOver}
      onCopy={event => onCopy(event)} onCut={event => onCopy(event, true)} onPaste={onPaste}>
      <table className="grid-table" style={{ width: tableWidth }}>
        <colgroup><col style={{ width: ROW_HEAD }} />{cols.map(column => <col key={column.key} style={{ width: widthOf(column) }} />)}</colgroup>
        <thead><tr>
          <th className="grid-rowhead grid-corner" scope="col">
            <input type="checkbox" tabIndex={-1} aria-label="Check every shown row" checked={allChecked}
              onChange={() => setChecked(allChecked ? new Set() : new Set(order))} />
            <span>{order.length === rows.length ? rows.length : `${order.length}/${rows.length}`}</span>
          </th>
          {cols.map((column, c) => {
            const filled = filledCount(rows, column);
            const inRange = bounds && c >= bounds.left && c <= bounds.right;
            return <th key={column.key} scope="col" className={`${column.pinned ? 'grid-pinned' : ''} ${inRange ? 'is-selected' : ''} ${column.reqd && filled < rows.length ? 'is-missing' : ''}`}
              title={[`${column.label} (${column.key})`, column.fieldtype + (column.options && column.kind !== 'table' && !column.options.includes('\n') ? ` → ${column.options}` : ''),
                column.kind === 'table' ? `Child table: ${column.options}` : '', column.description, `${filled} of ${rows.length} rows filled`].filter(Boolean).join('\n')}>
              <button type="button" className="grid-head" onClick={e => selectColumn(c, e.shiftKey)}>
                <span className="grid-head-label">{column.label}{column.reqd ? <b aria-label="required"> *</b> : null}</span>
                <small>{filled}/{rows.length}</small>
              </button>
              {!column.pinned && <button type="button" className="grid-hide" aria-label={`Hide ${column.label}`} title="Hide column" onClick={() => toggleColumn(column.key, false)}>×</button>}
              <span className="grid-resize" aria-hidden="true" onMouseDown={e => startResize(e, column)}
                onDoubleClick={() => { const widths = { ...prefs.widths }; delete widths[column.key]; savePrefs({ ...prefs, widths }); }} />
            </th>;
          })}
        </tr></thead>
        <tbody>
          {order.map((i, r) => {
            const rowOpen = [...open].filter(id => id.startsWith(`${i}|`)).map(id => id.slice(String(i).length + 1)).join('|');
            const inRange = bounds && r >= bounds.top && r <= bounds.bottom;
            return <GridRow key={i} grid={grid} doctype={doctype} row={rows[i]} index={i} r={r} columns={cols} top={top} path={path}
              sel={inRange ? `${bounds.left}:${bounds.right}` : ''} active={clamped && clamped.fr === r ? clamped.fc : -1}
              checked={checked.has(i)} open={rowOpen} issues={index} issueSig={(index.rows.get(`${path}[${i}]`) || []).join('\n')}
              lists={lists} reference={reference} actions={actions} rowIdPrefix={rowIdPrefix}
              childFocus={childFocus?.row === i ? childFocus : null} />;
          })}
          {!order.length && <tr><td className="grid-empty" colSpan={cols.length + 1}>
            {rows.length ? 'No rows match the filter.' : 'No rows yet. Add a row, or copy cells from a spreadsheet and use Paste rows.'}</td></tr>}
        </tbody>
      </table>
    </div>
    <div className="grid-footer">
      <button type="button" onClick={() => addRows(1)}>+ Add row</button>
      <button type="button" onClick={() => addRows(10)}>+ Add 10 rows</button>
      {needle && <span>Showing {order.length} of {rows.length} rows</span>}
    </div>
    {targetList.map(target => <LinkList key={target} id={lists[target]} target={target} local={localNames(target)} reference={reference} />)}
  </div>;
}
