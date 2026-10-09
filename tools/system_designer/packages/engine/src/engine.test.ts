import { describe, expect, it } from 'vitest';
import { calculate, assignWireTags } from './calculate';
import { demoProject } from '@ill/data/demo';
import { seedProducts, seedWires, seedCodeTables } from '@ill/data/seeds';
import { createDraft } from '@ill/core-schemas/workspace';
import { ProjectSchema, ProjectSettingsSchema, type Project } from '@ill/core-schemas/project';
import { CatalogItemSchema, type TapeSpecs } from '@ill/core-schemas/catalog';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import { type RunInput, EngineResultSchema } from './model';
import {
  evaluateWire,
  selectWire,
  environmentMatches,
  constructionMatches,
  wireResistance,
  wireAmpacity,
} from './wireSelect';
import { voltageDrop, maximumLength } from './voltageDrop';
import { loadProfile, inputCurrent } from './loads';
import { buildGraph } from './graph';
import { patchDmx, dmxSegments } from './dmx';
import { powerPortOptions } from './ports';

const library = (): LibrarySnapshot =>
  structuredClone({
    schemaVersion: 1,
    products: seedProducts,
    wires: seedWires,
    codeTables: seedCodeTables,
  });
const settings = ProjectSettingsSchema.parse({});
const run = (patch: Partial<RunInput> = {}): RunInput => ({
  runId: 'run1',
  type: 'class2-dc',
  from: { id: 'ps1', tag: 'PS-1' },
  to: { id: 't1', tag: 'T1' },
  entityRef: 't1',
  lengthFt: 50,
  voltageV: 24,
  currentA: 100 / 24,
  wattsW: 100,
  channelCurrentsA: [],
  phase: '1PH',
  env: 'riser',
  terminalMaxAwg: ['12'],
  required: { power: 2, ground: 0, channel: 0, signal: 0, dataPair: 0 },
  ...patch,
});
const wire = (awg: string, channels = 0) =>
  seedWires.find(
    (w) =>
      w.applications.includes(channels ? 'class2-dc-multichannel' : 'class2-dc') &&
      w.riser &&
      !w.plenum &&
      w.conductors.some((c) => c.awg === awg) &&
      w.conductors.filter((c) => c.role === 'channel').reduce((s, c) => s + c.count, 0) ===
        channels,
  )!;
function single(watts = 88, catalogId = 'tape-white'): Project {
  const draft = createDraft();
  return ProjectSchema.parse({
    ...draft,
    sources: [
      {
        id: 'src',
        tag: 'LP-1/1',
        panel: 'LP-1',
        circuit: '1',
        voltage: 120,
        phase: '1PH',
        breakerA: 20,
        poles: 1,
      },
    ],
    equipment: [
      {
        id: 'ps',
        tag: 'PS-1',
        catalogId: 'psu-24v-96w',
        category: 'psu',
        qty: 1,
        location: 'Cabinet',
        fedFrom: { ref: 'src' },
        feedLengthFt: 20,
        env: 'raceway',
      },
    ],
    loads: [
      {
        id: 'load',
        typeTag: 'T1',
        catalogId,
        lengthFt: watts / 4.4,
        zone: 'Test',
        fedFrom: { ref: 'ps', port: 'OUT1' },
        homeRunLengthFt: 10,
        feedMethod: 'end',
        env: 'riser',
      },
    ],
  });
}

