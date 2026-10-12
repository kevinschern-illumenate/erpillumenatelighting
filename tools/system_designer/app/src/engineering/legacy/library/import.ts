import Papa from 'papaparse';
import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import { WireTypeSchema, type WireType } from '@ill/core-schemas/wire';
import { seedProducts, seedWires } from '@ill/data/seeds';

export type LibraryKind = 'products' | 'wires';
export type LibraryRow = CatalogItem | WireType;
export type ImportRow = {
  row: number;
  key: string;
  action: 'new' | 'updated' | 'unchanged' | 'error';
  value?: LibraryRow;
  errors: string[];
};
export const normalizeHeader = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
export function flatten(
  value: unknown,
  prefix = '',
  result: Record<string, string> = {},
): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result;
  for (const [key, v] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (['specs.available', 'sourceData'].includes(path)) result[path] = JSON.stringify(v);
    else if (v !== null && typeof v === 'object' && !Array.isArray(v)) flatten(v, path, result);
    else if (v !== undefined) result[path] = typeof v === 'string' ? v : JSON.stringify(v);
  }
  return result;
}
export function fieldsFor(kind: LibraryKind): string[] {
  const examples = kind === 'products' ? seedProducts : seedWires;
  return [
    ...new Set([
      ...examples.flatMap((row) => Object.keys(flatten(row))),
      ...(kind === 'products'
        ? [
            'erpItemCode',
            'sourceData',
            'specs',
            'specs.intendedKind',
            'specs.available',
            'specs.missingFields',
            'specs.notes',
            'specs.acInputVMin',
            'specs.acInputVMax',
            'specs.dcInputVMin',
            'specs.dcInputVMax',
            'specs.maxInputAType',
            'specs.maxWPerChannel',
            'specs.maxWTotal',
            'specs.outputDimming',
          ]
        : []),
    ]),
  ];
}
export function autoMap(headers: string[], fields: string[]): Record<string, string> {
  const aliases: Record<string, string> = {
    itemcode: 'sku',
    itemname: 'model',
    itemgroup: 'category',
    manufacturer: 'brand',
    watts: 'specs.ratedW',
    voltage: 'specs.outputV',
  };
  return Object.fromEntries(
    headers.map((h) => [
      h,
      fields.find((f) => normalizeHeader(f) === normalizeHeader(h)) ??
        aliases[normalizeHeader(h)] ??
        fields.find(
          (f) => normalizeHeader(f).endsWith(normalizeHeader(h)) && normalizeHeader(h).length >= 5,
        ) ??
        '',
    ]),
  );
}
export function readCsv(text: string): {
  headers: string[];
  rows: Record<string, string>[];
  errors: string[];
} {
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: 'greedy',
    transformHeader: (h) => h.trim(),
  });
  return {
    headers: parsed.meta.fields ?? [],
    rows: parsed.data,
    errors: parsed.errors.map((e) => `Row ${(e.row ?? 0) + 2}: ${e.message}`),
  };
}
function setPath(target: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split('.');
  if (keys.some((k) => ['__proto__', 'constructor', 'prototype'].includes(k)))
    throw new Error('Unsafe field path');
  let cursor = target;
  keys.forEach((key, i) => {
    if (i === keys.length - 1) cursor[key] = value;
    else {
      if (typeof cursor[key] !== 'object' || cursor[key] === null) cursor[key] = {};
      cursor = cursor[key] as Record<string, unknown>;
    }
  });
}
function valueAtPath(value: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (v, k) => (v && typeof v === 'object' ? (v as Record<string, unknown>)[k] : undefined),
      value,
    );
}
function coerce(path: string, value: string, sample: LibraryRow, kind: LibraryKind): unknown {
  if (
    ['specs', 'specs.available', 'specs.missingFields', 'specs.notes', 'sourceData'].includes(path)
  )
    return JSON.parse(value);
  // Optional fields may exist only on another example in the same library.
  const exemplar =
    valueAtPath(sample, path) ??
    (kind === 'products' ? seedProducts : seedWires)
      .map((row) => valueAtPath(row, path))
      .find((v) => v !== undefined);
  // Some numeric fields also accept ranges (for example fixture inputV).
  if (
    Array.isArray(exemplar) ||
    value.trim().startsWith('[') ||
    (exemplar && typeof exemplar === 'object')
  )
    return JSON.parse(value);
  if (
    typeof exemplar === 'number' ||
    /(?:\.)(?:acInputVMin|acInputVMax|dcInputVMin|dcInputVMax|maxWPerChannel|maxWTotal|maxInputA|maxInputAAtV|inrushA|maxUnitsPer20ABreaker|reelLengthFt|maxPixels|maxUniverses|maxDataLengthFt|maxBusDevices)$/.test(
      path,
    ) ||
    ['costPerFt', 'odIn', 'ampacityA', 'resistanceOhmPerKft', 'impedanceOhm'].includes(path)
  )
    return value.trim() === '' ? undefined : Number(value);
  if (typeof exemplar === 'boolean' || ['isExample', 'verify'].includes(path))
    return value === 'true' ? true : value === 'false' ? false : value;
  return value;
}
export function previewImport(
  kind: LibraryKind,
  rows: Record<string, string>[],
  mapping: Record<string, string>,
  existing: LibraryRow[],
): ImportRow[] {
  const keys = new Set<string>();
  return rows.map((row, index) => {
    let key = '';
    try {
      const mapped = Object.entries(mapping).filter(([, v]) => v);
      const targets = mapped.map(([, f]) => f);
      if (new Set(targets).size !== targets.length)
        throw new Error('Two columns map to the same field');
      if (
        targets.some((target) =>
          targets.some((other) => other !== target && other.startsWith(`${target}.`)),
        )
      )
        throw new Error('Do not map both a whole object and one of its nested fields');
      const keyField = kind === 'products' ? 'sku' : 'id';
      const keyHeader = mapped.find(([, f]) => f === keyField)?.[0];
      key = (keyHeader ? row[keyHeader] : '')?.trim() ?? '';
      if (!key) throw new Error(`Map and supply ${keyField}`);
      if (keys.has(key)) throw new Error(`Duplicate ${keyField} in this import: ${key}`);
      keys.add(key);
      const old = existing.find((r) =>
        keyField === 'sku' ? 'sku' in r && r.sku === key : r.id === key,
      );
      const next: Record<string, unknown> = old ? structuredClone(old) : {};
      const categoryHeader = mapped.find(([, f]) => f === 'category')?.[0];
      const category = categoryHeader ? row[categoryHeader] : old?.category;
      const specsKindHeader = mapped.find(([, f]) => f === 'specs.kind')?.[0];
      // Changing record state replaces the discriminator object; old full/draft fields must not leak.
      if (
        specsKindHeader &&
        row[specsKindHeader] &&
        old &&
        'specs' in old &&
        row[specsKindHeader] !== old.specs.kind
      )
        next.specs = {};
      const sample =
        (kind === 'products'
          ? seedProducts.find((p) => p.category === category)
          : seedWires.find((w) => w.category === category)) ??
        (kind === 'products' ? seedProducts[0] : seedWires[0]);
      for (const [header, field] of mapped) {
        const cell = row[header];
        if (cell !== undefined && cell !== '')
          setPath(next, field, coerce(field, cell, sample!, kind));
      }
      const freeHeader = mapped.find(([, f]) => f === 'specs.freeCutting')?.[0];
      const intervalHeader = mapped.find(([, f]) => f === 'specs.cutIntervalIn')?.[0];
      if (
        kind === 'products' &&
        freeHeader &&
        row[freeHeader] === 'true' &&
        (!intervalHeader || !row[intervalHeader]?.trim()) &&
        next.specs &&
        typeof next.specs === 'object'
      )
        delete (next.specs as Record<string, unknown>).cutIntervalIn;
      if (kind === 'products') {
        next.id = old?.id ?? next.id ?? `catalog-${key}`;
        if (next.isExample === undefined) next.isExample = false;
      }
      const schema = kind === 'products' ? CatalogItemSchema : WireTypeSchema;
      const result = schema.safeParse(next);
      if (!result.success)
        return {
          row: index + 2,
          key,
          action: 'error',
          errors: result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`),
        };
      const unchanged =
        old && JSON.stringify(flatten(old)) === JSON.stringify(flatten(result.data));
      return {
        row: index + 2,
        key,
        action: old ? (unchanged ? 'unchanged' : 'updated') : 'new',
        value: result.data,
        errors: [],
      };
    } catch (error) {
      return {
        row: index + 2,
        key,
        action: 'error',
        errors: [error instanceof Error ? error.message : 'Invalid value'],
      };
    }
  });
}
export function commitImport(existing: LibraryRow[], preview: ImportRow[]): LibraryRow[] {
  if (preview.some((r) => r.action === 'error'))
    throw new Error('Fix all import errors before committing');
  const next = new Map(existing.map((r) => [r.id, r]));
  preview.forEach((r) => {
    if (r.value) next.set(r.value.id, r.value);
  });
  return [...next.values()];
}
export function exportCsv(rows: LibraryRow[]): string {
  const flat = rows.map((r) => flatten(r));
  const fields = [...new Set(flat.flatMap(Object.keys))];
  return Papa.unparse(
    { fields, data: flat.map((r) => fields.map((f) => r[f] ?? '')) },
    { escapeFormulae: true },
  );
}
