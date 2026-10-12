import { describe, expect, it } from 'vitest';
import { seedProducts, seedWires } from '@ill/data/seeds';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { WireTypeSchema } from '@ill/core-schemas/wire';
import {
  at,
  changeCategory,
  fullProduct,
  incompleteProduct,
  newLibraryItem,
  parseEditor,
  updateField,
} from './editor-model';

describe('library form data', () => {
  it('starts converters with signal ports and carries the selected AC/DC range when changing supply type', () => {
    const fresh = changeCategory(newLibraryItem('products', 'converter'), 'dmx-0-10v-converter');
    expect(at(fresh, 'specs.available.ports')).toEqual([
      { name: 'DMX-IN', direction: 'in', protocol: 'DMX512' },
      { name: 'DIM1', direction: 'out', protocol: '0-10V' },
    ]);
    const item = seedProducts.find((p) => p.category === 'dmx-0-10v-converter')!;
    let edited = updateField(item, 'specs.dcInputVMin', 18);
    edited = updateField(edited, 'specs.dcInputVMax', 30);
    edited = updateField(edited, 'specs.maxInputA', 0.5);
    edited = updateField(edited, 'specs.maxInputAAtV', 12);
    edited = updateField(edited, 'specs.maxInputAType', 'AC');
    edited = updateField(edited, 'specs.inputType', 'DC');
    expect(at(edited, 'specs.inputVMin')).toBe(18);
    expect(at(edited, 'specs.inputVMax')).toBe(30);
    expect(at(edited, 'specs.maxInputA')).toBeUndefined();
    expect(at(edited, 'specs.dcInputVMin')).toBeUndefined();
    expect(CatalogItemSchema.safeParse(edited).success).toBe(true);
  });
  it('preserves every complete product and wire through a form edit and JSON round trip', () => {
    for (const product of seedProducts) {
      const edited = updateField(product, 'brand', 'Edited brand');
      expect(CatalogItemSchema.parse(parseEditor(JSON.stringify(edited)))).toEqual({
        ...product,
        brand: 'Edited brand',
      });
      expect(product.brand).not.toBe('Edited brand');
    }
    for (const wire of seedWires) {
      const edited = updateField(wire, 'riserLabel', 'Edited label');
      expect(WireTypeSchema.parse(parseEditor(JSON.stringify(edited)))).toEqual({
        ...wire,
        riserLabel: 'Edited label',
      });
    }
  });
  it('starts real products without synthetic ratings and preserves unknown booleans', () => {
    let item = newLibraryItem('products', 'real-item');
    expect(item.isExample).toBe(false);
    expect(at(item, 'specs.available')).toEqual({});
    item = updateField(item, 'specs.available.outputs', [{ name: 'OUT1', maxW: 100 }]);
    expect(at(incompleteProduct(item), 'specs.available.outputs.0.class2')).toBeUndefined();
    expect(CatalogItemSchema.safeParse(fullProduct(item)).success).toBe(false);
  });
  it('updates missing fields while retaining source data and unresolved model conflicts', () => {
    const raw = {
      fields: { name: 'Exact source', watts: '10.0' },
      children: { options: [{ name: 'Warm' }] },
    };
    const item = {
      ...newLibraryItem('products', 'sheet'),
      sku: 'SHEET',
      model: 'Sheet',
      description: 'Whole sheet',
      category: 'fixture',
      sourceData: raw,
      specs: {
        kind: 'incomplete',
        intendedKind: 'fixture',
        available: { voltageClass: 'low', inputV: 24, watts: 10 },
        missingFields: ['dimming', 'integralDriver', 'Channel topology review'],
        notes: ['Check the source.'],
      },
    };
    const edited = updateField(
      updateField(item, 'specs.available.integralDriver', false),
      'specs.available.dimming',
      ['PWM'],
    );
    const pending = incompleteProduct(edited);
    expect(at(pending, 'specs.missingFields')).toEqual(['Channel topology review']);
    expect(at(pending, 'specs.notes')).toEqual(['Check the source.']);
    expect(pending.sourceData).toEqual(raw);
    const ready = CatalogItemSchema.parse(fullProduct(pending));
    expect(ready.sourceData).toEqual(raw);
    expect(ready.specs.kind).toBe('fixture');
  });
  it('edits repeaters without changing sibling values or the source object', () => {
    const item = seedProducts.find((p) => p.specs.kind === 'psu')!;
    const next = updateField(item, 'specs.outputs.0.name', 'LOAD-A');
    expect(at(next, 'specs.outputs.0.maxW')).toEqual(at(item, 'specs.outputs.0.maxW'));
    expect(at(item, 'specs.outputs.0.name')).not.toBe('LOAD-A');
    expect(CatalogItemSchema.safeParse(next).success).toBe(true);
  });
  it('clears optional compound fields and keeps manufacturer checks synchronized', () => {
    let pixel: Record<string, unknown> = structuredClone(
      seedProducts.find((p) => p.specs.kind === 'tape' && p.specs.pixel)!,
    );
    for (const field of ['protocol', 'pixelsPerFt', 'ampsPerPixelMax'])
      pixel = updateField(pixel, `specs.pixel.${field}`, undefined);
    expect(at(pixel, 'specs.pixel')).toBeUndefined();
    let wire: Record<string, unknown> = structuredClone(seedWires[0]!);
    wire = updateField(wire, 'manufacturerRefChecks', [{ reference: 'Acme 123' }]);
    expect(wire.manufacturerRefs).toEqual(['Acme 123']);
    expect(wire.manufacturerRefChecks).toEqual([{ reference: 'Acme 123', verify: true }]);
    expect(WireTypeSchema.safeParse(wire).success).toBe(true);
    wire = updateField(wire, 'manufacturerRefChecks', []);
    expect(wire.manufacturerRefs).toEqual([]);
  });
  it('uses the selected category schema without borrowing unrelated ratings', () => {
    const item = seedProducts.find((p) => p.specs.kind === 'psu')!;
    const next = changeCategory(item, 'tape');
    expect(at(next, 'specs.intendedKind')).toBe('tape');
    expect(at(next, 'specs.available')).toEqual({});
    expect(next.id).toBe(item.id);
    expect(CatalogItemSchema.safeParse(next).success).toBe(true);
  });
  it('switches a decoder between DC and AC without retaining an incompatible phase method', () => {
    const legacy = seedProducts.find((p) => p.id === 'decoder-4ch')!;
    expect(CatalogItemSchema.parse(legacy).specs).toMatchObject({ powerType: 'DC' });
    let item = updateField(legacy, 'specs.powerType', 'AC');
    expect(CatalogItemSchema.safeParse(item).success).toBe(false);
    item = updateField(item, 'specs.outputDimming', 'phase-reverse');
    expect(CatalogItemSchema.safeParse(item).success).toBe(true);
    item = updateField(item, 'specs.powerType', 'DC');
    expect(at(item, 'specs.outputDimming')).toBeUndefined();
    expect(CatalogItemSchema.safeParse(item).success).toBe(true);
  });
});
