// Renaming records and replacing text across a draft. Links follow renamed records,
// including records whose names are built from links (a Link naming field, or a format: rule),
// so renaming an Item renames its spec, the spec's offerings, and every link to them.
// Catalogs are never mutated; every function returns new objects so undo can keep snapshots.
import { inReference, recordName } from './catalog-model.js';

const TABLES = new Set(['Table', 'Table MultiSelect']);
const LINKS = new Set(['Link', 'Dynamic Link']);
const TEXT_TYPES = new Set(['Data', 'Link', 'Dynamic Link', 'Small Text', 'Text', 'Long Text', 'Text Editor']);
const MAX_PASSES = 20;
const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const key = (doctype, name) => JSON.stringify([doctype, name]);

/** The field holding a record's typed name, or null when the name is built from other fields. */
export function namingField(doctype, schema) {
  const rule = schema.doctypes[doctype]?.autoname || '';
  if (rule.startsWith('field:')) return rule.slice(6);
  return rule.startsWith('format:') ? null : 'name';
}

function recordNames(records, schema) {
  const names = new Map();
  for (const [doctype, rows] of Object.entries(records)) rows.forEach((row, i) => {
    if (isRecord(row)) names.set(key(doctype, i), recordName(doctype, row, schema));
  });
  return names;
}

/** Rewrite links in a row and its child rows that point at renamed records; `skip` is a field to leave. */
function rewriteLinks(doctype, row, schema, renames, path, changes, skip = null) {
  let next = row;
  for (const field of schema.doctypes[doctype]?.fields || []) {
    const value = row[field.fieldname];
    if (value === undefined || value === null || value === '' || field.fieldname === skip) continue;
    if (TABLES.has(field.fieldtype)) {
      if (!Array.isArray(value)) continue;
      let children = value;
      value.forEach((child, i) => {
        if (!isRecord(child)) return;
        const updated = rewriteLinks(field.options, child, schema, renames, `${path}${field.fieldname}[${i}].`, changes);
        if (updated === child) return;
        if (children === value) children = [...value];
        children[i] = updated;
      });
      if (children !== value) next = { ...next, [field.fieldname]: children };
    } else if (LINKS.has(field.fieldtype)) {
      const target = field.fieldtype === 'Link' ? field.options : row[field.options];
      const to = renames.get(key(target, String(value)));
      if (to === undefined || to === value) continue;
      next = { ...next, [field.fieldname]: to };
      changes.push({ path: `${path}${field.fieldname}`, from: String(value), to });
    }
  }
  return next;
}

/**
 * Rename records ([{ doctype, from, to }]) and update every link to them. A rename can
 * target a name the draft only links to, which retargets those links. Returns the new
 * catalog, `changes` (one per field written: { doctype, index, path, from, to, rename })
 * and `renamed` (every record renamed, including ones named from a renamed link).
 */
export function renameRecords(catalog, schema, renames) {
  const records = { ...catalog.records };
  const changes = [];
  const done = new Map();
  let pending = new Map(renames.filter(item => item.from && item.to && item.from !== item.to)
    .map(item => [key(item.doctype, item.from), item.to]));
  for (let pass = 0; pending.size && pass < MAX_PASSES; pass += 1) {
    const before = recordNames(records, schema);
    for (const [doctype, rows] of Object.entries(records)) {
      const naming = namingField(doctype, schema);
      let list = rows;
      rows.forEach((row, i) => {
        if (!isRecord(row)) return;
        const local = [];
        let next = row;
        const own = naming ? pending.get(key(doctype, recordName(doctype, row, schema))) : undefined;
        if (own !== undefined) {
          local.push({ path: naming, from: recordName(doctype, row, schema), to: own, rename: true });
          next = { ...row, [naming]: own };
        }
        next = rewriteLinks(doctype, next, schema, pending, '', local, own !== undefined ? naming : null);
        if (next === row) return;
        if (list === rows) list = [...rows];
        list[i] = next;
        local.forEach(change => changes.push({ doctype, index: i, ...change }));
      });
      if (list !== rows) records[doctype] = list;
    }
    pending.forEach((to, id) => done.set(id, to));
    // Records named from links or format rules changed name; links to them follow next pass.
    const after = recordNames(records, schema);
    const cascade = new Map();
    for (const [id, name] of before) {
      const now = after.get(id);
      const renamed = key(JSON.parse(id)[0], name);
      if (name && now && now !== name && !done.has(renamed)) cascade.set(renamed, now);
    }
    pending = cascade;
  }
  const renamed = [...done].map(([id, to]) => { const [doctype, from] = JSON.parse(id); return { doctype, from, to }; });
  return { catalog: { ...catalog, records }, changes, renamed };
}

/**
 * Renames that would collide, as Map(index in `renames` → reason): an empty name, two
 * renames to one name, a draft record that already has the name, or an ERPNext record.
 */
