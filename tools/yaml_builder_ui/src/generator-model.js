// Generating rows from option matrices: every combination of the axes' values becomes a
// row whose fields come from patterns like "EC-{template.default_profile_family}-{style.code}".
// A token names an axis; dotted fields read the value's record and follow its links, so
// {pair.endcap_color.code} reads a Finish Endcap Color record, then its Endcap Color's code.
import { blankRecord, inReference, recordName } from './catalog-model.js';
import { coerceCell, gridColumns, setField } from './grid-model.js';

export const MAX_COMBINATIONS = 2000;
export const TOKEN = /^[A-Za-z_]\w*$/;
const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

/** A record by name from the draft, else the ERPNext reference. */
export function findRecord(doctype, name, catalog, reference, schema) {
  const own = (catalog.records[doctype] || []).find(row => isRecord(row) && recordName(doctype, row, schema) === name);
  return own || reference?.doctypes?.[doctype]?.records?.[name] || null;
}

/** Names available for a DocType: draft records first, then existing ERPNext records. */
export function availableNames(doctype, catalog, reference, schema) {
  const own = (catalog.records[doctype] || []).filter(isRecord).map(row => recordName(doctype, row, schema)).filter(Boolean);
  return [...new Set([...own, ...Object.keys(reference?.doctypes?.[doctype]?.records || {})])];
}

/** Columns a pattern can fill: top-level fields (not child tables or computed names). */
export function patternColumns(doctype, schema) {
  return gridColumns(doctype, schema, [], true).filter(column => column.kind === 'field');
}

/** Read `{token.field.field}` for one combination. Returns { value } or { missing } or { unknown }. */
function tokenValue(path, binding, context) {
  const [token, ...fields] = path.split('.');
  if (!Object.hasOwn(binding, token)) return { unknown: token };
  let { value, doctype } = binding[token];
  for (const field of fields) {
    const record = doctype ? findRecord(doctype, value, context.catalog, context.reference, context.schema) : null;
    const raw = record?.[field];
    if (raw === undefined || raw === null || raw === '') return { missing: path };
    const meta = context.schema.doctypes[doctype]?.fields.find(item => item.fieldname === field);
    doctype = meta?.fieldtype === 'Link' ? meta.options : meta?.fieldtype === 'Dynamic Link' ? record[meta.options] : null;
    value = String(raw);
  }
  return { value };
}

/** Fill a pattern's {tokens}. Returns { text, missing: [paths], unknown: [tokens] }. */
export function expandPattern(pattern, binding, context) {
  const missing = [];
  const unknown = [];
  const text = String(pattern).replace(/\{([^{}]+)\}/g, (_, path) => {
    const result = tokenValue(path.trim(), binding, context);
    if (result.unknown) unknown.push(result.unknown);
    if (result.missing) missing.push(result.missing);
    return result.value ?? '';
  });
  return { text, missing, unknown };
}

/** Problems with a recipe's axes, as text; an empty list means it can generate. */
export function recipeErrors(recipe) {
  const errors = [];
  const tokens = new Set();
  for (const axis of recipe.axes) {
    if (!TOKEN.test(axis.token || '')) errors.push(`Name each axis with letters, digits or _ (not "${axis.token || ''}")`);
    else if (tokens.has(axis.token)) errors.push(`Two axes are named ${axis.token}`);
    tokens.add(axis.token);
  }
  const combinations = recipe.axes.reduce((total, axis) => total * axis.values.length, 1);
  if (combinations > MAX_COMBINATIONS) errors.push(`${combinations} combinations is more than ${MAX_COMBINATIONS}; narrow the axes`);
  return errors;
}

function* combinations(axes) {
  if (!axes.length) { yield []; return; }
  const [first, ...rest] = axes;
  for (const value of first.values) for (const tail of combinations(rest)) yield [value, ...tail];
}

/**
 * Generate one row per combination of the recipe's axes ({ doctype, axes: [{ token, doctype,
 * values }], fields: { fieldname: pattern } }), each starting from the DocType's defaults.
 * Each result: { row, name, binding, missing, unknown, status } where status is 'new', 'draft'
 * (already in the draft), 'erpnext' (already exists), 'repeat' (an earlier row has the name)
 * or 'unnamed'. Only 'new' rows should be added.
 */
