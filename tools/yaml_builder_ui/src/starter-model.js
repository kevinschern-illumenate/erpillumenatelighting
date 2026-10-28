// Starting a new product from a starter: a built-in example, or a draft saved in this browser.
// A starter is a complete draft plus the code, series and product name its records are named
// with; applying it rewrites those everywhere, so every name and link follows the new product.
// Catalogs are never mutated; every function returns new objects so undo can keep snapshots.
import { inReference, isComplete, recordName } from './catalog-model.js';

export const STARTERS = 'illumenate-catalog-starters-v1';
const TABLES = new Set(['Table', 'Table MultiSelect']);
const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Built-in starters are the examples. Their names use code DEMO, series "Example Series",
 * product name "Example <label>", and an "Example" prefix on other names.
 */
export function builtinStarters(examples, schema) {
  return Object.keys(schema.products).filter(type => examples[type]).map(type => ({
    id: `example:${type}`, label: `${schema.products[type].label} starter`, productType: type, builtin: true,
    catalog: examples[type], code: 'DEMO', series: examples[type].series_name, name: `Example ${schema.products[type].label}`, prefix: 'Example',
  }));
}

export function readStarters() {
  try {
    const saved = JSON.parse(localStorage.getItem(STARTERS));
    return Array.isArray(saved) ? saved.filter(item => item && typeof item.id === 'string' && isRecord(item.catalog?.records) && item.code) : [];
  } catch { return []; }
}

export function writeStarters(starters) {
  try { localStorage.setItem(STARTERS, JSON.stringify(starters)); return true; } catch { return false; }
}

/** A starter saved from a draft; `code`, `series` and `name` are what the draft's names use now. */
export function draftStarter(catalog, { label, code, series, name }, savedOn) {
  const copy = structuredClone(catalog);
  delete copy.add_to_reference;
  return { id: `saved:${savedOn}:${label}`, label, productType: catalog.product_type, catalog: copy,
    code: code.trim(), series: series.trim(), name: name.trim(), saved_on: savedOn };
}

/** The template's name in a draft, the usual product name for a saved starter. */
export function templateName(catalog, schema) {
  const template = schema.products[catalog.product_type]?.template;
  return String(catalog.records[template]?.[0]?.template_name || '');
}

/** The product name when none is typed: the starter's name under the new series. */
export function defaultName(starter, series) {
  const base = starter.prefix ? starter.name.replace(new RegExp(`^${escape(starter.prefix)}\\s*`), '') : starter.name;
  if (starter.series && base.includes(starter.series)) return base.replace(starter.series, series);
  return `${series} ${base}`.trim();
}

/**
 * A function renaming a starter's text for a new product: its product name, series, name
 * prefix and code, in one pass so a replacement is never renamed again. Longer text wins where
 * matches overlap. The code matches only where it is not part of a longer code (LX2 never
 * matches inside LX20 or FLX2), in upper and lower case so slugs follow.
 */
export function starterRenamer(starter, { code, series, name }) {
  const series_ = series.trim();
  const rules = [];
  const add = (find, replace, after) => {
    if (find && find !== replace && !rules.some(rule => rule.find === find)) rules.push({ find, replace, after });
  };
  add(starter.name, name.trim() || defaultName(starter, series_), '(?![A-Za-z0-9])');
  add(starter.series, series_, '(?![A-Za-z0-9])');
  if (starter.prefix) add(starter.prefix, series_, '(?![A-Za-z0-9])');
  const to = code.trim();
  if (starter.code && to) {
    add(starter.code, to, '(?![0-9])');
    add(starter.code.toLowerCase(), to.toLowerCase(), '(?![0-9])');
  }
  if (!rules.length) return text => text;
  rules.sort((a, b) => b.find.length - a.find.length);
  const pattern = new RegExp(rules.map(rule => `(?<![A-Za-z0-9])(${escape(rule.find)})${rule.after}`).join('|'), 'g');
  return text => text.replace(pattern, (...groups) => rules[groups.slice(1, rules.length + 1).findIndex(group => group !== undefined)].replace);
}

function rewrite(value, rename) {
  if (typeof value === 'string') return rename(value);
  if (Array.isArray(value)) return value.map(item => rewrite(item, rename));
  if (isRecord(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rewrite(item, rename)]));
  return value;
}

/** Point Link fields (and child rows) that hold `from` for DocType `target` at `to`. */
function relink(doctype, row, schema, target, from, to) {
  const next = { ...row };
  for (const field of schema.doctypes[doctype]?.fields || []) {
    const value = row[field.fieldname];
    if (TABLES.has(field.fieldtype) && Array.isArray(value)) {
      next[field.fieldname] = value.map(child => isRecord(child) ? relink(field.options, child, schema, target, from, to) : child);
    } else if (value === from && ((field.fieldtype === 'Link' && field.options === target) || (field.fieldtype === 'Dynamic Link' && row[field.options] === target))) {
      next[field.fieldname] = to;
    }
  }
  return next;
}

/**
 * Existing records a starter links to that a complete ERPNext list does not have, such as the
 * example's EXISTING-96W-DRIVER. Each comes with the existing names to choose instead.
 */
export function placeholders(catalog, reference) {
  return Object.entries(catalog.external_links || {}).flatMap(([doctype, names]) => {
    const entry = reference?.doctypes?.[doctype];
    if (!isComplete(entry)) return [];
    return names.filter(name => !inReference(reference, doctype, name))
      .map(name => ({ doctype, name, choices: Object.keys(entry.records).sort() }));
  });
}

/**
 * The draft a starter makes for a new product. `picks` maps `${doctype}\n${name}` of a
 * placeholder to the existing record to link instead. Attribute records whose new name already
 * exists in ERPNext (the series, a finish) are left out, so links use the existing record.
 * Returns { catalog, reused: [{ doctype, name }], count }.
 */
export function applyStarter(starter, values, { schema, reference = null, picks = new Map() }) {
  const rename = starterRenamer(starter, values);
  const source = starter.catalog;
  let records = rewrite(source.records, rename);
  const external = rewrite(source.external_links || {}, rename);
  for (const [id, to] of picks) {
    const [doctype, from] = id.split('\n');
    if (!to || to === from) continue;
    records = Object.fromEntries(Object.entries(records).map(([type, rows]) => [type, rows.map(row => isRecord(row) ? relink(type, row, schema, doctype, from, to) : row)]));
    if (external[doctype]) external[doctype] = [...new Set(external[doctype].map(name => name === from ? to : name))];
  }
  const reused = [];
  for (const [doctype, rows] of Object.entries(records)) {
    if (!doctype.startsWith('ilL-Attribute-')) continue;
    const kept = rows.filter(row => {
      const name = recordName(doctype, row, schema);
      if (!name || !inReference(reference, doctype, name)) return true;
      reused.push({ doctype, name });
      external[doctype] = [...new Set([...(external[doctype] || []), name])];
      return false;
    });
    if (kept.length) records[doctype] = kept; else delete records[doctype];
  }
  const catalog = { ...structuredClone(source), records, external_links: external, product_type: starter.productType, series_name: values.series.trim() };
  delete catalog.add_to_reference;
  const count = Object.values(records).reduce((sum, rows) => sum + rows.length, 0);
  return { catalog, reused, count };
}

/** [{ doctype, name, exists }] for every record a starter would create, for review before applying. */
export function starterPreview(catalog, schema, reference) {
  return Object.entries(catalog.records).flatMap(([doctype, rows]) => rows.map(row => {
    const name = recordName(doctype, row, schema);
    return { doctype, name, exists: Boolean(name) && inReference(reference, doctype, name) };
  }));
}
