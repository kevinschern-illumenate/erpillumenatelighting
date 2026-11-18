/**
 * Talking to the Command Center when the builder runs inside its Catalog tab (an iframe on the
 * same site). Pure helpers, so the rules are unit-tested without a browser.
 *
 * Builder → Command Center (only when framed, always to our own origin):
 *   {source: 'ill-catalog-builder', type: 'ready'}
 *   {source: 'ill-catalog-builder', type: 'dirty', dirty: bool}
 *   {source: 'ill-catalog-builder', type: 'imported', name: <ilL-Catalog-Import receipt>, created: n}
 * Command Center → builder (same origin, from the parent frame only):
 *   {source: 'ill-command-center', type: 'open', records: [{doctype, name}, ...]}
 *   {source: 'ill-command-center', type: 'new', doctype}
 * `/catalog-builder?open=<doctype>:<name>` (repeatable, or comma-separated) behaves like `open`.
 */
import { recordName } from './catalog-model.js';

export const BUILDER_SOURCE = 'ill-catalog-builder';
export const PARENT_SOURCE = 'ill-command-center';
const MAX_OPEN = 200;

/** Post a message to the Command Center; a no-op when the builder is not framed. */
export function notifyParent(win, message) {
  try {
    if (!win || !win.parent || win.parent === win) return false;
    win.parent.postMessage({ source: BUILDER_SOURCE, ...message }, win.location.origin);
    return true;
  } catch { return false; }
}

/** The message's data when it is from the framing Command Center on this site, else null. */
export function parentMessage(event, win) {
  if (!event || !win || !win.parent || win.parent === win) return null;
  if (event.origin !== win.location.origin || event.source !== win.parent) return null;
  const data = event.data;
  if (!data || typeof data !== 'object' || data.source !== PARENT_SOURCE) return null;
  return data;
}

/** [{doctype, name}] from an `open` message or the ?open= parameter, deduplicated and capped. */
export function openList(records) {
  const out = [];
  const seen = new Set();
  for (const row of Array.isArray(records) ? records : []) {
    const doctype = typeof row?.doctype === 'string' ? row.doctype.trim() : '';
    const name = typeof row?.name === 'string' ? row.name.trim() : '';
    const key = JSON.stringify([doctype, name]);
    if (!doctype || !name || seen.has(key)) continue;
    seen.add(key);
    out.push({ doctype, name });
    if (out.length >= MAX_OPEN) break;
  }
  return out;
}

/** `?open=ilL-Fixture-Template:ABC&open=Item:X,Item:Y` → [{doctype, name}]. The first ":" splits. */
export function openParam(search) {
  const params = new URLSearchParams(search || '');
  const rows = params.getAll('open').flatMap(value => value.split(',')).map(part => {
    const at = part.indexOf(':');
    return at > 0 ? { doctype: part.slice(0, at), name: part.slice(at + 1) } : null;
  });
  return openList(rows);
}

/** True for a DocType the builder can hold records of (a catalog parent DocType). */
export const editable = (doctype, schema) => Boolean(schema.doctypes[doctype] && !schema.doctypes[doctype].istable);

/**
 * The product draft a DocType belongs in: the active product when the DocType is part of it,
 * else the first product whose template is that DocType, else whose spec is, else whose family
 * (familyTypes) includes it. Anything else stays in the active product's draft, under Other DocTypes.
 */
export function productFor(doctype, schema, active, familyTypes) {
  const products = Object.entries(schema.products);
  const family = key => {
    const product = schema.products[key];
    return [product.template, product.spec, ...familyTypes(product, schema)];
  };
  if (schema.products[active] && family(active).includes(doctype)) return active;
  for (const test of [p => p.template === doctype, p => p.spec === doctype, (p, key) => family(key).includes(doctype)]) {
    const hit = products.find(([key, product]) => test(product, key));
    if (hit) return hit[0];
  }
  return schema.products[active] ? active : products[0][0];
}

/**
 * Add fetched ERPNext records to a draft as-is (under their current names). Records whose name is
 * already in the draft are skipped. Returns the new catalog and what was added or skipped.
 */
export function addAsIs(catalog, rows, schema) {
  const records = { ...catalog.records };
  const added = [];
  const skipped = [];
  for (const { doctype, name, record } of rows) {
    const current = records[doctype] || [];
    if (current.some(row => recordName(doctype, row, schema) === name)) { skipped.push({ doctype, name }); continue; }
    records[doctype] = [...current, structuredClone(record)];
    added.push({ doctype, name });
  }
  return { catalog: added.length ? { ...catalog, records } : catalog, added, skipped };
}