export function generateRows(recipe, { catalog, reference, schema }) {
  if (recipeErrors(recipe).length) return [];
  const context = { catalog, reference, schema };
  const columns = new Map(patternColumns(recipe.doctype, schema).map(column => [column.key, column]));
  const patterns = Object.entries(recipe.fields || {}).filter(([field, pattern]) => columns.has(field) && String(pattern ?? '').trim());
  const rule = schema.doctypes[recipe.doctype].autoname || '';
  const needsName = rule === 'prompt' || rule.startsWith('field:');
  const present = new Set((catalog.records[recipe.doctype] || []).filter(isRecord).map(row => recordName(recipe.doctype, row, schema)));
  const seen = new Set();
  const results = [];
  for (const values of combinations(recipe.axes)) {
    const binding = Object.fromEntries(recipe.axes.map((axis, i) => [axis.token, { value: values[i], doctype: axis.doctype || null }]));
    let row = blankRecord(recipe.doctype, schema);
    const missing = [];
    const unknown = [];
    for (const [field, pattern] of patterns) {
      const expanded = expandPattern(pattern, binding, context);
      missing.push(...expanded.missing);
      unknown.push(...expanded.unknown);
      const cell = coerceCell(columns.get(field), expanded.text);
      if (cell.ok) row = setField(row, field, cell.value);
    }
    const name = recordName(recipe.doctype, row, schema);
    const status = needsName && !name ? 'unnamed' : present.has(name) ? 'draft' : inReference(reference, recipe.doctype, name) ? 'erpnext'
      : seen.has(name) ? 'repeat' : 'new';
    if (name) seen.add(name);
    results.push({ row, name, binding: Object.fromEntries(recipe.axes.map((axis, i) => [axis.token, values[i]])),
      missing: [...new Set(missing)], unknown: [...new Set(unknown)], status });
  }
  return results;
}

/** Values of one option type ('Finish', 'Endcap Style', …) allowed by the draft's templates. */
export function allowedOptions(catalog, schema, optionType) {
  const values = [];
  const templates = new Set(Object.values(schema.products).map(product => product.template));
  for (const [doctype, rows] of Object.entries(catalog.records)) {
    if (!templates.has(doctype)) continue;
    const table = schema.doctypes[doctype].fields.find(field => field.fieldname === 'allowed_options');
    const fields = table ? schema.doctypes[table.options]?.fields || [] : [];
    for (const row of rows) for (const option of Array.isArray(row?.allowed_options) ? row.allowed_options : []) {
      if (!isRecord(option) || option.option_type !== optionType || option.is_active === 0) continue;
      const field = fields.find(item => item.fieldtype === 'Link' && item.options === `ilL-Attribute-${optionType}`)
        || fields.find(item => item.fieldtype === 'Dynamic Link');
      const value = field && option[field.fieldname];
      if (value && !values.includes(value)) values.push(String(value));
    }
  }
  return values;
}

/** Option types a template can allow, from its allowed-options child table. */
export function optionTypes(schema) {
  const types = new Set();
  for (const product of Object.values(schema.products)) {
    const table = schema.doctypes[product.template].fields.find(field => field.fieldname === 'allowed_options');
    const select = table && schema.doctypes[table.options]?.fields.find(field => field.fieldname === 'option_type');
    String(select?.options || '').split('\n').filter(Boolean).forEach(type => types.add(type));
  }
  return [...types];
}

const draftNames = (doctype, catalog, schema) => (catalog.records[doctype] || []).filter(isRecord).map(row => recordName(doctype, row, schema)).filter(Boolean);

/**
 * Starting recipes for a DocType, filled from the draft: its templates, their allowed
 * options, and its LED Tape specs. Returns [{ id, label, description, recipe }].
 */