describe('required engineering acceptance cases', () => {
  it('100 W, 24 V, 50 ft: #14/#12 fail; #10 passes, with a 43.6 ft terminal-compatible hint', () => {
    const a = evaluateWire(run(), wire('14'), seedCodeTables, settings);
    const b = evaluateWire(run(), wire('12'), seedCodeTables, settings);
    const c = evaluateWire(run(), wire('10'), seedCodeTables, settings);
    expect(a.vdV).toBeCloseTo(1.3083, 4);
    expect(a.vdPct).toBeCloseTo(5.4514, 4);
    expect(a.eligible).toBe(false);
    expect(b.vdV).toBeCloseTo(0.825, 4);
    expect(b.vdPct).toBeCloseTo(3.4375, 4);
    expect(b.eligible).toBe(false);
    expect(c.vdV).toBeCloseTo(0.51667, 4);
    expect(c.eligible).toBe(true);
    const selected = selectWire(run(), 'W-01', seedWires, seedCodeTables, settings);
    expect(selected.wireTypeId).toBe(wire('10').id);
    expect(selected.messages.find((m) => m.code === 'TERMINAL_OVERSIZE')?.text).toContain(
      '43.6 ft',
    );
  });
  it('RGBW common plus return uses 1.093 V; doubling the common reduces the drop', () => {
    const rgbw = run({
      type: 'class2-dc-multichannel',
      lengthFt: 30,
      currentA: 88 / 24,
      channelCurrentsA: [22 / 24, 22 / 24, 22 / 24, 22 / 24],
      required: { power: 1, channel: 4, ground: 0, signal: 0, dataPair: 0 },
    });
    expect(voltageDrop(rgbw, 7.95)).toBeCloseTo(1.093125, 5);
    expect(voltageDrop(rgbw, 7.95, 1, 2)).toBeCloseTo(0.655875, 5);
    expect(constructionMatches(rgbw, wire('18', 4), 2)).toBe(false);
  });
  it('TW maximum operating power is 88 W with each channel sized for its own full current', () => {
    const p = single(88, 'tape-tw');
    const tape = seedProducts.find((p) => p.id === 'tape-tw')!.specs as TapeSpecs;
    const profile = loadProfile(p.loads[0]!, tape, p.settings);
    expect(profile.watts).toBe(88);
    expect(profile.channelAmps).toEqual([88 / 24, 88 / 24]);
    const allOn = loadProfile(p.loads[0]!, { ...tape, powerBasis: 'all-channel-max' }, p.settings);
    expect(allOn.watts).toBe(44);
    const result = calculate(p, library());
    expect(result.loading.find((l) => l.kind === 'psu')?.wattsW).toBe(88);
  });
  it('96 W supply warns at 90 W and errors at 100 W', () => {
    const low = calculate(single(90), library());
    const high = calculate(single(100), library());
    expect(low.messages.some((m) => m.code === 'PSU_ABOVE_DERATE')).toBe(true);
    expect(low.messages.some((m) => m.code === 'PSU_OVERLOAD')).toBe(false);
    expect(high.messages.some((m) => m.code === 'PSU_OVERLOAD')).toBe(true);
  });
  it('12 supplies at 1.4 A require 21 A after continuous-load factor', () => {
    const p = single();
    p.equipment[0]!.qty = 12;
    p.loads = [];
    const libs = library();
    const item = libs.products.find((p) => p.id === 'psu-24v-96w')!;
    if (item.specs.kind !== 'psu') throw new Error('fixture');
    item.specs.maxInputA = 1.4;
    item.specs.maxInputAAtV = 120;
    const result = calculate(p, libs);
    expect(result.messages.find((m) => m.code === 'BREAKER_OVERLOAD')?.text).toContain('21 A');
    expect(result.runs.filter((r) => r.runId.includes('jumper'))).toHaveLength(11);
  });
  it('34 DMX receivers exceed unit loads, and address 510/footprint 4 overflows', () => {
    const p = demoProject();
    const first = p.equipment.find((e) => e.id === 'dec-1')!;
    p.equipment = [
      ...p.equipment.filter((e) => !e.id.startsWith('dec-')),
      ...Array.from({ length: 34 }, (_, i) => ({
        ...first,
        id: `d${i}`,
        tag: `DEC-${i}`,
        chainOrder: i,
        controlFrom: { ref: i ? `d${i - 1}` : 'con-1' },
        controlLengthFt: 35,
        dmx: {
          universe: 1,
          startAddress: i === 0 ? 510 : ('auto' as const),
          terminatorPresent: false,
        },
      })),
    ];
    p.loads = [];
    const graph = buildGraph(p, seedProducts);
    const patch = patchDmx(p, graph);
    const segments = dmxSegments(p, graph);
    expect(patch.messages.some((m) => m.code === 'DMX_ADDRESS_OVERFLOW')).toBe(true);
    expect(segments.messages.some((m) => m.code === 'DMX_UNIT_LOADS')).toBe(true);
    expect(segments.messages.some((m) => m.code === 'DMX_LENGTH')).toBe(true);
    expect(segments.messages.some((m) => m.code === 'DMX_NO_TERMINATOR')).toBe(true);
  });
  it('corrects the plan contradiction: 21.2 V fails a 21.5 V minimum; equality passes', () => {
    const w = wire('18');
    const r = run({ minOperatingV: 21.5, lengthFt: (2.8 * 1000) / (2 * (100 / 24) * 7.95) });
    const failed = selectWire(r, 'W-01', seedWires, seedCodeTables, settings, {
      wireTypeId: w.id,
      parallelSets: 1,
      parallelCommonConductors: 1,
    });
    expect(failed.endV).toBeCloseTo(21.2);
    expect(failed.messages.some((m) => m.code === 'TAPE_UNDERVOLTAGE')).toBe(true);
    r.lengthFt = (2.5 * 1000) / (2 * (100 / 24) * 7.95);
    expect(
      selectWire(r, 'W-01', seedWires, seedCodeTables, settings, {
        wireTypeId: w.id,
        parallelSets: 1,
        parallelCommonConductors: 1,
      }).messages.some((m) => m.code === 'TAPE_UNDERVOLTAGE'),
    ).toBe(false);
  });
  it('40 ft tape with a 32 ft limit suggests two feeds and accepting creates two runs', () => {
    const p = single(40 * 4.4);
    const result = calculate(p, library());
    expect(result.splits).toEqual([{ loadId: 'load', feeds: 2 }]);
    p.loads[0]!.feedMethod = 'multi-feed';
    p.loads[0]!.feeds = 2;
    const changed = calculate(p, library());
    expect(changed.splits).toEqual([]);
    expect(changed.runs.filter((r) => r.entityRef === 'load')).toHaveLength(2);
  });
  it('filters plenum and burial strictly, and repeats deterministically with stable tags', () => {
    const result = selectWire(
      run({ env: 'plenum', lengthFt: 10 }),
      'W-01',
      seedWires,
      seedCodeTables,
      settings,
    );
    expect(seedWires.find((w) => w.id === result.wireTypeId)?.plenum).toBe(true);
    expect(environmentMatches(wire('18'), 'direct-burial')).toBe(false);
    expect(
      seedWires.filter((w) => environmentMatches(w, 'direct-burial')).every((w) => w.directBurial),
    ).toBe(true);
    const p = demoProject();
    const a = calculate(p, library());
    const b = calculate(p, library());
    expect(a).toEqual(b);
    expect(EngineResultSchema.safeParse(a).success).toBe(true);
    const old = assignWireTags([run()], {});
    const changed = assignWireTags(
      [run(), run({ runId: 'new', from: { id: 'a', tag: 'A' } })],
      old,
    );
    expect(changed.run1).toBe(old.run1);
  });
});

