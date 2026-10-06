// Cloning an existing ERPNext product family into a draft. Starting from a template (or
// Webflow Product), the family is every record it links to, plus the records owned by it
// (maps, offerings, submittal mappings, specs of its Items). Rename rules give the copies
// new names; a record is copied only when its name changes, since a copy keeping its
// name would collide with the original. Unchanged names stay links to existing records.
import { inReference, linkedRecords, recordName } from './catalog-model.js';
import { namingField, renameRecords } from './rename-model.js';

const MASTERS = new Set(['Item Group', 'UOM', 'Brand', 'Item Attribute', 'Item Price', 'ilL-Webflow-Category']);
const LINKS = new Set(['Link', 'Dynamic Link']);
export const DEFAULT_LIMIT = 300;
const key = (doctype, name) => JSON.stringify([doctype, name]);
const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

/** Records of these DocTypes are shared masters: always linked, never copied. */
export function copyable(doctype, schema) {
  const meta = schema.doctypes[doctype];
  return Boolean(meta) && !meta.istable && !doctype.startsWith('ilL-Attribute-') && !MASTERS.has(doctype);
}

/** DocTypes a family can start from: every product template, and Webflow Product. */
export function rootTypes(schema) {
  return [...new Set([...Object.values(schema.products).map(product => product.template), 'ilL-Webflow-Product'])];
}

const templateTypes = schema => new Set(Object.values(schema.products).map(product => product.template));

/**
 * The record a related record belongs to: a template it links, else a spec, else the Item
 * it describes (`item`, or `variant_of` for Item variants). Returns [{ doctype, name }].
 */
function owners(doctype, record, schema) {
  const templates = templateTypes(schema);
  const classes = [[], [], []];
  for (const field of schema.doctypes[doctype]?.fields || []) {
    const value = record[field.fieldname];
    if (!LINKS.has(field.fieldtype) || value === undefined || value === null || value === '') continue;
    const target = field.fieldtype === 'Link' ? field.options : record[field.options];
    if (!target) continue;
    if (templates.has(target)) classes[0].push({ doctype: target, name: String(value) });
    else if (target.startsWith('ilL-Spec-')) classes[1].push({ doctype: target, name: String(value) });
    else if (target === 'Item' && ['item', 'variant_of'].includes(field.fieldname)) classes[2].push({ doctype: target, name: String(value) });
  }
  return classes.find(list => list.length) || [];
}

const ownerIndexes = new WeakMap();
/** Map(owner key → [{ doctype, name }]) over the reference; templates never count as owned. */
export function ownerIndex(reference, schema) {
  if (!reference?.doctypes) return new Map();
  if (ownerIndexes.has(reference)) return ownerIndexes.get(reference);
  const index = new Map();
  const templates = templateTypes(schema);
  for (const [doctype, entry] of Object.entries(reference.doctypes)) {
    if (!copyable(doctype, schema) || templates.has(doctype)) continue;
    for (const [name, record] of Object.entries(entry.records || {})) {
      for (const owner of owners(doctype, record || {}, schema)) {
        const id = key(owner.doctype, owner.name);
        if (!index.has(id)) index.set(id, []);
        index.get(id).push({ doctype, name });
      }
    }
  }
  ownerIndexes.set(reference, index);
  return index;
}

/** Keep the case of what was matched: "ca01" → "ca02", "CA01" → "CA02". */
function sameCase(match, replace) {
  if (match === match.toLowerCase() && match !== match.toUpperCase()) return replace.toLowerCase();
  if (match === match.toUpperCase() && match !== match.toLowerCase()) return replace.toUpperCase();
  return replace;
}

/** A function giving a name its new name under rename rules [{ find, replace }], applied in order. */
export function ruleRenamer(rules, { matchCase = false } = {}) {
  const active = (rules || []).filter(rule => rule.find).map(rule => ({
    pattern: new RegExp(rule.find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), matchCase ? 'g' : 'gi'), replace: rule.replace ?? '',
  }));
  return name => active.reduce((text, rule) => text.replace(rule.pattern, match => matchCase ? rule.replace : sameCase(match, rule.replace)), name);
}