export function presetsFor(doctype, catalog, reference, schema) {
  const product = schema.products[catalog.product_type];
  const template = product?.template;
  const templates = { token: 'template', doctype: template, values: template ? draftNames(template, catalog, schema) : [] };
  const option = (token, type) => ({ token, doctype: `ilL-Attribute-${type}`, values: allowedOptions(catalog, schema, type) });
  const tapes = { token: 'tape', doctype: 'ilL-Spec-LED Tape', values: draftNames('ilL-Spec-LED Tape', catalog, schema) };
  const finishes = allowedOptions(catalog, schema, 'Finish');
  // Endcap colors come from the finishes the templates allow, through Finish Endcap Color records.
  const pairs = { token: 'pair', doctype: 'ilL-Rel-Finish Endcap Color', values: availableNames('ilL-Rel-Finish Endcap Color', catalog, reference, schema)
    .filter(name => finishes.includes(findRecord('ilL-Rel-Finish Endcap Color', name, catalog, reference, schema)?.finish)) };
  const presets = [];
  const add = (id, forType, label, description, axes, fields) => {
    if (forType === doctype && schema.doctypes[doctype]) presets.push({ id, label, description, recipe: { doctype, axes, fields } });
  };
  add('endcap-map', 'ilL-Rel-Endcap-Map', 'Endcap map from allowed options',
    'One row per template, allowed endcap style, and endcap color of an allowed finish.',
    [templates, option('style', 'Endcap Style'), pairs],
    { fixture_template: '{template}', endcap_style: '{style}', endcap_color: '{pair.endcap_color}',
      endcap_item: 'EC-{template.default_profile_family}-{pair.endcap_color.code}-{style.code}', is_active: '1' });
  add('mounting-map', 'ilL-Rel-Mounting-Accessory-Map', 'Mounting map from allowed mounting methods',
    'One row per template and allowed mounting method.',
    [templates, option('method', 'Mounting Method')],
    { template_type: template || '', fixture_template: '{template}', mounting_method: '{method}',
      accessory_item: 'ACC-{template.default_profile_family}-{method.code}', qty_rule_type: 'PER_FIXTURE', is_active: '1' });
  add('driver-eligibility', 'ilL-Rel-Driver-Eligibility', 'Driver eligibility for chosen drivers',
    'One row per template and driver. Choose the drivers on the driver axis.',
    [templates, { token: 'driver', doctype: 'ilL-Spec-Driver', values: [] }],
    { template_type: template || '', fixture_template: '{template}', driver_spec: '{driver}', is_allowed: '1', is_active: '1' });
  add('leader-map', 'ilL-Rel-Leader-Cable-Map', 'Leader cable map for tape specs and feed types',
    "One row per LED Tape spec and allowed power feed type, using each spec's leader cable Item.",
    [tapes, option('feed', 'Power Feed Type')],
    { tape_spec: '{tape}', power_feed_type: '{feed}', leader_item: '{tape.leader_cable_item}', is_active: '1' });
  add('tape-offering', 'ilL-Rel-Tape Offering', 'Tape offerings by CCT and output',
    'One row per LED Tape spec, CCT and output level. Choose the CCTs and output levels.',
    [tapes, { token: 'cct', doctype: 'ilL-Attribute-CCT', values: [] }, { token: 'output', doctype: 'ilL-Attribute-Output Level', values: [] }],
    { tape_spec: '{tape}', cct: '{cct}', output_level: '{output}', led_package: '{tape.led_package}' });
  add('profile-items', 'Item', 'Profile Items by finish',
    "One Item per template and allowed finish, coded from the template's profile family.",
    [templates, option('finish', 'Finish')],
    { item_code: 'CH-{template.default_profile_family}-{finish.code}', item_name: '{template.template_name} profile, {finish}', stock_uom: 'Nos',
      is_stock_item: '1', is_sales_item: '1', is_purchase_item: '1' });
  add('lens-items', 'Item', 'Lens Items by appearance',
    'One Item per template and allowed lens appearance.',
    [templates, option('lens', 'Lens Appearance')],
    { item_code: 'LNS-{template.default_profile_family}-{lens.code}', item_name: '{template.template_name} lens, {lens}', stock_uom: 'Nos',
      is_stock_item: '1', is_sales_item: '1', is_purchase_item: '1' });
  add('endcap-items', 'Item', 'Endcap Items by color and style',
    'One Item per template, endcap color of an allowed finish, and allowed endcap style.',
    [templates, pairs, option('style', 'Endcap Style')],
    { item_code: 'EC-{template.default_profile_family}-{pair.endcap_color.code}-{style.code}', item_name: '{template.template_name} endcap, {pair.endcap_color} {style}',
      stock_uom: 'Nos', is_stock_item: '1', is_sales_item: '1', is_purchase_item: '1' });
  return presets;
}

/** The recipe to save: axes keep their values, so a recipe reproduces the same rows. */
export function cleanRecipe(recipe, name) {
  return {
    name, doctype: recipe.doctype,
    axes: recipe.axes.map(axis => ({ token: axis.token, ...(axis.doctype ? { doctype: axis.doctype } : {}), values: [...axis.values] })),
    fields: Object.fromEntries(Object.entries(recipe.fields).filter(([, pattern]) => String(pattern ?? '').trim())),
  };
}

/** Saved recipes in a draft (catalog.builder.recipes), tolerating a missing or malformed key. */
export function savedRecipes(catalog, doctype = null) {
  const recipes = Array.isArray(catalog.builder?.recipes) ? catalog.builder.recipes : [];
  return recipes.filter(recipe => isRecord(recipe) && typeof recipe.name === 'string' && Array.isArray(recipe.axes) && isRecord(recipe.fields)
    && (!doctype || recipe.doctype === doctype));
}

/** The draft with a recipe saved (replacing one of the same name and DocType) or removed (recipe null). */
export function withRecipe(catalog, doctype, name, recipe) {
  const others = savedRecipes(catalog).filter(item => !(item.doctype === doctype && item.name === name));
  const recipes = recipe ? [...others, recipe] : others;
  const next = { ...catalog };
  if (recipes.length) next.builder = { ...(isRecord(catalog.builder) ? catalog.builder : {}), recipes };
  else delete next.builder;
  return next;
}
