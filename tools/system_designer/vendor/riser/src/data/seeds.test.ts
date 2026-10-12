import { describe, expect, it } from 'vitest';
import {
  seedProducts,
  seedWires,
  seedLayers,
  seedNotes,
  seedCodeTables,
  seedTitleBlocks,
} from './seeds';
import {
  CatalogItemSchema,
  CatalogSpecsSchema,
  mergeSpecOverrides,
  ProductLibrarySchema,
} from '../schemas/catalog';
import { WireLibrarySchema, WireTypeSchema } from '../schemas/wire';
import { CatalogCategorySchema, RunTypeSchema } from '../schemas/common';
import {
  AmpacityTableSchema,
  CodeTableLibrarySchema,
  CodeTableSchema,
  LayerLibrarySchema,
  TitleBlockSchema,
} from '../schemas/reference-data';

describe('seed data acceptance', () => {
  it('loads all JSON files through their Zod schemas', () => {
    expect(seedProducts).toHaveLength(25);
    expect(seedWires).toHaveLength(61);
    expect(seedLayers.layers).toHaveLength(16);
    expect(seedTitleBlocks).toHaveLength(4);
    expect(seedNotes).toHaveLength(12);
    expect(seedCodeTables).toHaveLength(4);
  });
  it('has example products for every category and separately identifies TW conductor limits', () => {
    expect(new Set(seedProducts.map((p) => p.category))).toEqual(
      new Set(CatalogCategorySchema.options),
    );
    for (const item of seedProducts) {
      expect(item.isExample).toBe(true);
      expect(item.description).toContain('EXAMPLE – replace with real data');
      expect(item.brand).toBe('EXAMPLE');
    }
    const tape = seedProducts.find((p) => p.id === 'tape-tw')!.specs;
    expect(tape.kind).toBe('tape');
    if (tape.kind !== 'tape') throw new Error('Expected tape');
    expect(tape.powerBasis).toBe('max-operating');
    expect(tape.wPerFtMax).toBe(4.4);
    expect(tape.channelWPerFtMax).toEqual([4.4, 4.4]);
    expect(tape.maxSimultaneousPct).toBe(100);
  });
  it('covers all run types, required wire families and verification flags', () => {
    expect(new Set(seedWires.flatMap((w) => w.applications))).toEqual(
      new Set(RunTypeSchema.options),
    );
    for (const family of [
      'THHN/THWN-2',
      'NM-B',
      'MC',
      'UF-B',
      'SOOW',
      'SJOOW',
      'CL3R',
      'CL3P',
      'CM',
      'CMR',
      'CMP',
    ])
      expect(seedWires.some((w) => w.listing === family)).toBe(true);
    for (const wire of seedWires) {
      expect(wire.verify).toBe(true);
      expect(wire.isExample).toBe(true);
      expect(wire.manufacturerRefChecks.every((ref) => ref.verify)).toBe(true);
      expect(wire.manufacturerRefChecks.map((ref) => ref.reference)).toEqual(wire.manufacturerRefs);
    }
    expect(seedWires.find((w) => w.id === 'wireless-crmx')!.conductors).toEqual([]);
    expect(seedWires.find((w) => w.id === 'dmx-24-2p')!.manufacturerRefs).not.toContain(
      'Belden 9729',
    );
  });
  it('keeps edition, temperature, conductor limits and unavailable impedance explicit', () => {
    const resistance = seedCodeTables.find((t) => t.kind === 'resistance')!;
    expect(resistance.source.edition).toBe('2023');
    if (resistance.kind !== 'resistance') throw new Error('Expected resistance');
    expect(resistance.rows.find((r) => r.awg === '12')).toEqual({
      awg: '12',
      solid: 1.93,
      stranded: 1.98,
    });
    const ampacity = AmpacityTableSchema.parse(seedCodeTables.find((t) => t.kind === 'ampacity'));
    expect(ampacity.rows.find((r) => r.awg === '12')).toEqual({
      awg: '12',
      at60C: 20,
      at75C: 25,
      at90C: 30,
      smallConductorOcpdLimitA: 20,
    });
    const impedance = seedCodeTables.find((t) => t.kind === 'effective-z')!;
    expect(impedance.rows).toEqual([]);
    expect('status' in impedance && impedance.status).toBe('unavailable');
    expect(
      seedCodeTables.every(
        (t) => t.comment.length > 20 && t.source.verification !== 'user-verified',
      ),
    ).toBe(true);
  });
  it('preserves plotted inches, minimum text sizes and the non-exportable QA layer', () => {
    expect(seedTitleBlocks.find((t) => t.sheetSize === 'ARCH_D')).toMatchObject({
      widthIn: 36,
      heightIn: 24,
    });
    expect(seedTitleBlocks.find((t) => t.sheetSize === 'ANSI_B')).toMatchObject({
      widthIn: 17,
      heightIn: 11,
    });
    for (const sheet of seedTitleBlocks) {
      expect(sheet.coordinateSystem).toBe('paper-inches-lower-left');
      expect(sheet.fields.every((f) => f.textHeightIn >= 3 / 32)).toBe(true);
      expect(sheet.referenceSquare).toMatchObject({ width: 1, height: 1 });
    }
    expect(seedLayers.layers.find((l) => l.name === 'E-ANNO-QAFL')!.export).toBe(false);
  });
});