export function renameConflicts(catalog, schema, reference, renames) {
  const conflicts = new Map();
  const away = new Set(renames.map(item => key(item.doctype, item.from)));
  const targets = new Set();
  renames.forEach((item, i) => {
    const to = String(item.to ?? '').trim();
    const id = key(item.doctype, to);
    if (!to) conflicts.set(i, 'The new name is empty');
    else if (targets.has(id)) conflicts.set(i, `Another change also renames a ${item.doctype} to ${to}`);
    else if (!away.has(id) && (catalog.records[item.doctype] || []).some(row => isRecord(row) && recordName(item.doctype, row, schema) === to)) {
      conflicts.set(i, `${to} is already a ${item.doctype} in this draft`);
    } else if (inReference(reference, item.doctype, to)) conflicts.set(i, `${to} already exists in ERPNext`);
    targets.add(id);
  });
  return conflicts;
}

/** A replacer for text, or null when nothing is searched. Throws on an invalid pattern. */
export function textReplacer({ find = '', replace = '', regex = false, matchCase = false, wholeValue = false }) {
  if (!find) return null;
  const source = regex ? find : find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(wholeValue ? `^(?:${source})$` : source, matchCase ? 'g' : 'gi');
  if (pattern.test('')) throw new Error('The search matches empty text; make it more specific.');
  return text => {
    pattern.lastIndex = 0;
    if (!pattern.test(text)) return null;
    pattern.lastIndex = 0;
    return regex ? text.replace(pattern, replace) : text.replace(pattern, () => replace);
  };
}

function textFields(doctype, row, schema, keys, visit) {
  for (const field of schema.doctypes[doctype]?.fields || []) {
    const value = row[field.fieldname];
    if (TABLES.has(field.fieldtype) && Array.isArray(value)) {
      value.forEach((child, i) => isRecord(child) && textFields(field.options, child, schema, [...keys, field.fieldname, i], visit));
    } else if (TEXT_TYPES.has(field.fieldtype) && typeof value === 'string' && value) visit(field, row, value, [...keys, field.fieldname]);
  }
}

const pathText = keys => keys.reduce((text, part) => typeof part === 'number' ? `${text}[${part}]` : `${text}${text ? '.' : ''}${part}`, '');

/**
 * Plan a find and replace. `scope` is 'names' (record names; links follow) or 'text'
 * (names plus every text and link field). `doctypes` limits it to those DocTypes.
 * Returns changes: { id, kind: 'name' | 'value', doctype, index, record, keys, path, label, from, to }.
 */
export function findReplace(catalog, schema, options) {
  const replacer = textReplacer(options);
  if (!replacer) return [];
  const { scope = 'names', doctypes = null } = options;
  const changes = [];
  const renamed = new Set();
  const inScope = Object.entries(catalog.records).filter(([doctype]) => schema.doctypes[doctype] && (!doctypes || doctypes.includes(doctype)));
  for (const [doctype, rows] of inScope) {
    const naming = namingField(doctype, schema);
    if (!naming) continue;
    rows.forEach((row, index) => {
      if (!isRecord(row)) return;
      const name = recordName(doctype, row, schema);
      const to = name ? replacer(name) : null;
      if (to === null || to === name) return;
      renamed.add(key(doctype, name));
      changes.push({ id: `${doctype}|${index}|${naming}`, kind: 'name', doctype, index, record: name, keys: [naming], path: naming, label: 'Name', from: name, to });
    });
  }
  if (scope !== 'text') return changes;
  for (const [doctype, rows] of inScope) {
    const naming = namingField(doctype, schema);
    rows.forEach((row, index) => {
      if (!isRecord(row)) return;
      const record = recordName(doctype, row, schema);
      textFields(doctype, row, schema, [], (field, owner, value, keys) => {
        if (keys.length === 1 && keys[0] === naming) return;
        // Links to renamed records follow the rename instead.
        const target = field.fieldtype === 'Link' ? field.options : field.fieldtype === 'Dynamic Link' ? owner[field.options] : null;
        if (target && renamed.has(key(target, value))) return;
        const to = replacer(value);
        if (to === null || to === value) return;
        changes.push({ id: `${doctype}|${index}|${keys.join('.')}`, kind: 'value', doctype, index, record, keys,
          path: pathText(keys), label: field.label || field.fieldname, from: value, to });
      });
    });
  }
  return changes;
}

function setIn(value, keys, next) {
  if (!keys.length) return next;
  const [head, ...rest] = keys;
  const copy = Array.isArray(value) ? [...value] : { ...value };
  copy[head] = setIn(value?.[head], rest, next);
  return copy;
}

/** Apply chosen findReplace changes: values are written, then names are renamed with their links. */
export function applyReplace(catalog, schema, changes) {
  const records = { ...catalog.records };
  for (const change of changes) {
    if (change.kind !== 'value') continue;
    const rows = [...records[change.doctype]];
    rows[change.index] = setIn(rows[change.index], change.keys, change.to);
    records[change.doctype] = rows;
  }
  const renames = changes.filter(change => change.kind === 'name').map(({ doctype, from, to }) => ({ doctype, from, to }));
  return renameRecords({ ...catalog, records }, schema, renames);
}