describe('additional engineering boundaries', () => {
  it('handles distributed and three-phase drops, parallel sets and zero-current maximums', () => {
    const r = run({
      currentA: 4,
      lengthFt: 40,
      distributed: { qty: 4, homeRunFt: 10, interFixtureFt: 10 },
    });
    expect(voltageDrop(r, 1, 1, 1, 'distributed')).toBeCloseTo(0.2);
    expect(voltageDrop(r, 1)).toBeCloseTo(0.32);
    expect(voltageDrop({ ...r, phase: '3PH' }, 1)).toBeCloseTo((Math.sqrt(3) * 40 * 4) / 1000);
    expect(voltageDrop(r, 1, 2)).toBeCloseTo(0.16);
    expect(maximumLength({ ...r, currentA: 0 }, 1, 3)).toBeNull();
  });
  it('never falls back to resistance for missing Table 9, or silently relabels the edition', () => {
    expect(
      wireResistance(wire('12'), seedCodeTables, { ...settings, acVdMethod: 'effective-z' }, true),
    ).toBeNull();
    expect(
      wireResistance(wire('12'), seedCodeTables, { ...settings, necEdition: '2026' }),
    ).toBeNull();
    const line = seedWires.find(
      (w) => w.category === 'building-wire' && w.conductors[0]?.awg === '12',
    )!;
    expect(wireAmpacity(line, seedCodeTables, settings)).toBe(25);
    expect(wireAmpacity(line, seedCodeTables, { ...settings, terminationTempC: 60 })).toBe(20);
    const override = { ...line, resistanceOhmPerKft: 2.2 };
    expect(wireResistance(override, [], settings)).toBe(2.2);
  });
  it('resolves tag references, rejects missing refs, cycles and incompatible overrides', () => {
    const p = single();
    p.loads[0]!.fedFrom.ref = 'missing';
    expect(calculate(p, library()).messages.some((m) => m.code === 'UNRESOLVED_REF')).toBe(true);
    p.equipment[0]!.fedFrom.ref = 'PS-1';
    p.equipment[0]!.specOverrides = { kind: 'decoder' };
    const graph = buildGraph(p, seedProducts);
    expect(graph.messages.some((m) => m.code === 'CYCLE')).toBe(true);
    expect(graph.messages.some((m) => m.code === 'INVALID_SPEC')).toBe(true);
  });
  it('computes pixel currents with integer pixels and respects tape percentage margin', () => {
    const p = single(4.4, 'tape-pixel');
    const spec = seedProducts.find((p) => p.id === 'tape-pixel')!.specs;
    expect(loadProfile(p.loads[0]!, spec, settings).watts).toBeCloseTo(4.32);
    expect(
      loadProfile(p.loads[0]!, spec, { ...settings, tapeLengthMarginPct: 10 }).watts,
    ).toBeCloseTo(5.76);
    expect(inputCurrent(80, 120, seedProducts[0]!.specs)).toBeGreaterThan(80 / 120);
    expect(inputCurrent(80, 0, seedProducts[0]!.specs)).toBe(0);
    expect(loadProfile(p.loads[0]!, seedProducts[0]!.specs, settings).watts).toBe(0);
  });
  it('marks invalid manual wire overrides and preserves them for review', () => {
    const result = selectWire(run(), 'W-01', seedWires, seedCodeTables, settings, {
      wireTypeId: 'missing',
      parallelSets: 2,
      parallelCommonConductors: 1,
    });
    expect(result.overridden).toBe(true);
    expect(result.wireTypeId).toBeNull();
    expect(result.messages.some((m) => m.code === 'NO_VALID_WIRE')).toBe(true);
    expect(result.messages.some((m) => m.code === 'PARALLEL_REVIEW_REQUIRED')).toBe(true);
  });
  it('a complete demo has no errors and includes circuits, channel loading, schedules and terminators', () => {
    const result = calculate(demoProject(), library());
    expect(result.messages.filter((m) => m.severity === 'error')).toEqual([]);
    expect(result.loading.filter((l) => l.kind === 'circuit')).toHaveLength(2);
    expect(result.loading.filter((l) => l.kind === 'decoder')).toHaveLength(8);
    expect(result.patch).toHaveLength(2);
    expect(result.bom.some((b) => b.key === 'accessory:terminator')).toBe(true);
    expect(result.bom.find((b) => b.sku === 'EX-TAPE-WHITE')?.reels).toBe(1);
  });
  it('feeds a phase-dimmable 120 V fixture from an AC DMX decoder as a line-voltage run', () => {
    const l = library();
    const decoder = l.products.find((item) => item.id === 'decoder-4ch')!;
    const fixture = l.products.find((item) => item.id === 'downlight-line')!;
    l.products.push(
      CatalogItemSchema.parse({
        ...decoder,
        id: 'decoder-ac',
        sku: 'EX-DECODER-AC',
        specs: {
          ...decoder.specs,
          powerType: 'AC',
          inputVMin: 110,
          inputVMax: 130,
          channels: 1,
          dmxFootprint: 1,
          maxAPerChannel: 2,
          maxATotal: 2,
          maxWPerChannel: 100,
          maxWTotal: 100,
          outputDimming: 'phase-reverse',
        },
      }),
      CatalogItemSchema.parse({
        ...fixture,
        id: 'phase-downlight',
        sku: 'EX-DOWNLIGHT-PHASE',
        specs: { ...fixture.specs, inputV: 120, powerFactor: 0.9, dimming: ['phase-reverse'] },
      }),
    );
    const p = single();
    p.equipment[0]!.catalogId = 'decoder-ac';
    p.equipment[0]!.category = 'dmx-decoder';
    p.equipment[0]!.tag = 'DIM-1';
    p.loads[0]!.catalogId = 'phase-downlight';
    p.loads[0]!.fedFrom = { ref: 'ps', port: 'CH1' };
    p.loads[0]!.env = 'raceway';
    p.loads[0]!.qty = 2;
    delete p.loads[0]!.lengthFt;
    expect(powerPortOptions(p, l.products, 'ps').some((option) => option.value === 'LP-1/1')).toBe(
      true,
    );
    expect(
      powerPortOptions(p, l.products, 'load').some((option) => option.value === 'DIM-1::CH1'),
    ).toBe(true);
    const result = calculate(p, l);
    expect(result.messages.filter((m) => m.severity === 'error')).toEqual([]);
    expect(result.runs.find((r) => r.to.id === 'ps')?.type).toBe('lv-branch');
    const output = result.runs.find((r) => r.to.id === 'load')!;
    expect(output.type).toBe('lv-branch');
    expect(output.voltageV).toBe(120);
    expect(output.required.ground).toBe(1);
    expect(output.currentA).toBeCloseTo(30 / (120 * 0.9));
    expect(result.loading.find((row) => row.entityId === 'ps' && row.port === 'CH1')?.wattsW).toBe(
      30,
    );
    const rated = l.products.find((item) => item.id === 'decoder-ac')!;
    if (rated.specs.kind !== 'decoder') throw new Error('Expected decoder');
    rated.specs.maxAPerChannel = 0.2;
    expect(calculate(p, l).messages.some((m) => m.code === 'CHANNEL_OVERCURRENT')).toBe(true);
    const phaseFixture = l.products.find((item) => item.id === 'phase-downlight')!;
    if (phaseFixture.specs.kind !== 'fixture') throw new Error('Expected fixture');
    phaseFixture.specs.dimming = ['0-10V'];
    expect(
      powerPortOptions(p, l.products, 'load').some((option) => option.value === 'DIM-1::CH1'),
    ).toBe(false);
    expect(calculate(p, l).messages.some((m) => m.code === 'DRIVE_MISMATCH')).toBe(true);
  });
  it('does not mutate input project or libraries', () => {
    const p = demoProject();
    const l = library();
    const before = JSON.stringify([p, l]);
    calculate(p, l);
    expect(JSON.stringify([p, l])).toBe(before);
  });
});
