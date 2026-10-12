import { describe, expect, it } from 'vitest';
import { seedProducts, seedWires } from '@ill/data/seeds';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { autoMap, commitImport, exportCsv, fieldsFor, previewImport, readCsv } from './import';

describe('library CSV workflow', () => {
  const pending = CatalogItemSchema.parse({
    id: 'imported-fixture',
    sku: 'ERP-SHEET',
    brand: 'Test',
    model: 'Sheet',
    category: 'fixture',
    description: 'Incomplete source record',
    isExample: false,
    erpItemCode: 'ERP-SHEET',
    specs: {
      kind: 'incomplete',
      intendedKind: 'fixture',
      available: { voltageClass: 'low', inputType: 'DC', inputV: 24, watts: 10 },
      missingFields: ['dimming', 'integralDriver'],
      notes: ['One quantity is one whole sheet.'],
    },
    sourceData: {
      fields: { item: 'ERP-SHEET', watts: '10.0', blank: '' },
      children: { ccts: [{ cct: '3000K' }, { cct: '4000K' }] },
    },
  });
  it('round-trips complete and incomplete products, optional ratings, ranges and source records', () => {
    const ranged = CatalogItemSchema.parse({
      ...seedProducts.find((p) => p.specs.kind === 'fixture')!,
      id: 'range-fixture',
      sku: 'EX-RANGE',
      specs: {
        kind: 'fixture',
        voltageClass: 'line',
        inputV: [120, 277],
        watts: 10,
        dimming: [],
        integralDriver: true,
      },
    });
    const products = [...seedProducts, ranged, pending];
    const parsed = readCsv(exportCsv(products));
    const preview = previewImport(
      'products',
      parsed.rows,
      autoMap(parsed.headers, fieldsFor('products')),
      [],
    );
    expect(preview.filter((r) => r.action === 'error')).toEqual([]);
    expect(commitImport([], preview)).toEqual(products);
    expect(
      previewImport(
        'products',
        parsed.rows,
        autoMap(parsed.headers, fieldsFor('products')),
        products,
      ).every((r) => r.action === 'unchanged'),
    ).toBe(true);
  });
  it('imports whole spec JSON, validates promotion, and preserves identity and source data', () => {
    const draftRows = [{ sku: pending.sku, specs: JSON.stringify(pending.specs) }];
    expect(
      previewImport('products', draftRows, { sku: 'sku', specs: 'specs' }, [pending])[0]?.action,
    ).toBe('unchanged');
    const prepared = {
      ...pending,
      specs: {
        ...(pending.specs.kind === 'incomplete' ? pending.specs.available : {}),
        kind: 'fixture',
      },
    };
    expect(CatalogItemSchema.safeParse(prepared).success).toBe(false);
    expect(CatalogItemSchema.safeParse({ ...pending, category: 'tape' }).success).toBe(false);
    const complete = CatalogItemSchema.parse({
      ...prepared,
      specs: { ...prepared.specs, dimming: ['PWM'], integralDriver: false },
    });
    const parsed = readCsv(exportCsv([complete]));
    const promoted = previewImport(
      'products',
      parsed.rows,
      autoMap(parsed.headers, fieldsFor('products')),
      [pending],
    );
    expect(promoted[0]?.action).toBe('updated');
    expect(commitImport([pending], promoted)).toEqual([complete]);
    const ambiguous = previewImport(
      'products',
      [{ sku: pending.sku, specs: '{}', kind: 'fixture' }],
      { sku: 'sku', specs: 'specs', kind: 'specs.kind' },
      [pending],
    );
    expect(ambiguous[0]?.errors.join(' ')).toContain('whole object');
  });
  it('imports 50 complete PSU rows with renamed column mapping, errors and upsert by SKU', () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({
      ...structuredClone(seedProducts[0]!),
      id: `csv-${i}`,
      sku: `PSU-${i}`,
    }));
    const csv = exportCsv(rows).replace('sku,', 'item_code,');
    const parsed = readCsv(csv);
    const mapping = autoMap(parsed.headers, fieldsFor('products'));
    expect(mapping.item_code).toBe('sku');
    const preview = previewImport('products', parsed.rows, mapping, []);
    expect(preview.filter((r) => r.action === 'new')).toHaveLength(50);
    const imported = commitImport([], preview);
    expect(imported).toHaveLength(50);
    expect(
      previewImport('products', parsed.rows, mapping, imported).every(
        (r) => r.action === 'unchanged',
      ),
    ).toBe(true);
    const broken = structuredClone(parsed.rows);
    broken[6]!['specs.efficiency'] = '1.2';
    const invalid = previewImport('products', broken, mapping, imported);
    expect(invalid[6]?.action).toBe('error');
    expect(invalid[6]?.errors.join(' ')).toContain('efficiency');
    expect(() => commitImport(imported, invalid)).toThrow('Fix all');
    parsed.rows[2]!['specs.ratedW'] = '120';
    expect(previewImport('products', parsed.rows, mapping, imported)[2]?.action).toBe('updated');
  });
  it('round-trips mixed-gauge wire arrays and preserves their verification metadata', () => {
    const parsed = readCsv(exportCsv(seedWires));
    const preview = previewImport(
      'wires',
      parsed.rows,
      autoMap(parsed.headers, fieldsFor('wires')),
      [],
    );
    expect(preview.filter((r) => r.action === 'error')).toEqual([]);
    expect(commitImport([], preview)).toEqual(seedWires);
  });
  it('rejects duplicate keys, ambiguous mappings, and missing real-product ratings', () => {
    const source = readCsv(
      'sku,model,brand,category\nREAL-1,Real PSU,Brand,psu\nREAL-1,Duplicate,Brand,psu',
    );
    const mapping = autoMap(source.headers, fieldsFor('products'));
    const preview = previewImport('products', source.rows, mapping, []);
    expect(preview.every((r) => r.action === 'error')).toBe(true);
    expect(preview[0]?.errors.join(' ')).toContain('specs');
    expect(preview[1]?.errors.join(' ')).toContain('Duplicate');
    expect(
      previewImport('products', source.rows, { sku: 'sku', model: 'sku' }, [])[0]?.errors.join(' '),
    ).toContain('same field');
  });
});
