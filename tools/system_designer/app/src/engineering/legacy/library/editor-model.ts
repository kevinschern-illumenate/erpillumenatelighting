import { CatalogItemSchema, CatalogSpecsSchema } from '@ill/core-schemas/catalog';
import { WireTypeSchema } from '@ill/core-schemas/wire';
import { intendedKind, specSections } from './editor-fields';
import type { LibraryKind } from './import';

export type EditorRecord = Record<string, unknown>;
export const record = (value: unknown): EditorRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as EditorRecord) : {};
export function at(value: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (v, key) => (v && typeof v === 'object' ? (v as EditorRecord)[key] : undefined),
      value,
    );
}
export function updateField(value: EditorRecord, path: string, next: unknown): EditorRecord {
  const result = structuredClone(value);
  const keys = path.split('.');
  if (keys.some((k) => ['__proto__', 'constructor', 'prototype'].includes(k)))
    throw new Error('Invalid field');
  let cursor = result;
  for (const key of keys.slice(0, -1)) {
    if (!cursor[key] || typeof cursor[key] !== 'object') cursor[key] = {};
    cursor = cursor[key] as EditorRecord;
  }
  if (next === undefined) delete cursor[keys.at(-1)!];
  else cursor[keys.at(-1)!] = next;
  if (keys.at(-1) === 'freeCutting' && next === true) delete cursor.cutIntervalIn;
  if (keys.at(-1) === 'powerType' && next === 'DC') delete cursor.outputDimming;
  if (keys.at(-1) === 'inputType' && (next === 'AC' || next === 'DC')) {
    if (cursor.maxInputAType && cursor.maxInputAType !== next) {
      delete cursor.maxInputA;
      delete cursor.maxInputAAtV;
    }
    const prefix = next.toLowerCase();
    if (cursor[`${prefix}InputVMin`] !== undefined) cursor.inputVMin = cursor[`${prefix}InputVMin`];
    if (cursor[`${prefix}InputVMax`] !== undefined) cursor.inputVMax = cursor[`${prefix}InputVMax`];
    for (const key of ['acInputVMin', 'acInputVMax', 'dcInputVMin', 'dcInputVMax', 'maxInputAType'])
      delete cursor[key];
  }
  // Optional compound fields disappear when their last value is cleared.
  for (const optional of ['specs.pixel', 'specs.available.pixel', 'source']) {
    const child = at(result, optional);
    if (child && typeof child === 'object' && !Object.keys(child).length) {
      const parts = optional.split('.');
      const parent = parts.length === 1 ? result : record(at(result, parts.slice(0, -1).join('.')));
      delete parent[parts.at(-1)!];
    }
  }
  if (path.startsWith('manufacturerRefChecks')) {
    const checks = Array.isArray(result.manufacturerRefChecks) ? result.manufacturerRefChecks : [];
    result.manufacturerRefChecks = checks.map((c) => ({ ...record(c), verify: true }));
    result.manufacturerRefs = checks.map((c) => record(c).reference ?? '');
  }
  return result;
}
export function newLibraryItem(kind: LibraryKind, id: string): EditorRecord {
  if (kind === 'wires')
    return {
      id,
      name: '',
      category: 'class2-power',
      manufacturerRefs: [],
      manufacturerRefChecks: [],
      applications: [],
      conductors: [],
      notes: '',
      isExample: false,
      verify: true,
      source: { kind: 'user-supplied', reference: '' },
    };
  return {
    id,
    sku: '',
    brand: 'ilLumenate Lighting',
    model: '',
    category: 'psu',
    description: '',
    isExample: false,
    localOverrides: [],
    specs: {
      kind: 'incomplete',
      intendedKind: 'psu',
      available: {},
      missingFields: ['Specifications'],
      notes: [],
    },
  };
}
export function fullProduct(item: EditorRecord): EditorRecord {
  const specs = record(item.specs);
  return specs.kind === 'incomplete'
    ? {
        ...item,
        specs: {
          ...(specs.intendedKind === 'decoder' ? { dmxThru: true } : {}),
          ...record(specs.available),
          kind: specs.intendedKind,
        },
      }
    : item;
}
export function incompleteProduct(item: EditorRecord): EditorRecord {
  const full = fullProduct(item),
    spec = record(full.specs),
    previous = record(item.specs);
  const kind = String(spec.kind ?? intendedKind(item.category));
  const checked = CatalogSpecsSchema.safeParse(spec);
  const missing = checked.success
    ? []
    : checked.error.issues.map((i) => i.path.join('.') || 'Specifications');
  if (checked.success) {
    const categoryCheck = CatalogItemSchema.safeParse(full);
    if (!categoryCheck.success)
      missing.push(
        ...categoryCheck.error.issues
          .filter((i) => i.path[0] === 'specs')
          .map((i) => i.path.slice(1).join('.')),
      );
  }
  const known = new Set(
    (specSections[kind] ?? []).flatMap((section) =>
      section.fields.map((field) => field.key.split('.')[0]),
    ),
  );
  const unresolved =
    previous.kind === 'incomplete' && Array.isArray(previous.missingFields)
      ? previous.missingFields.filter(
          (field): field is string =>
            typeof field === 'string' &&
            !known.has(field.split(/[.[]/)[0]!) &&
            !['Specifications', 'Specification review'].includes(field),
        )
      : [];
  const available = structuredClone(spec);
  delete available.kind;
  return {
    ...item,
    specs: {
      kind: 'incomplete',
      intendedKind: kind,
      available,
      missingFields: [...new Set([...missing, ...unresolved])].length
        ? [...new Set([...missing, ...unresolved])]
        : ['Specification review'],
      notes: previous.kind === 'incomplete' && Array.isArray(previous.notes) ? previous.notes : [],
    },
  };
}
export function changeCategory(item: EditorRecord, category: string): EditorRecord {
  const previous = record(item.specs),
    kind = intendedKind(category);
  const oldKind = previous.kind === 'incomplete' ? previous.intendedKind : previous.kind;
  if (oldKind === kind) return { ...item, category };
  // Keep entered ratings by schema family so category exploration does not erase them.
  // The editor restores these when switching back; different families start empty.
  return {
    ...item,
    category,
    specs: {
      kind: 'incomplete',
      intendedKind: kind,
      available:
        category === 'dmx-0-10v-converter'
          ? {
              protocolIn: ['DMX512'],
              protocolOut: ['0-10V'],
              ports: [
                { name: 'DMX-IN', direction: 'in', protocol: 'DMX512' },
                { name: 'DIM1', direction: 'out', protocol: '0-10V' },
              ],
              startsNewSegment: false,
            }
          : kind === 'decoder'
            ? { dmxThru: true }
            : {},
      missingFields: ['Specifications'],
      notes: previous.kind === 'incomplete' && Array.isArray(previous.notes) ? previous.notes : [],
    },
  };
}
export function parseEditor(text: string): EditorRecord {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Enter an item object before returning to the form.');
  return value as EditorRecord;
}
export const itemSchema = (kind: LibraryKind) =>
  kind === 'products' ? CatalogItemSchema : WireTypeSchema;
