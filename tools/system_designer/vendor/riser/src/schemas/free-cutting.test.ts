import { describe, expect, it } from 'vitest';
import { CatalogItemSchema, CatalogSpecOverridesSchema, mergeSpecOverrides } from './catalog';
import { seedProducts } from '../data/seeds';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { loadProfile } from '../engine/loads';
import { buildDrawing } from '../drawing/build';
import {
  autoMap,
  commitImport,
  exportCsv,
  fieldsFor,
  previewImport,
  readCsv,
} from '../features/library/import';
import { fullProduct, incompleteProduct, updateField } from '../features/library/editor-model';

const tape = seedProducts.find((p) => p.id === 'tape-white')!;
const free = () => {
  const item = structuredClone(tape);
  if (item.specs.kind !== 'tape') throw new Error('Expected tape');
  item.specs.freeCutting = true;
  delete item.specs.cutIntervalIn;
  return CatalogItemSchema.parse(item);
};
describe('free-cutting tape', () => {
  it('requires an explicit free-cutting flag and rejects contradictory or zero intervals', () => {
    expect(CatalogItemSchema.safeParse(free()).success).toBe(true);
    const fixed = structuredClone(tape);
    if (fixed.specs.kind !== 'tape') throw new Error('Expected tape');
    const legacy = { ...fixed, specs: { ...fixed.specs, freeCutting: undefined } };
    expect(CatalogItemSchema.parse(legacy).specs).toMatchObject({
      freeCutting: false,
      cutIntervalIn: 4,
    });
    delete fixed.specs.cutIntervalIn;
    expect(CatalogItemSchema.safeParse(fixed).success).toBe(false);
    expect(
      CatalogItemSchema.safeParse({ ...free(), specs: { ...free().specs, cutIntervalIn: 4 } })
        .success,
    ).toBe(false);
    expect(
      CatalogItemSchema.safeParse({ ...free(), specs: { ...free().specs, cutIntervalIn: 0 } })
        .success,
    ).toBe(false);
  });
  it('round-trips CSV and clears an old interval on a flat free-cutting upsert', () => {
    const parsed = readCsv(exportCsv([free()])),
      mapping = autoMap(parsed.headers, fieldsFor('products'));
    expect(mapping['specs.freeCutting']).toBe('specs.freeCutting');
    const preview = previewImport('products', parsed.rows, mapping, [tape]);
    expect(preview[0]?.action).toBe('updated');
    expect(commitImport([tape], preview)).toEqual([free()]);
    expect(previewImport('products', parsed.rows, mapping, [free()])[0]?.action).toBe('unchanged');
    expect(CatalogItemSchema.parse(JSON.parse(JSON.stringify(free())))).toEqual(free());
  });
  it('upgrades legacy incomplete ERP records from their explicit source flag without inventing other ratings', () => {
    const item = {
      ...tape,
      isExample: false,
      sourceData: {
        fields: { is_free_cutting: '1', cut_increment_mm: '0' },
        children: { options: [{ value: 'original' }] },
      },
      specs: {
        kind: 'incomplete',
        intendedKind: 'tape',
        available: { voltage: 24 },
        missingFields: ['cutIntervalIn', 'minOperatingV'],
        notes: ['Keep this note.'],
      },
    };
    const migrated = CatalogItemSchema.parse(item);
    expect(migrated.specs).toMatchObject({
      kind: 'incomplete',
      available: { voltage: 24, freeCutting: true },
      missingFields: ['minOperatingV'],
      notes: ['Keep this note.'],
    });
    expect(migrated.sourceData).toEqual(item.sourceData);
    expect(item.specs.available).toEqual({ voltage: 24 });
    expect(CatalogItemSchema.parse(migrated)).toEqual(migrated);
    const noFlag = CatalogItemSchema.parse({
      ...item,
      sourceData: { fields: { cut_increment_mm: '0' } },
    });
    expect(noFlag.specs).not.toHaveProperty('available.freeCutting');
    const local = CatalogItemSchema.parse({
      ...item,
      specs: { ...item.specs, available: { freeCutting: false } },
    });
    expect(local.specs).toHaveProperty('available.freeCutting', false);
    const entered = CatalogItemSchema.parse({
      ...item,
      specs: { ...item.specs, available: { cutIntervalIn: 2 } },
    });
    expect(entered.specs).toHaveProperty('available.cutIntervalIn', 2);
    expect(entered.specs).not.toHaveProperty('available.freeCutting');
  });
  it('supports form toggles, incomplete progress and overrides without restoring fixed cutting accidentally', () => {
    const edited = updateField(tape, 'specs.freeCutting', true);
    expect(CatalogItemSchema.parse(edited)).toEqual(free());
    expect(incompleteProduct(edited)).not.toHaveProperty('specs.available.cutIntervalIn');
    expect(CatalogItemSchema.parse(fullProduct(incompleteProduct(edited)))).toEqual(free());
    expect(
      CatalogItemSchema.safeParse(updateField(edited, 'specs.freeCutting', false)).success,
    ).toBe(false);
    const override = CatalogSpecOverridesSchema.parse({ kind: 'tape', wPerFtMax: 5 });
    expect(override).not.toHaveProperty('freeCutting');
    expect(mergeSpecOverrides(free(), override).specs).toHaveProperty('freeCutting', true);
    expect(mergeSpecOverrides(tape, { kind: 'tape', freeCutting: true })).toEqual(free());
  });
  it('uses the entered fractional length for load, BOM and drawing with no artificial cut increment', async () => {
    const item = free(),
      library = seedLibrary(),
      project = demoProject();
    library.products = library.products.map((p) => (p.id === item.id ? item : p));
    const load = project.loads.find((l) => l.catalogId === item.id)!;
    load.lengthFt = 1.125;
    project.settings.tapeLengthMarginPct = 10;
    if (item.specs.kind !== 'tape') throw new Error('Expected tape');
    const profile = loadProfile(load, item.specs, project.settings);
    expect(profile.watts).toBeCloseTo(1.125 * 1.1 * item.specs.wPerFtMax);
    expect(profile.current).toBeCloseTo(profile.watts / item.specs.voltage);
    const result = calculate(project, library);
    expect(result.messages.some((m) => ['INVALID_SPEC', 'INCOMPLETE_SPEC'].includes(m.code))).toBe(
      false,
    );
    const total = project.loads
      .filter((l) => l.catalogId === item.id)
      .reduce((n, l) => n + (l.lengthFt ?? 0) * 1.1, 0);
    expect(result.bom.find((b) => b.sku === item.sku)?.quantity).toBeCloseTo(total, 2);
    expect((await buildDrawing(project, library, result)).sheets.length).toBeGreaterThan(0);
  });
});
