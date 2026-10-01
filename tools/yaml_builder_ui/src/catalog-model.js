export function recordName(doctype, row, schema) {
  const rule = schema.doctypes[doctype]?.autoname || '';
  if (rule.startsWith('field:')) return String(row[rule.slice(6)] || '');
  if (rule.startsWith('format:')) return rule.slice(7).replace(/\{([^}]+)\}/g, (_, field) => String(row[field] ?? ''));
  return String(row.name || '');
}

export function blankRecord(doctype, schema) {
  const row = {};
  for (const field of schema.doctypes[doctype].fields) {
    if (field.default === undefined || field.read_only) continue;
    const numeric = ['Int', 'Float', 'Currency', 'Percent', 'Check'].includes(field.fieldtype);
    if (numeric && !Number.isFinite(Number(field.default))) continue;
    row[field.fieldname] = numeric ? Number(field.default) : field.default;
  }
  return row;
}

export function emptyCatalog(productType = 'fixture') {
  return { schema_version: 2, product_type: productType, series_name: '', records: {}, external_links: {} };
}

export function parseCatalog(text, parse, schema) {
  const value = parse(text);
  if (!value || value.schema_version !== 2 || !schema.products[value.product_type]
      || !value.records || Array.isArray(value.records) || typeof value.records !== 'object') {
    throw new Error('Choose a version 2 product catalog YAML file. Legacy family files use the family expansion editor.');
  }
  for (const [doctype, rows] of Object.entries(value.records)) {
    if (!schema.doctypes[doctype] || schema.doctypes[doctype].istable || !Array.isArray(rows)
        || rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error(`Invalid records for ${doctype}`);
    }
  }
  if (value.external_links && (Array.isArray(value.external_links) || typeof value.external_links !== 'object'
      || Object.values(value.external_links).some(names => !Array.isArray(names) || names.some(name => typeof name !== 'string')))) {
    throw new Error('External links must list existing record names for each DocType.');
  }
  return { ...value, external_links: value.external_links || {} };
}

export function linkedRecords(doctype, row, schema, prefix = '') {
  const result = [];
  for (const field of schema.doctypes[doctype].fields) {
    const value = row[field.fieldname];
    if (value === undefined || value === null || value === '') continue;
    const path = `${prefix}${field.fieldname}`;
    if (['Table', 'Table MultiSelect'].includes(field.fieldtype)) {
      if (Array.isArray(value)) value.forEach((child, i) => {
        if (child && typeof child === 'object') result.push(...linkedRecords(field.options, child, schema, `${path}[${i}].`));
      });
    } else if (['Link', 'Dynamic Link'].includes(field.fieldtype)) {
      const target = field.fieldtype === 'Link' ? field.options : row[field.options];
      if (target !== 'DocType') result.push({ doctype: target || '', name: String(value), path });
    }
  }
  return result;
}

/** True when an ERPNext export (erp-reference.json) lists this record. */
export function inReference(reference, doctype, name) {
  return Boolean(reference?.doctypes?.[doctype]?.records && Object.hasOwn(reference.doctypes[doctype].records, name));
}

/** A short, human description of an existing ERPNext record for pickers. */
export function referenceSummary(doctype, record, schema, limit = 4) {
  const fields = schema.doctypes[doctype]?.fields || [];
  const naming = (schema.doctypes[doctype]?.autoname || '').replace(/^field:/, '');
  return fields.filter(field => field.fieldname !== naming && ['Data', 'Link', 'Select', 'Int', 'Float'].includes(field.fieldtype)
      && record?.[field.fieldname] !== undefined && record[field.fieldname] !== '' && record[field.fieldname] !== 0)
    .slice(0, limit).map(field => `${field.label || field.fieldname}: ${record[field.fieldname]}`).join(' · ');
}

export function unresolvedLinks(catalog, schema, reference = null) {
  const known = new Set();
  for (const [doctype, rows] of Object.entries(catalog.records)) {
    rows.forEach(row => known.add(JSON.stringify([doctype, recordName(doctype, row, schema)])));
  }
  const missing = new Map();
  for (const [doctype, rows] of Object.entries(catalog.records)) rows.forEach((row, i) => {
    linkedRecords(doctype, row, schema).forEach(link => {
      const key = JSON.stringify([link.doctype, link.name]);
      if (!known.has(key) && !catalog.external_links?.[link.doctype]?.includes(link.name)
          && !inReference(reference, link.doctype, link.name)) {
        if (!missing.has(key)) missing.set(key, { ...link, sources: [] });
        missing.get(key).sources.push(`${doctype}[${i}].${link.path}`);
      }
    });
  });
  return [...missing.values()];
}

/**
 * Declare every link that resolves to an exported ERPNext record, so the YAML
 * stays self-contained for the CLI and reviewers see what it depends on.
 */
