// Spreadsheet helpers for the record table: columns, clipboard text, and bulk edits.
// Rows are never mutated; every edit returns new arrays and objects so undo can keep snapshots.
import { recordName } from './catalog-model.js';

export const TABLE_TYPES = new Set(['Table', 'Table MultiSelect']);
export const NUMERIC_TYPES = new Set(['Int', 'Float', 'Currency', 'Percent']);
export const LONG_TEXT_TYPES = new Set(['Small Text', 'Text', 'Long Text', 'Text Editor', 'JSON', 'Code']);
const TRUE_WORDS = new Set(['1', 'true', 'yes', 'y', 'x', '✓', '✔', 'checked', 'on']);
const FALSE_WORDS = new Set(['0', 'false', 'no', 'n', 'unchecked', 'off']);
const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

/**
 * One column per field, naming field first. Top-level grids also get the record
 * name: an editable Record ID for prompt naming, or the computed name for format naming.
 */
export function gridColumns(doctype, schema, rows = [], top = true) {
  const meta = schema.doctypes[doctype];
  const rule = meta.autoname || '';
  const naming = top && rule.startsWith('field:') ? rule.slice(6) : null;
  const columns = [];
  if (top && rule.startsWith('format:')) {
    columns.push({ key: '__name', label: 'Record name', fieldtype: 'Data', kind: 'computed', pinned: true,
      description: `Built from ${rule.slice(7)}` });
  } else if (top && !naming) {
    columns.push({ key: 'name', label: 'Record ID', fieldtype: 'Data', kind: 'field', pinned: true, reqd: rule === 'prompt' });
  }
  for (const field of meta.fields) {
    if (field.read_only && !rows.some(row => isRecord(row) && Object.hasOwn(row, field.fieldname))) continue;
    const column = {
      key: field.fieldname, label: field.label || field.fieldname, fieldtype: field.fieldtype, options: field.options,
      kind: TABLE_TYPES.has(field.fieldtype) ? 'table' : 'field', reqd: Boolean(field.reqd),
      description: field.description ? field.description.replace(/<[^>]*>/g, '') : '',
    };
    if (field.fieldname === naming) columns.unshift({ ...column, pinned: true }); else columns.push(column);
  }
  return columns;
}

