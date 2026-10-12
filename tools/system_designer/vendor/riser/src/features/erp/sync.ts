import { z } from 'zod';
import { CatalogItemSchema, ProductLibrarySchema, type CatalogItem } from '../../schemas/catalog';
import { seedProducts } from '../../data/seeds';
import mappingJson from '../../data/erp-mapping.example.json';

const safePath = (value: string) =>
  !value.split('.').some((p) => ['__proto__', 'prototype', 'constructor'].includes(p));
export const MappingSchema = z
  .object({
    version: z.literal(1),
    fields: z.record(
      z.string().regex(/^[a-zA-Z][a-zA-Z0-9_]*$/),
      z
        .string()
        .regex(
          /^(sku|brand|model|category|description|isExample|datasheetUrl|specs(\.[a-zA-Z0-9_]+)*)$/,
        )
        .refine(safePath),
    ),
  })
  .strict();
export type Mapping = z.infer<typeof MappingSchema>;
export const defaultMapping = MappingSchema.parse(mappingJson);
export type SyncRow = {
  code: string;
  status: 'added' | 'updated' | 'unchanged' | 'conflict' | 'invalid';
  item?: CatalogItem;
  conflicts: string[];
  errors: string[];
};
const get = (value: unknown, path: string): unknown =>
  path
    .split('.')
    .reduce<unknown>(
      (v, k) => (v && typeof v === 'object' ? (v as Record<string, unknown>)[k] : undefined),
      value,
    );
function set(target: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split('.');
  let object = target;
  for (const key of parts.slice(0, -1)) {
    if (!object[key] || typeof object[key] !== 'object') object[key] = {};
    object = object[key] as Record<string, unknown>;
  }
  object[parts.at(-1)!] = structuredClone(value);
}
export function previewSync(
  records: unknown[],
  mapping: Mapping,
  existing: CatalogItem[],
): SyncRow[] {
  MappingSchema.parse(mapping);
  const seen = new Set<string>();
  return records.map((record): SyncRow => {
    const raw = z.record(z.string(), z.unknown()).safeParse(record);
    const code = raw.success ? String(raw.data.item_code ?? '') : '';
    if (!raw.success || !code || seen.has(code))
      return { code, status: 'invalid', conflicts: [], errors: ['Missing or duplicate item_code'] };
    seen.add(code);
    const matches = existing.filter((p) => p.erpItemCode === code);
    if (matches.length > 1)
      return {
        code,
        status: 'invalid',
        conflicts: [],
        errors: ['Several local products have this ERP item code. Resolve them before syncing.'],
      };
    const old = matches[0];
    const candidate: Record<string, unknown> = old
      ? structuredClone(old)
      : { id: `erp:${code}`, erpItemCode: code, isExample: false, localOverrides: [] };
    const conflicts: string[] = [];
    try {
      for (const [field, path] of Object.entries(mapping.fields)) {
        let value = raw.data[field];
        if (value === undefined || value === null || value === '') continue;
        if (path === 'specs' && typeof value === 'string') value = JSON.parse(value);
        if (path === 'isExample')
          value = value === true || value === 1 || value === '1' || value === 'true';
        if (path.startsWith('specs.') && typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value))
          value = Number(value);
        const protectedPaths = (old?.localOverrides ?? []).filter(
          (p) => p === path || path.startsWith(p + '.') || p.startsWith(path + '.'),
        );
        if (!protectedPaths.length) {
          set(candidate, path, value);
          continue;
        }
        const proposed = structuredClone(candidate);
        set(proposed, path, value);
        for (const protectedPath of protectedPaths) {
          const previous = get(old, protectedPath);
          if (JSON.stringify(get(proposed, protectedPath)) !== JSON.stringify(previous)) {
            conflicts.push(protectedPath);
            if (previous !== undefined) set(proposed, protectedPath, previous);
            else {
              const keys = protectedPath.split('.');
              const parent =
                keys.length === 1 ? proposed : get(proposed, keys.slice(0, -1).join('.'));
              if (parent && typeof parent === 'object')
                delete (parent as Record<string, unknown>)[keys.at(-1)!];
            }
          }
        }
        for (const key of Object.keys(candidate)) delete candidate[key];
        Object.assign(candidate, proposed);
      }
      candidate.erpItemCode = code;
      const item = CatalogItemSchema.parse(candidate);
      if (existing.some((p) => p.id !== old?.id && (p.id === item.id || p.sku === item.sku)))
        throw new Error('SKU or ID conflicts with another local product.');
      return {
        code,
        status: conflicts.length
          ? 'conflict'
          : !old
            ? 'added'
            : JSON.stringify(item) === JSON.stringify(old)
              ? 'unchanged'
              : 'updated',
        item,
        conflicts: [...new Set(conflicts)],
        errors: [],
      };
    } catch (e) {
      return {
        code,
        status: 'invalid',
        conflicts,
        errors: [e instanceof Error ? e.message : 'Invalid ERP item'],
      };
    }
  });
}
export function commitSync(existing: CatalogItem[], rows: SyncRow[]): CatalogItem[] {
  if (rows.some((r) => r.status === 'invalid'))
    throw new Error('Resolve invalid rows before committing the pull.');
  const result = [...existing];
  for (const row of rows) {
    if (!row.item) continue;
    const index = result.findIndex((p) => p.erpItemCode === row.code);
    if (index < 0) result.push(row.item);
    else result[index] = row.item;
  }
  return ProductLibrarySchema.parse(result);
}
export function demoRecords() {
  return seedProducts
    .filter((p) => ['psu-24v-96w', 'decoder-4ch', 'tape-tw'].includes(p.id))
    .map((p) => ({
      item_code: `ERP-DEMO-${p.id}`,
      brand: p.brand,
      item_name: p.model,
      description: p.description,
      custom_riser_category: p.category,
      custom_riser_is_example: 1,
      custom_riser_specs: JSON.stringify(p.specs),
      item_group: 'Lighting Demo',
    }));
}
