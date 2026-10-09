import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CatalogItemSchema, ProductLibrarySchema } from './catalog';
import { WireLibrarySchema, WireTypeSchema } from './wire';

// Built by system_design/catalog.py from fixtures/catalog/erp-records.json (WP-2.1 parity).
const payload = JSON.parse(
  readFileSync(new URL('../fixtures/catalog/payload.json', import.meta.url), 'utf8'),
) as { items: unknown[]; wires: unknown[]; engine_contract_version: string };

const FORBIDDEN = [
  'cost',
  'valuation_rate',
  'last_purchase_rate',
  'standard_rate',
  'selection_cost',
  'buying_price',
];

function keys(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(keys);
  if (value && typeof value === 'object')
    return Object.entries(value).flatMap(([key, child]) => [key, ...keys(child)]);
  return [];
}

describe('ERP catalog payload', () => {
  it('parses every item and wire with the engine schemas', () => {
    for (const item of payload.items) {
      const parsed = CatalogItemSchema.safeParse(item);
      expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
    }
    for (const wire of payload.wires) {
      const parsed = WireTypeSchema.safeParse(wire);
      expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
    }
    expect(ProductLibrarySchema.safeParse(payload.items).success).toBe(true);
    expect(WireLibrarySchema.safeParse(payload.wires).success).toBe(true);
  });

  it('keeps ERP records real, ranked and cost-free', () => {
    const items = ProductLibrarySchema.parse(payload.items);
    expect(items.every((item) => !item.isExample)).toBe(true);
    const ranks = items.flatMap((item) => (item.rank === undefined ? [] : [item.rank]));
    expect(ranks.sort()).toEqual([1, 2, 3]);
    expect(keys(payload).filter((key) => FORBIDDEN.includes(key))).toEqual([]);
    expect(items.filter((item) => item.specs.kind === 'incomplete').map((item) => item.id)).toEqual([
      'drv:TEST-PSU-BAD',
      'tape:TEST-TAPE-120:3:1000',
    ]);
  });
});