/** True when a cell holds data worth reviewing; unchecked boxes count as empty. */
export function hasData(value, column) {
  if (value === undefined || value === null || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (column?.fieldtype === 'Check') return Boolean(value) && value !== '0';
  return true;
}

export function filledCount(rows, column) {
  return rows.filter(row => hasData(row?.[column.key], column)).length;
}

/** Columns to show: pinned name, then fields matching the search that aren't hidden. */
export function visibleColumns(columns, rows, { dataOnly = false, hidden = [], filter = '' } = {}) {
  const needle = filter.trim().toLowerCase();
  return columns.filter(column => column.pinned || (
    !hidden.includes(column.key)
    && (!needle || `${column.label} ${column.key}`.toLowerCase().includes(needle))
    && (!dataOnly || column.reqd || filledCount(rows, column) > 0)));
}

export function defaultWidth(column) {
  if (column.kind === 'computed') return 220;
  if (column.kind === 'table') return 120;
  if (column.fieldtype === 'Check') return 72;
  if (NUMERIC_TYPES.has(column.fieldtype)) return 110;
  if (column.fieldtype === 'Select') return 160;
  if (['Link', 'Dynamic Link'].includes(column.fieldtype)) return 200;
  if (LONG_TEXT_TYPES.has(column.fieldtype)) return 260;
  return 180;
}

/** Spreadsheet-compatible TSV: quoted cells may hold tabs, newlines and doubled quotes. */
export function parseTSV(text) {
  const source = String(text ?? '').replace(/\r\n?/g, '\n').replace(/\n$/, '');
  const rows = [[]];
  let cell = '';
  let i = 0;
  while (i <= source.length) {
    if (cell === '' && source[i] === '"' && (i === 0 || source[i - 1] === '\t' || source[i - 1] === '\n')) {
      let end = i + 1;
      let quoted = '';
      while (end < source.length) {
        if (source[end] === '"' && source[end + 1] === '"') { quoted += '"'; end += 2; }
        else if (source[end] === '"') break;
        else quoted += source[end++];
      }
      // A quote that never closes, or is followed by more text, was literal.
      if (end < source.length && [undefined, '\t', '\n'].includes(source[end + 1])) { cell = quoted; i = end + 1; continue; }
    }
    const char = source[i];
    if (char === undefined || char === '\t' || char === '\n') {
      rows.at(-1).push(cell);
      cell = '';
      if (char === '\n') rows.push([]);
    } else cell += char;
    i += 1;
  }
  return rows;
}

export function toTSV(matrix) {
  return matrix.map(row => row.map(value => {
    const text = String(value ?? '');
    return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }).join('\t')).join('\n');
}

/** Read a typed or pasted number; text that isn't one is kept so validation can flag it. */
export function parseNumber(text) {
  const raw = String(text ?? '').trim();
  if (!raw) return '';
  let cleaned = raw.replace(/^\$/, '').replace(/%$/, '');
  if (/^[-+]?\d{1,3}(,\d{3})+(\.\d*)?$/.test(cleaned)) cleaned = cleaned.replace(/,/g, '');
  return /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(cleaned) ? Number(cleaned) : raw;
}

/**
 * Convert clipboard text for a column. Returns { ok, value } where '' clears the
 * cell; ok is false when the text can't fill the column (it is then skipped).
 */
export function coerceCell(column, text) {
  const raw = String(text ?? '').replace(/\r/g, '');
  const value = raw.trim();
  if (column.kind === 'computed') return { ok: false };
  if (!value) return { ok: true, value: '' };
  if (column.kind === 'table') {
    try {
      const rows = JSON.parse(value);
      if (Array.isArray(rows) && rows.every(isRecord)) return { ok: true, value: rows };
    } catch { /* Not child rows. */ }
    return { ok: false };
  }
  if (NUMERIC_TYPES.has(column.fieldtype)) return { ok: true, value: parseNumber(value) };
  if (column.fieldtype === 'Check') {
    const word = value.toLowerCase();
    return { ok: true, value: TRUE_WORDS.has(word) ? 1 : FALSE_WORDS.has(word) ? 0 : value };
  }
  if (column.fieldtype === 'Select') {
    const choices = String(column.options || '').split('\n').filter(Boolean);
    return { ok: true, value: choices.find(choice => choice === value)
      ?? choices.find(choice => choice.toLowerCase() === value.toLowerCase()) ?? value };
  }
  if (LONG_TEXT_TYPES.has(column.fieldtype)) return { ok: true, value: raw };
  return { ok: true, value };
}

/** Text for one cell when copying. Child tables copy as JSON so they paste into other rows. */
export function cellText(column, row, doctype, schema) {
  if (column.kind === 'computed') return recordName(doctype, row, schema);
  const value = row?.[column.key];
  if (value === undefined || value === null) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Set or clear (on '') one field, returning a new row. */
export function setField(row, key, value) {
  const next = { ...(isRecord(row) ? row : {}) };
  if (value === '' || value === undefined) delete next[key]; else next[key] = value;
  return next;
}

/** Normalize an anchor/focus selection to inclusive bounds. */
export function rangeBounds(selection) {
  if (!selection) return null;
  return {
    top: Math.min(selection.ar, selection.fr), bottom: Math.max(selection.ar, selection.fr),
    left: Math.min(selection.ac, selection.fc), right: Math.max(selection.ac, selection.fc),
  };
}

export function copyMatrix(rows, order, columns, bounds, doctype, schema) {
  const matrix = [];
  for (let r = bounds.top; r <= bounds.bottom; r += 1) {
    const row = rows[order[r]];
    matrix.push(columns.slice(bounds.left, bounds.right + 1).map(column => cellText(column, row, doctype, schema)));
  }
  return matrix;
}

const cloneValue = value => (value && typeof value === 'object' ? structuredClone(value) : value);

/**
 * Paste a block at the top-left of the selection. A single value fills the whole
 * selection. Rows past the end are appended when `blank` is given (no row filter).
 * `order` maps visible rows to row indexes.
 */
export function pasteCells(rows, order, columns, bounds, matrix, blank = null) {
  const next = [...rows];
  const visible = [...order];
  const single = matrix.length === 1 && matrix[0].length === 1;
  const height = single ? bounds.bottom - bounds.top + 1 : matrix.length;
  const width = single ? bounds.right - bounds.left + 1 : Math.max(...matrix.map(line => line.length));
  let written = 0;
  let skipped = 0;
  let added = 0;
  for (let r = 0; r < height; r += 1) {
    const at = bounds.top + r;
    if (at >= visible.length) {
      if (!blank) break;
      next.push(blank());
      visible.push(next.length - 1);
      added += 1;
    }
    const index = visible[at];
    let row = next[index];
    for (let c = 0; c < width; c += 1) {
      const column = columns[bounds.left + c];
      if (!column) break;
      const text = single ? matrix[0][0] : matrix[r][c];
      if (text === undefined) continue;
      const { ok, value } = coerceCell(column, text);
      if (!ok) { if (column.kind !== 'computed') skipped += 1; continue; }
      row = setField(row, column.key, value);
      written += 1;
    }
    next[index] = row;
  }
  return { rows: next, written, skipped, added, height };
}

/**
 * Rows to append from spreadsheet cells. A first line that names the columns (by
 * label or field name) maps cells by header; otherwise cells follow `visible`.
 */
export function rowsFromMatrix(matrix, columns, visible, blank) {
  const names = (matrix[0] || []).map(text => text.trim().replace(/\s*\*$/, '').toLowerCase());
  const byHeader = names.map(name => name && columns.find(column => column.label.toLowerCase() === name || column.key.toLowerCase() === name));
  const header = byHeader.filter(Boolean).length >= Math.max(1, Math.ceil(names.filter(Boolean).length / 2));
  const mapping = header ? byHeader : visible;
  let skipped = 0;
  const rows = (header ? matrix.slice(1) : matrix).filter(line => line.some(text => text.trim())).map(line => {
    let row = blank();
    line.forEach((text, i) => {
      const column = mapping[i];
      if (!column || column.kind === 'computed') return;
      const { ok, value } = coerceCell(column, text);
      if (ok) row = setField(row, column.key, value); else skipped += 1;
    });
    return row;
  });
  return { rows, skipped, header };
}

/** Copy the top selected row into the rows below it; one selected row copies from the row above. */
export function fillDown(rows, order, columns, bounds) {
  const sourceAt = bounds.top === bounds.bottom ? bounds.top - 1 : bounds.top;
  if (sourceAt < 0) return { rows, written: 0 };
  const source = rows[order[sourceAt]];
  const next = [...rows];
  let written = 0;
  for (let r = sourceAt + 1; r <= bounds.bottom; r += 1) {
    let row = next[order[r]];
    for (const column of columns.slice(bounds.left, bounds.right + 1)) {
      if (column.kind === 'computed') continue;
      row = setField(row, column.key, cloneValue(source?.[column.key]) ?? '');
      written += 1;
    }
    next[order[r]] = row;
  }
  return { rows: next, written };
}

export function clearCells(rows, order, columns, bounds) {
  const next = [...rows];
  let written = 0;
  for (let r = bounds.top; r <= bounds.bottom; r += 1) {
    let row = next[order[r]];
    for (const column of columns.slice(bounds.left, bounds.right + 1)) {
      if (column.kind === 'computed') continue;
      row = setField(row, column.key, '');
      written += 1;
    }
    next[order[r]] = row;
  }
  return { rows: next, written };
}

/** Insert rows after the last of `indexes`, returning the rows and the new rows' indexes. */
export function insertAfter(rows, indexes, made) {
  const at = indexes.length ? Math.max(...indexes) + 1 : rows.length;
  return { rows: [...rows.slice(0, at), ...made, ...rows.slice(at)], inserted: made.map((_, i) => at + i) };
}

export function duplicateRows(rows, indexes, copy = structuredClone) {
  const sorted = [...indexes].sort((a, b) => a - b);
  return insertAfter(rows, sorted, sorted.map(i => copy(rows[i])));
}

export function removeRows(rows, indexes) {
  const drop = new Set(indexes);
  return rows.filter((_, i) => !drop.has(i));
}

/** Move the chosen rows one step up (-1) or down (+1); blocked rows stay put. */
export function moveRows(rows, indexes, direction) {
  const next = [...rows];
  const positions = new Set(indexes);
  // Rows nearest the edge move first, so a blocked row also blocks the rows behind it.
  for (const i of [...positions].sort((a, b) => direction < 0 ? a - b : b - a)) {
    const j = i + direction;
    if (j < 0 || j >= next.length || positions.has(j)) continue;
    [next[i], next[j]] = [next[j], next[i]];
    positions.delete(i);
    positions.add(j);
  }
  return { rows: next, indexes: [...positions].sort((a, b) => a - b) };
}

/**
 * Index validation findings by location (`Doctype[0].child[1].field`) so the grid
 * can mark cells, child-table cells and row numbers. `rows` lists every finding
 * under a row, relative to it, for the row's tooltip.
 */
export function issueIndex(issues, missing = [], catalog = null, schema = null) {
  const cells = new Map();
  const add = (path, message) => {
    if (!cells.has(path)) cells.set(path, []);
    if (!cells.get(path).includes(message)) cells.get(path).push(message);
  };
  for (const issue of issues) {
    const located = /^(.+?\[\d+\][^:]*): (.+)$/.exec(issue);
    const duplicate = /^(.+): duplicate record (.+)$/.exec(issue);
    if (located) add(located[1], located[2]);
    else if (duplicate && catalog && schema?.doctypes[duplicate[1]]) {
      (catalog.records[duplicate[1]] || []).forEach((row, i) => {
        if (recordName(duplicate[1], row, schema) === duplicate[2]) add(`${duplicate[1]}[${i}]`, `duplicate record ${duplicate[2]}`);
      });
    }
  }
  for (const link of missing) for (const source of link.sources) add(source, `unresolved ${link.doctype || 'link'} / ${link.name}`);
  const under = new Set();
  const rows = new Map();
  for (const [path, messages] of cells) {
    for (let k = 1; k < path.length; k += 1) {
      if (path[k] === '[' || path[k] === '.') under.add(path.slice(0, k));
      if (path[k - 1] === ']' && (k === path.length || path[k] === '.')) {
        const rowPath = path.slice(0, k);
        if (!rows.has(rowPath)) rows.set(rowPath, []);
        messages.forEach(message => rows.get(rowPath).push(`${path.slice(k + 1)}: ${message}`));
      }
    }
    if (path.endsWith(']')) {
      if (!rows.has(path)) rows.set(path, []);
      rows.get(path).push(...messages);
    }
  }
  return { cells, under, rows };
}