/**
 * Find a family and decide what to do with each record. `full(doctype, name)` returns a
 * fetched full record (with child tables) or undefined; the reference fills in until then.
 * `modes` overrides a node's mode: 'copy', 'link' (keep linking the original) or 'existing'
 * (link the existing record that already has the new name).
 * Returns { nodes: [{ doctype, name, newName, mode, modes, reason, via, owner }], needed, truncated }:
 * `needed` lists copied records still to fetch, so their child-table links can be followed.
 */
export function discoverFamily({ root, reference, schema, full = () => undefined, rename = name => name, modes = new Map(), limit = DEFAULT_LIMIT }) {
  const index = ownerIndex(reference, schema);
  const content = (doctype, name) => full(doctype, name) ?? reference?.doctypes?.[doctype]?.records?.[name];
  const exists = (doctype, name) => full(doctype, name) !== undefined || inReference(reference, doctype, name);
  const memo = new Map();
  const resolving = new Set();

  /** { newName, mode, modes, reason } for one record, independent of how it was reached. */
  function decide(doctype, name) {
    const id = key(doctype, name);
    if (memo.has(id)) return memo.get(id);
    if (resolving.has(id)) return { newName: name, mode: 'link', modes: ['link'], reason: 'Circular name' };
    resolving.add(id);
    let result;
    const isRoot = doctype === root.doctype && name === root.name;
    if (!copyable(doctype, schema)) result = { newName: name, mode: 'link', modes: ['link'], reason: 'Shared master record' };
    else if (!exists(doctype, name)) result = { newName: name, mode: 'link', modes: ['link'], reason: 'Not found in ERPNext' };
    else {
      const record = content(doctype, name) || {};
      const naming = namingField(doctype, schema);
      const fields = new Map((schema.doctypes[doctype]?.fields || []).map(field => [field.fieldname, field]));
      const linkNamed = Boolean(naming) && LINKS.has(fields.get(naming)?.fieldtype);
      // A name taken from a link (a spec named by its Item) follows what happens to that record.
      const newName = !naming ? formatName(doctype, record, fields)
        : linkNamed ? linkedName({ ...record, [naming]: record[naming] || name }, fields.get(naming)) : rename(name);
      // Stored ERPNext names can predate a format rule or a renamed link, so derived names are
      // compared with the same derivation before renaming.
      const before = !naming ? recordName(doctype, record, schema) : linkNamed ? String(record[naming] || name) : name;
      if (newName === before) {
        result = { newName, mode: 'link', modes: ['link'], reason: isRoot ? 'Add a rename rule that changes this name' : 'Name unchanged by the rename rules' };
      } else {
        const taken = inReference(reference, doctype, newName);
        const allowed = taken ? ['existing', 'link'] : ['copy', 'link'];
        const chosen = modes.get(id);
        const mode = allowed.includes(chosen) ? chosen : allowed[0];
        result = { newName, mode, modes: allowed, reason: taken ? `${newName} already exists in ERPNext` : isRoot ? 'Family root' : 'Renamed by the rules' };
      }
    }
    resolving.delete(id);
    memo.set(id, result);
    return result;
  }
  /** The value a link field will hold after cloning: its target's new name unless the target is kept. */
  function linkedName(record, field) {
    const value = record[field.fieldname];
    if (value === undefined || value === null || value === '') return '';
    const target = field.fieldtype === 'Link' ? field.options : record[field.options];
    const decision = target ? decide(target, String(value)) : null;
    return decision && decision.mode !== 'link' ? decision.newName : String(value);
  }
  /** A format: name after cloning: linked parts take the name their target will have. */
  function formatName(doctype, record, fields) {
    const rule = (schema.doctypes[doctype]?.autoname || '').slice(7);
    return rule.replace(/\{([^}]+)\}/g, (_, fieldname) => {
      const field = fields.get(fieldname);
      return field && LINKS.has(field.fieldtype) ? linkedName(record, field) : String(record[fieldname] ?? '');
    });
  }

  const nodes = new Map();
  const needed = [];
  let copies = 0;
  let truncated = false;
  const queue = [];
  const add = (doctype, name, via, owner) => {
    const id = key(doctype, name);
    if (nodes.has(id)) return;
    const node = { doctype, name, via, owner, ...decide(doctype, name) };
    nodes.set(id, node);
    queue.push(node);
  };
  add(root.doctype, root.name, 'root', null);
  while (queue.length) {
    const node = queue.shift();
    if (node.mode !== 'copy') continue;
    if (copies >= limit) { truncated = true; continue; }
    copies += 1;
    if (full(node.doctype, node.name) === undefined) needed.push({ doctype: node.doctype, name: node.name });
    const record = content(node.doctype, node.name) || {};
    const from = `${node.doctype} ${node.name}`;
    for (const link of linkedRecords(node.doctype, record, schema)) if (link.doctype) add(link.doctype, link.name, 'link', from);
    for (const owned of index.get(key(node.doctype, node.name)) || []) add(owned.doctype, owned.name, 'owned', from);
  }
  // Records the user chose a mode for stay listed, so the choice can be changed back.
  for (const id of modes.keys()) {
    const [doctype, name] = JSON.parse(id);
    if (!nodes.has(id)) nodes.set(id, { doctype, name, via: 'chosen', owner: null, ...decide(doctype, name) });
  }
  return { nodes: [...nodes.values()], needed, truncated };
}

