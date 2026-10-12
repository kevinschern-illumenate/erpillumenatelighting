import { describe, it, expect } from 'vitest';
import { commitSync, defaultMapping, demoRecords, previewSync, MappingSchema } from './sync';
import { seedProducts } from '../../data/seeds';

describe('pull-only ERP mapping', () => {
  it('preserves an explicitly removed optional nested field during full-spec pulls', () => {
    const products = commitSync([], previewSync(demoRecords(), defaultMapping, []));
    const psu = products.find((p) => p.specs.kind === 'psu')!;
    if (psu.specs.kind !== 'psu') throw new Error('fixture');
    delete psu.specs.maxInputA;
    psu.localOverrides = ['specs.maxInputA'];
    const records = demoRecords();
    const remote = records.find((r) => r.item_code === psu.erpItemCode)!;
    remote.custom_riser_specs = JSON.stringify({
      ...JSON.parse(remote.custom_riser_specs),
      maxInputA: 1.4,
      maxInputAAtV: 120,
    });
    const row = previewSync(records, defaultMapping, products).find(
      (r) => r.code === psu.erpItemCode,
    )!;
    expect(row.conflicts).toContain('specs.maxInputA');
    expect(row.item?.specs).not.toHaveProperty('maxInputA');
  });
  it('adds demo items, then upserts by ERP item code without duplicating products', () => {
    const rows = previewSync(demoRecords(), defaultMapping, seedProducts);
    expect(rows.map((r) => r.status)).toEqual(['added', 'added', 'added']);
    const next = commitSync(seedProducts, rows);
    expect(next.length).toBe(seedProducts.length + 3);
    expect(
      previewSync(demoRecords(), defaultMapping, next).every((r) => r.status === 'unchanged'),
    ).toBe(true);
  });
  it('preserves top-level and nested local overrides and reports conflicts', () => {
    const next = commitSync([], previewSync(demoRecords(), defaultMapping, []));
    const psu = next.find((p) => p.category === 'psu')!;
    psu.model = 'EXAMPLE local preferred name';
    psu.localOverrides = ['model', 'specs.ratedW'];
    if (psu.specs.kind === 'psu') psu.specs.ratedW = 95;
    const row = previewSync(demoRecords(), defaultMapping, next).find(
      (r) => r.code === psu.erpItemCode,
    )!;
    expect(row.status).toBe('conflict');
    expect(row.conflicts).toEqual(['model', 'specs.ratedW']);
    expect(row.item?.model).toBe(psu.model);
    expect(row.item?.specs).toMatchObject({ ratedW: 95 });
  });
  it('rejects incomplete electrical data and prototype paths, and commits nothing on invalid rows', () => {
    expect(
      MappingSchema.safeParse({ version: 1, fields: { bad: 'specs.__proto__.polluted' } }).success,
    ).toBe(false);
    const rows = previewSync([{ item_code: 'MISSING', item_name: 'Real PSU' }], defaultMapping, []);
    expect(rows[0]?.status).toBe('invalid');
    expect(() => commitSync([], rows)).toThrow();
    expect(
      previewSync([...demoRecords(), demoRecords()[0]], defaultMapping, []).at(-1)?.status,
    ).toBe('invalid');
  });
});
