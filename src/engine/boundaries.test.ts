import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate, controlRunType } from './calculate';
import { buildGraph } from './graph';
import { patchDmx, dmxSegments } from './dmx';
import { powerPortOptions, controlPortOptions, supportedProtocols, parsePort } from './ports';
import { inputCurrent, loadProfile } from './loads';
import { CatalogItemSchema, type CatalogSpecs } from '../schemas/catalog';
import { ProjectSchema, ProjectSettingsSchema } from '../schemas/project';
import { createDraft } from '../schemas/workspace';
import { environmentMatches, wireAmpacity, wireResistance, selectWire } from './wireSelect';
import type { RunInput } from './model';

const setup = () => ({ p: demoProject(), l: seedLibrary() });
const codes = (result: ReturnType<typeof calculate>) => result.messages.map((m) => m.code);
const ccProject = () => {
  const { p, l } = setup();
  const driver = l.products.find((x) => x.specs.kind === 'driver')!;
  const fixture = l.products.find((x) => x.specs.kind === 'fixture' && x.specs.drive === 'CC')!;
  p.sources = p.sources.slice(0, 1);
  p.equipment = [{ ...p.equipment[0]!, catalogId: driver.id, category: 'driver' }];
  p.loads = [
    {
      ...p.loads[4]!,
      catalogId: fixture.id,
      qty: 1,
      fedFrom: { ref: 'PS-1', port: 'OUT1' },
      homeRunLengthFt: 10,
    },
  ];
  return { p, l };
};
describe('connection compatibility and limits', () => {
  it('offers voltage-compatible ports, excludes descendants and preserves tag parsing', () => {
    const { p, l } = setup();
    const tape = powerPortOptions(p, l.products, 'load-1');
    expect(tape.some((o) => o.value === 'DEC-1::CH1-4')).toBe(true);
    expect(tape.some((o) => o.value.startsWith('LP-'))).toBe(false);
    expect(powerPortOptions(p, l.products, 'ps-1').map((o) => o.value)).toContain('LP-1/12');
    expect(powerPortOptions(p, l.products, 'ps-1').some((o) => o.value.startsWith('DEC-1'))).toBe(
      false,
    );
    expect(parsePort('PS-1::OUT1')).toEqual({ ref: 'PS-1', port: 'OUT1' });
    expect(parsePort('LP-1/12')).toEqual({ ref: 'LP-1/12' });
    expect(parsePort('')).toEqual({ ref: '' });
    expect(powerPortOptions(p, l.products, 'missing').length).toBeGreaterThan(0);
    p.loads[0]!.catalogId = 'tape-pixel';
    expect(powerPortOptions(p, l.products, 'load-1').some((o) => o.value.startsWith('LP-'))).toBe(
      false,
    );
  });
  it('offers matching CC driver ports and filters mismatched current ratings', () => {
    const { p, l } = ccProject();
    expect(powerPortOptions(p, l.products, p.loads[0]!.id).map((o) => o.value)).toContain(
      'PS-1::OUT1',
    );
    p.equipment[0]!.specOverrides = { kind: 'driver', outputmA: 999 };
    expect(powerPortOptions(p, l.products, p.loads[0]!.id)).toEqual([]);
  });
  it('filters control ports by direction and protocol, including pixel loads', () => {
    const { p, l } = setup();
    expect(
      controlPortOptions(p, l.products, 'out', undefined, 'dec-1').map((o) => o.value),
    ).toContain('CON-1::DATA-OUT');
    expect(controlPortOptions(p, l.products, 'out', 'DALI-2')).toEqual([]);
    expect(
      controlPortOptions(p, l.products, 'in', 'DMX512').some((o) => o.value === 'DEC-1::DATA-IN'),
    ).toBe(true);
    p.loads[0]!.catalogId = 'tape-pixel';
    expect(controlPortOptions(p, l.products, 'in', 'SPI').some((o) => o.value === 'load-1')).toBe(
      true,
    );
    expect(supportedProtocols(undefined, 'in')).toEqual([]);
    expect(
      supportedProtocols(l.products.find((i) => i.id === 'psu-24v-96w')!.specs, 'out'),
    ).toEqual([]);
  });
  it('enforces universe and device capacities through a chain', () => {
    const { p, l } = setup();
    p.equipment.find((e) => e.id === 'con-1')!.specOverrides = {
      kind: 'controller',
      maxUniverses: 1,
      maxBusDevices: 1,
    };
    p.equipment.find((e) => e.id === 'dec-2')!.dmx!.universe = 2;
    const r = calculate(p, l);
    expect(r.messages.filter((m) => m.code === 'DEVICE_CAPACITY')).toHaveLength(2);
    expect(codes(r)).toContain('DMX_TOPOLOGY');
  });
  it('counts whole pixels downstream and respects device data-length limits', () => {
    const { p, l } = setup();
    const pixel = l.products.find((i) => i.category === 'pixel-controller')!;
    const c = p.equipment.find((e) => e.id === 'con-1')!;
    c.catalogId = pixel.id;
    c.category = 'pixel-controller';
    c.specOverrides = { kind: 'controller', maxPixels: 1, maxDataLengthFt: 5 };
    p.loads[0]!.catalogId = 'tape-pixel';
    p.controlLinks = [
      {
        id: 'pixel-link',
        from: { ref: c.id },
        to: { ref: 'load-1' },
        protocol: 'SPI',
        lengthFt: 20,
        env: 'riser',
      },
    ];
    const r = calculate(p, l);
    expect(r.messages.some((m) => m.code === 'DEVICE_CAPACITY' && m.text.includes('pixels'))).toBe(
      true,
    );
    expect(codes(r)).toContain('SPI_DATA_LENGTH');
    expect(
      r.messages.some((m) => m.entityRef === 'pixel-link' && m.code === 'PROTOCOL_MISMATCH'),
    ).toBe(false);
  });
  it('maps each control protocol to its physical cable family', () => {
    for (const [protocol, type] of [
      ['CRMX-wireless', 'wireless'],
      ['sACN', 'ethernet'],
      ['Art-Net', 'ethernet'],
      ['SPI', 'spi-data'],
      ['0-10V', '0-10v'],
      ['1-10V', '0-10v'],
      ['DALI-2', 'dali'],
      ['Lutron-QS', 'lutron-qs'],
      ['Lutron-EcoSystem', 'lutron-ecosystem'],
      ['RDM', 'dmx'],
    ] as const)
      expect(controlRunType(protocol)).toBe(type);
  });
});
describe('electrical and topology boundaries', () => {
  it('keeps full CC series current in every interfixture segment and rejects parallel branches', () => {
    const { p, l } = ccProject();
    p.settings.vdMethod = 'distributed';
    p.loads[0]!.qty = 2;
    p.loads[0]!.interFixtureLengthFt = 10;
    const result = calculate(p, l);
    const r = result.runs.find((r) => r.entityRef === p.loads[0]!.id)!;
    expect(r.lengthFt).toBe(20);
    expect(r.distributed).toBeUndefined();
    p.loads.push({ ...p.loads[0]!, id: 'parallel' });
    expect(codes(calculate(p, l))).toContain('INVALID_SPEC');
    p.loads[0]!.feedMethod = 'double-end';
    expect(calculate(p, l).runs.filter((r) => r.entityRef === p.loads[0]!.id)).toHaveLength(1);
  });
  it('handles manufacturer fallback data and rejects incompatible manual cable choices', () => {
    const { l } = setup();
    const settings = ProjectSettingsSchema.parse({});
    const wire = structuredClone(l.wires.find((w) => w.id === 'thhn-12')!);
    expect(environmentMatches(wire, 'dry-concealed')).toBe(false);
    expect(environmentMatches(wire, 'wet')).toBe(wire.wet);
    expect(environmentMatches(wire, 'outdoor-exposed')).toBe(wire.wet && wire.sunlightResistant);
    expect(
      wireAmpacity({ ...wire, ampacityTempLimitC: 90 }, l.codeTables, {
        ...settings,
        terminationTempC: 90,
      }),
    ).toBe(30);
    const r: RunInput = {
      runId: 'test',
      type: 'lv-branch',
      from: { id: 's', tag: 'S' },
      to: { id: 't', tag: 'T' },
      entityRef: 't',
      currentA: 2,
      wattsW: 240,
      voltageV: 120,
      lengthFt: 50,
      phase: '1PH',
      channelCurrentsA: [],
      terminalMaxAwg: [],
      env: 'raceway',
      required: { power: 2, ground: 1, channel: 0, signal: 0, dataPair: 0 },
      breakerA: 100,
    };
    expect(
      selectWire(r, 'W-1', [wire], l.codeTables, settings, {
        wireTypeId: wire.id,
        parallelSets: 1,
        parallelCommonConductors: 1,
      }).messages.some((m) => m.text.includes('OCPD')),
    ).toBe(true);
    expect(
      selectWire(
        { ...r, type: 'ethernet', lengthFt: 400 },
        'W-1',
        l.wires,
        l.codeTables,
        settings,
      ).messages.some((m) => m.code === 'DATA_LENGTH'),
    ).toBe(true);
    expect(
      selectWire({ ...r, env: 'direct-burial' }, 'W-1', [wire], l.codeTables, settings, {
        wireTypeId: wire.id,
        parallelSets: 1,
        parallelCommonConductors: 1,
      }).candidates,
    ).toHaveLength(1);
    expect(
      selectWire({ ...r, breakerA: 20 }, 'W-1', [wire], [], settings).messages.some(
        (m) => m.code === 'CODE_TABLE_UNAVAILABLE',
      ),
    ).toBe(true);
    wire.conductors = wire.conductors.map((c) => ({
      ...c,
      resistanceOhmPerKft: 1.7,
      ampacityA: 22,
    }));
    expect(wireAmpacity(wire, [], settings)).toBe(22);
    expect(wireResistance(wire, [], settings)).toBe(1.7);
    const fixture = structuredClone(
      l.wires.find((w) => w.category === 'class2-power' && w.conductors[0]!.awg === '18')!,
    );
    delete fixture.ampacityA;
    fixture.conductors = fixture.conductors.map((c) => {
      const copy = { ...c };
      delete copy.ampacityA;
      return copy;
    });
    expect(wireAmpacity(fixture, l.codeTables, settings)).toBe(6);
    const impedance = {
      ...l.codeTables.find((t) => t.kind === 'effective-z')!,
      status: 'available',
      rows: [{ awg: '12', effectiveZOhmPerKft: 2 }],
    } as (typeof l.codeTables)[number];
    expect(
      wireResistance(wire, [impedance], { ...settings, acVdMethod: 'effective-z' }, true),
    ).toBe(2);
  });
  it('warns for phase dimmer compatibility, inrush and mismatched catalog categories', () => {
    const { p, l } = setup();
    p.sources[0]!.switching = 'phase-forward';
    p.equipment[0]!.specOverrides = { kind: 'psu', maxUnitsPer20ABreaker: 1 };
    p.equipment[2]!.category = 'driver';
    const r = calculate(p, l);
    expect(codes(r)).toEqual(
      expect.arrayContaining(['INRUSH_LIMIT', 'PHASE_DIMMER_COMPAT_UNKNOWN', 'INVALID_SPEC']),
    );
    const tape = l.products.find((i) => i.id === 'tape-white')!.specs;
    if (tape.kind !== 'tape') throw new Error('fixture');
    expect(
      loadProfile(
        { ...p.loads[0]!, lengthFt: 1 },
        { ...tape, channelWPerFtMax: undefined },
        p.settings,
      ).channelAmps,
    ).toEqual([4.4 / 24]);
    p.equipment.find((e) => e.id === 'dec-1')!.dmx = undefined;
    p.equipment.find((e) => e.id === 'dec-1')!.specOverrides = {
      kind: 'decoder',
      protocolIn: ['none', 'DALI-2'],
    };
    expect(buildGraph(p, l.products).control.some((e) => e.protocol === 'DALI-2')).toBe(true);
  });
  it('uses constant driver current for wire and output loading and detects compliance limits', () => {
    const { p, l } = ccProject();
    let r = calculate(p, l);
    const driver = l.products.find((i) => i.id === p.equipment[0]!.catalogId)!.specs;
    if (driver.kind !== 'driver') throw new Error('fixture');
    expect(r.runs.find((x) => x.entityRef === p.loads[0]!.id)?.currentA).toBe(
      driver.outputmA! / 1000,
    );
    expect(r.loading.find((x) => x.kind === 'psu')?.currentA).toBe(driver.outputmA! / 1000);
    p.loads[0]!.qty = 100;
    r = calculate(p, l);
    expect(codes(r)).toContain('CC_COMPLIANCE');
    p.loads[0]!.catalogId = 'tape-white';
    p.loads[0]!.lengthFt = 10;
    expect(codes(calculate(p, l))).toContain('DRIVE_MISMATCH');
  });
  it('calculates verified three-phase inputs and rejects unverified equipment phases', () => {
    const { p, l } = setup();
    p.loads = p.loads.filter((x) => !x.qty);
    p.equipment = p.equipment.filter((x) => x.id !== 'con-1');
    p.sources[0]!.voltage = 208;
    p.sources[0]!.phase = '3PH';
    p.sources[0]!.poles = 3;
    expect(codes(calculate(p, l))).toContain('INVALID_SPEC');
    p.equipment[0]!.specOverrides = { kind: 'psu', inputPhase: '3PH' };
    p.equipment[1]!.specOverrides = { kind: 'psu', inputPhase: '3PH' };
    const r = calculate(p, l);
    const feed = r.runs.find((x) => x.entityRef === 'ps-1')!;
    expect(feed.phase).toBe('3PH');
    expect(feed.required.power).toBe(3);
    const psu = l.products.find((i) => i.id === 'psu-24v-96w')!.specs;
    if (psu.kind !== 'psu') throw new Error('fixture');
    expect(inputCurrent(80, 208, { ...psu, inputPhase: '3PH', maxInputA: undefined })).toBeCloseTo(
      80 / psu.efficiency / 208 / psu.powerFactor / Math.sqrt(3),
    );
    expect(inputCurrent(80, 24, { ...psu, inputType: 'DC', maxInputA: undefined })).toBeCloseTo(
      80 / psu.efficiency / 24,
    );
    p.sources[0]!.poles = 1;
    expect(codes(calculate(p, l))).toContain('INVALID_SPEC');
  });
  it('detects invalid output ports, channel allocations, voltages and device catalog IDs', () => {
    const { p, l } = setup();
    p.loads[0]!.fedFrom.port = 'CH4-7';
    p.equipment[2]!.fedFrom.ref = 'load-1';
    p.equipment[0]!.specOverrides = { kind: 'psu', outputV: 12 };
    p.loads[3]!.catalogId = 'missing';
    p.loads[4]!.catalogId = 'psu-24v-96w';
    const r = calculate(p, l);
    expect(codes(r)).toEqual(
      expect.arrayContaining([
        'INVALID_PORT',
        'VOLTAGE_MISMATCH',
        'UNRESOLVED_REF',
        'INVALID_SPEC',
      ]),
    );
  });
  it('reserves manual DMX addresses, reports overlap and returns null on exhaustion', () => {
    const { p, l } = setup();
    const decs = p.equipment.filter((e) => e.dmx);
    decs[0]!.dmx!.startAddress = 1;
    decs[1]!.dmx!.startAddress = 1;
    expect(
      patchDmx(p, buildGraph(p, l.products)).messages.some((m) => m.code === 'DMX_ADDRESS_OVERLAP'),
    ).toBe(true);
    decs[0]!.specOverrides = { kind: 'decoder', dmxFootprint: 512 };
    decs[1]!.dmx!.startAddress = 'auto';
    const patched = patchDmx(p, buildGraph(p, l.products));
    expect(patched.patch[1]!.startAddress).toBeNull();
    expect(patched.messages.some((m) => m.code === 'DMX_ADDRESS_OVERFLOW')).toBe(true);
  });
  it('splits physical DMX segments at isolated devices and flags branches and absent termination', () => {
    const { p, l } = setup();
    const source = p.equipment.find((e) => e.id === 'con-1')!;
    source.specOverrides = { kind: 'controller', startsNewSegment: true };
    p.equipment.find((e) => e.id === 'dec-2')!.controlFrom = { ref: source.id, port: 'DATA-OUT' };
    p.settings.dmxMaxLengthFt = 1;
    const r = dmxSegments(p, buildGraph(p, l.products));
    expect(r.segments).toHaveLength(1);
    expect(r.messages.map((m) => m.code)).toEqual(
      expect.arrayContaining(['DMX_LENGTH', 'DMX_NO_TERMINATOR', 'DMX_TOPOLOGY']),
    );
    p.equipment.find((e) => e.id === 'dec-2')!.controlFrom = undefined;
    expect(
      dmxSegments(p, buildGraph(p, l.products)).messages.some((m) =>
        m.text.includes('no resolved wired'),
      ),
    ).toBe(true);
  });
  it('uses all-channel ratings only when explicitly declared and validates AC/DC phase constraints', () => {
    const { p, l } = setup();
    const tape = l.products.find((i) => i.id === 'tape-tw')!.specs;
    if (tape.kind !== 'tape') throw new Error('fixture');
    const profile = loadProfile(
      { ...p.loads[1]!, lengthFt: 10 },
      { ...tape, powerBasis: 'all-channel-max', wPerFtMax: 8.8 },
      ProjectSettingsSchema.parse({}),
    );
    expect(profile.watts).toBe(44);
    const ps = l.products[0]!;
    expect(
      CatalogItemSchema.safeParse({
        ...ps,
        specs: { ...ps.specs, inputType: 'DC', inputPhase: '3PH' },
      }).success,
    ).toBe(false);
    expect(inputCurrent(24, 12, tape)).toBe(2);
    expect(calculate(ProjectSchema.parse(createDraft()), l).runs).toEqual([]);
    const unknown = {
      kind: 'accessory',
      function: 'other',
      ports: [],
      listings: [],
    } as CatalogSpecs;
    expect(supportedProtocols(unknown, 'in')).toEqual([]);
  });
});