describe('catalog rejection and partial override boundaries', () => {
  const psu = seedProducts.find((p) => p.category === 'psu')!;
  it('rejects ambiguous/missing power specs and category mismatches', () => {
    expect(CatalogItemSchema.safeParse({ ...psu, category: 'tape' }).success).toBe(false);
    expect(CatalogItemSchema.safeParse({ ...psu, model: 'Unlabelled' }).success).toBe(false);
    expect(
      CatalogSpecsSchema.safeParse({ ...psu.specs, inputVMin: 480, inputVMax: 120 }).success,
    ).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...psu.specs, efficiency: 1.01 }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...psu.specs, outputV: undefined }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...psu.specs, maxInputA: 1.4 }).success).toBe(false);
    expect(
      CatalogSpecsSchema.safeParse({ ...psu.specs, terminalMinAwg: '10', terminalMaxAwg: '18' })
        .success,
    ).toBe(false);
  });
  it('requires explicit channel maxima for limited-operation tape', () => {
    const tape = seedProducts.find((p) => p.id === 'tape-tw')!.specs;
    expect(CatalogSpecsSchema.safeParse({ ...tape, channelWPerFtMax: undefined }).success).toBe(
      false,
    );
    expect(CatalogSpecsSchema.safeParse({ ...tape, channelMap: ['WW'] }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...tape, channelMap: ['WW', 'WW'] }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...tape, maxSimultaneousPct: 201 }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...tape, minOperatingV: 25 }).success).toBe(false);
  });
  it('revalidates merged overrides and rejects duplicate SKU/ID imports', () => {
    expect(mergeSpecOverrides(psu, { kind: 'psu', ratedW: 100 }).specs).toMatchObject({
      ratedW: 100,
    });
    expect(() => mergeSpecOverrides(psu, { kind: 'driver' })).toThrow();
    expect(() => mergeSpecOverrides(psu, { kind: 'psu', efficiency: 2 })).toThrow();
    expect(ProductLibrarySchema.safeParse([psu, { ...psu, id: 'second' }]).success).toBe(false);
    expect(ProductLibrarySchema.safeParse([psu, { ...psu, sku: 'other' }]).success).toBe(false);
  });
  it('requires CC current and a valid compliance range', () => {
    const cc = seedProducts.find((p) => p.category === 'driver')!.specs;
    expect(CatalogSpecsSchema.safeParse({ ...cc, outputmA: undefined }).success).toBe(false);
    expect(CatalogSpecsSchema.safeParse({ ...cc, outputVMin: 48 }).success).toBe(false);
    const fixture = seedProducts.find((p) => p.id === 'downlight-cc')!.specs;
    expect(CatalogSpecsSchema.safeParse({ ...fixture, mA: undefined }).success).toBe(false);
  });
});

describe('wire and reference-data rejection', () => {
  it('rejects missing fine-gauge resistance, invalid pairs and false reference claims', () => {
    const wire = seedWires.find((w) => w.id === 'dmx-24-1p')!;
    expect(WireTypeSchema.safeParse({ ...wire, resistanceOhmPerKft: undefined }).success).toBe(
      false,
    );
    expect(
      WireTypeSchema.safeParse({ ...wire, conductors: [{ ...wire.conductors[0], count: 3 }] })
        .success,
    ).toBe(false);
    expect(WireTypeSchema.safeParse({ ...wire, manufacturerRefChecks: [] }).success).toBe(false);
    expect(WireTypeSchema.safeParse({ ...wire, verify: false }).success).toBe(false);
    expect(WireTypeSchema.safeParse({ ...wire, directBurial: true, wet: false }).success).toBe(
      false,
    );
    expect(WireLibrarySchema.safeParse([wire, wire]).success).toBe(false);
  });
  it('rejects code-table duplicates, reversed ampacity columns and fake available impedance', () => {
    expect(CodeTableLibrarySchema.safeParse([seedCodeTables[0], seedCodeTables[0]]).success).toBe(
      false,
    );
    const a = AmpacityTableSchema.parse(seedCodeTables.find((t) => t.kind === 'ampacity'));
    expect(
      CodeTableSchema.safeParse({ ...a, rows: [{ awg: '12', at60C: 30, at75C: 20, at90C: 10 }] })
        .success,
    ).toBe(false);
    const z = seedCodeTables.find((t) => t.kind === 'effective-z')!;
    expect(CodeTableSchema.safeParse({ ...z, status: 'available' }).success).toBe(false);
  });
  it('rejects missing layers, exported QA, off-sheet fields and subminimum text', () => {
    expect(
      LayerLibrarySchema.safeParse({ ...seedLayers, layers: seedLayers.layers.slice(1) }).success,
    ).toBe(false);
    expect(
      LayerLibrarySchema.safeParse({
        ...seedLayers,
        layers: seedLayers.layers.map((l) => ({ ...l, export: true })),
      }).success,
    ).toBe(false);
    const title = seedTitleBlocks[0]!;
    expect(
      TitleBlockSchema.safeParse({
        ...title,
        fields: [{ ...title.fields[0], textHeightIn: 0.08 }, ...title.fields.slice(1)],
      }).success,
    ).toBe(false);
    expect(
      TitleBlockSchema.safeParse({
        ...title,
        referenceSquare: { ...title.referenceSquare, width: 2 },
      }).success,
    ).toBe(false);
    expect(TitleBlockSchema.safeParse({ ...title, drawingArea: title.titleBlock }).success).toBe(
      false,
    );
  });
});