export function withReferenceLinks(catalog, schema, reference) {
  if (!reference) return catalog;
  const known = new Set();
  for (const [doctype, rows] of Object.entries(catalog.records)) {
    rows.forEach(row => known.add(JSON.stringify([doctype, recordName(doctype, row, schema)])));
  }
  const external = Object.fromEntries(Object.entries(catalog.external_links || {}).map(([doctype, names]) => [doctype, [...names]]));
  for (const [doctype, rows] of Object.entries(catalog.records)) rows.forEach(row => {
    if (!row || typeof row !== 'object') return;
    for (const link of linkedRecords(doctype, row, schema)) {
      if (!link.doctype || known.has(JSON.stringify([link.doctype, link.name])) || !inReference(reference, link.doctype, link.name)) continue;
      external[link.doctype] ||= [];
      if (!external[link.doctype].includes(link.name)) external[link.doctype].push(link.name);
    }
  });
  return { ...catalog, external_links: external };
}

/** Declared existing records missing from a fully exported DocType: likely typos. */
export function unconfirmedLinks(catalog, reference) {
  return Object.entries(catalog.external_links || {}).flatMap(([doctype, names]) =>
    reference?.doctypes?.[doctype]?.source === 'export'
      ? names.filter(name => !inReference(reference, doctype, name)).map(name => ({ doctype, name })) : []);
}

export function catalogIssues(catalog, schema, reference = null) {
  const issues = [];
  function inspect(doctype, row, path) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) { issues.push(`${path}: expected a record`); return; }
    const fields = schema.doctypes[doctype].fields;
    Object.keys(row).filter(key => key !== 'name' && !fields.some(f => f.fieldname === key))
      .forEach(key => issues.push(`${path}.${key}: unknown field`));
    const defaults = blankRecord(doctype, schema);
    for (const field of fields) {
      const value = row[field.fieldname] ?? defaults[field.fieldname];
      const location = `${path}.${field.fieldname}`;
      if (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)) {
        if (field.reqd) issues.push(`${location}: required`);
        continue;
      }
      if (['Table', 'Table MultiSelect'].includes(field.fieldtype)) {
        if (!Array.isArray(value)) issues.push(`${location}: expected child rows`);
        else value.forEach((child, i) => inspect(field.options, child, `${location}[${i}]`));
      } else if (['Int', 'Float', 'Currency', 'Percent'].includes(field.fieldtype)) {
        if (typeof value !== 'number' || !Number.isFinite(value)) issues.push(`${location}: enter a finite number`);
        else if (field.fieldtype === 'Int' && !Number.isInteger(value)) issues.push(`${location}: enter a whole number`);
      } else if (field.fieldtype === 'Select' && !field.options?.split('\n').includes(value)) {
        issues.push(`${location}: unsupported choice`);
      } else if (field.fieldtype === 'Check') {
        if (![0, 1, true, false].includes(value)) issues.push(`${location}: expected a checkbox value`);
      } else if (field.fieldtype === 'JSON') {
        try { if (typeof value === 'string') JSON.parse(value); } catch { issues.push(`${location}: invalid JSON`); }
      } else if (typeof value !== 'string') issues.push(`${location}: expected text`);
    }
  }
  const template = schema.products[catalog.product_type]?.template;
  if (!catalog.records[template]?.length) issues.push(`Add at least one ${template}`);
  for (const [doctype, rows] of Object.entries(catalog.records)) {
    const names = new Set();
    rows.forEach((row, i) => {
      inspect(doctype, row, `${doctype}[${i}]`);
      const name = recordName(doctype, row, schema);
      const rule = schema.doctypes[doctype].autoname || '';
      if (!name && (rule === 'prompt' || rule.startsWith('field:'))) issues.push(`${doctype}[${i}]: record name is required`);
      if (name && names.has(name)) issues.push(`${doctype}: duplicate record ${name}`);
      if (name && inReference(reference, doctype, name)) {
        issues.push(`${doctype}[${i}]: ${name} already exists in ERPNext; remove it and link to the existing record`);
      }
      names.add(name);
    });
  }
  for (const link of unresolvedLinks(catalog, schema, reference)) issues.push(`${link.sources[0]}: unresolved ${link.doctype} / ${link.name}`);
  return issues;
}

export function makeItemRecords(catalog, schema, reference = null) {
  const result = structuredClone(catalog);
  const missing = unresolvedLinks(result, schema, reference).filter(link => link.doctype === 'Item');
  if (!missing.length) return result;
  result.records.Item ||= [];
  for (const link of missing) result.records.Item.push({
    ...blankRecord('Item', schema), item_code: link.name, item_name: link.name,
    stock_uom: (result.records['ilL-Spec-LED Tape'] || []).some(spec => spec.item === link.name) ? 'Meter' : 'Nos',
  });
  return result;
}