/**
 * Add a discovered family's copies to a draft. Copies take their new names and every link
 * between them follows; links to 'existing' records point at the new name. A copied
 * template's `webflow_product` is cleared when the product is copied too, since the pair
 * would be circular on import. Records whose new name is already in the draft are skipped.
 */
export function cloneFamily(catalog, schema, discovery, full) {
  const records = {};
  const copied = discovery.nodes.filter(node => node.mode === 'copy');
  for (const node of copied) {
    const row = structuredClone(full(node.doctype, node.name) || {});
    if (namingField(node.doctype, schema) === 'name') row.name = node.name;
    (records[node.doctype] ||= []).push(row);
  }
  // Format names follow their links, but links hold the stored name, which can predate the format.
  const renames = discovery.nodes.filter(node => node.mode !== 'link' && node.newName !== node.name)
    .map(({ doctype, name, newName }) => ({ doctype, from: name, to: newName }));
  const renamed = renameRecords({ records, external_links: {} }, schema, renames).catalog.records;
  const products = new Set(copied.filter(node => node.doctype === 'ilL-Webflow-Product').map(node => node.newName));
  const cleared = [];
  const next = { ...catalog.records };
  const skipped = [];
  let added = 0;
  for (const [doctype, rows] of Object.entries(renamed)) {
    const present = new Set((next[doctype] || []).map(row => isRecord(row) ? recordName(doctype, row, schema) : ''));
    const kept = [];
    for (const original of rows) {
      let row = original;
      if (products.has(row.webflow_product) && doctype !== 'ilL-Webflow-Product') {
        row = { ...row };
        cleared.push({ doctype, name: recordName(doctype, row, schema), product: row.webflow_product });
        delete row.webflow_product;
      }
      const name = recordName(doctype, row, schema);
      if (present.has(name)) { skipped.push({ doctype, name }); continue; }
      present.add(name);
      kept.push(row);
    }
    if (kept.length) { next[doctype] = [...(next[doctype] || []), ...kept]; added += kept.length; }
  }
  return { catalog: { ...catalog, records: next }, added, skipped, cleared };
}
