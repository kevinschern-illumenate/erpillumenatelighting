import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { codeTables } from '@ill/data/codeTables';
import { WireTypeSchema } from '@ill/core-schemas/wire';
import {
  addControl,
  autoPowerControls,
  controlChecks,
  controlFeedOptions,
  controlInputOptions,
  deriveControlLinks,
  moveControl,
  PATCH_FT,
  removeControl,
  scheduleControlDrift,
  scheduleControlLines,
  scheduleIncompleteLines,
  setControlFeed,
  setControlInput,
  setDmx,
  setZoneControl,
  syncScheduleControls,
  zoneControlOptions,
} from './controls';
import { checkDesign, vdLimits } from './designCheck';
import { expandRuns } from './expand';
import {
  addSupply,
  addZone,
  assignmentProblem,
  assignRuns,
  assignToCircuit,
  autoAssignRuns,
  catalogMap,
  decoderPortFor,
  FROM_SCHEDULE,
  freeDecoderPort,
  moveSupply,
  outputLoads,
  removeSupply,
  setRunZone,
  syncScheduleSupplies,
  updateZone,
  type PowerContext,
} from './power';
import { addCabinet, addCircuit, distanceDefaults, setCabinetFeed, updateCabinet } from './site';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));
const opened = read('open-design/expected.json');
const baseLines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const payload = read('catalog/payload.json');
const items = (payload.items as unknown[]).map((item) => CatalogItemSchema.parse(item));
const wires = (payload.wires as unknown[]).map((wire) => WireTypeSchema.parse(wire));

/** A DMX controller with two universes and a 0-10V dimmer, for zone control. */
const dmxController = CatalogItemSchema.parse({
  id: 'ctl:TEST-DMX-2U',
  sku: 'TEST-DMX-2U',
  erpItemCode: 'TEST-DMX-2U',
  brand: 'ilLumenate',
  model: 'Test DMX controller',
  category: 'dmx-controller',
  description: 'Test two-universe DMX controller',
  isExample: false,
  source: { kind: 'manufacturer', reference: 'test' },
  localOverrides: [],
  specs: {
    kind: 'controller',
    inputType: 'AC',
    inputVMin: 100,
    inputVMax: 277,
    ownPowerW: 4,
    powerFactor: 0.9,
    protocolIn: [],
    protocolOut: ['DMX512'],
    ports: [
      { name: 'U1', direction: 'out', protocol: 'DMX512' },
      { name: 'U2', direction: 'out', protocol: 'DMX512' },
    ],
    terminalMaxAwg: '16',
  },
});
const dimmer = CatalogItemSchema.parse({
  ...dmxController,
  id: 'ctl:TEST-DIM-010',
  sku: 'TEST-DIM-010',
  erpItemCode: 'TEST-DIM-010',
  model: 'Test 0-10V dimmer',
  category: '0-10v-dimmer',
  specs: {
    kind: 'controller',
    inputType: 'AC',
    inputVMin: 100,
    inputVMax: 277,
    ownPowerW: 1,
    powerFactor: 0.9,
    protocolIn: [],
    protocolOut: ['0-10V'],
    ports: [{ name: 'DIM', direction: 'out', protocol: '0-10V', maxDevices: 1 }],
    terminalMaxAwg: '16',
  },
});
const catalog: CatalogItem[] = [...items, dmxController, dimmer];

/** The TEST schedule plus a dealer line of two decoders and one of a DMX controller. */
const controlLines: Line[] = [
  ...baseLines,
  {
    ...baseLines.find((line) => line.key === 'h1acc')!,
    key: 'k1dec',
    lineKey: 'k1dec',
    lineId: 'K1',
    idx: 11,
    qty: 2,
    location: 'Kitchen',
    accessoryItem: 'TEST-DEC-4',
    powerSupplyForLine: null,
  },
  {
    ...baseLines.find((line) => line.key === 'h1acc')!,
    key: 'l1dmx',
    lineKey: 'l1dmx',
    lineId: 'L1',
    idx: 12,
    qty: 1,
    location: '',
    accessoryItem: 'TEST-DMX-2U',
    powerSupplyForLine: null,
  },
];
const context: PowerContext = { catalog: catalogMap(catalog), lines: controlLines, builds };
const defaults = distanceDefaults({});
const kitchen = 'space-kitchen';
const valid = (value: Design) => expect(() => DesignSchema.parse(value)).not.toThrow();

function design(): Design {
  const { spaces, runs } = expandRuns(controlLines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  return { ...base, site: { ...base.site, spaces, cabinets: [] }, runs, zones: [] };
}
const run = (value: Design, key: string) => value.runs.find((item) => item.key === key)!;
const rgb = (value: Design, key: string) => {
  run(value, key).catalogId = 'tape:TEST-TAPE-RGB:6:free';
};

/** A kitchen cabinet on a 120 V circuit with a 96 W supply and a decoder powered from it. */
function powered() {
  const value = design();
  const cabinet = addCabinet(value, kitchen, defaults);
  const circuit = addCircuit(value);
  updateCabinet(value, cabinet, { sourceId: circuit });
  const psu = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
  const decoder = addControl(value, context, cabinet, 'ctl:TEST-DEC-4');
  setControlFeed(value, context, decoder, `${psu}::OUT1`);
  return { value, cabinet, circuit, psu, decoder };
}

describe('controls on the schedule', () => {
  it('reads the dealer’s control lines and brings one control per unit into the design', () => {
    expect(scheduleControlLines(context).map((entry) => [entry.line.key, entry.catalogId])).toEqual([
      ['k1dec', 'ctl:TEST-DEC-4'],
      ['l1dmx', 'ctl:TEST-DMX-2U'],
    ]);
    const value = design();
    const cabinetFor = (spaceId: string) => addCabinet(value, spaceId, defaults);
    syncScheduleSupplies(value, context, cabinetFor);
    expect(scheduleControlDrift(value, context)).toEqual({ missing: 3, extra: 0 });
    expect(syncScheduleControls(value, context, cabinetFor)).toEqual({ added: 3, removed: 0 });
    expect(
      value.project.equipment.map((item) => [item.tag, item.category, item.scheduleLine, item.notes, item.enclosure]),
    ).toEqual([
      ['PS-1', 'psu', 'h1acc', FROM_SCHEDULE, 'cab-1'],
      ['PS-2', 'psu', 'h1acc', FROM_SCHEDULE, 'cab-1'],
      ['DEC-1', 'dmx-decoder', 'k1dec', FROM_SCHEDULE, 'cab-1'],
      ['DEC-2', 'dmx-decoder', 'k1dec', FROM_SCHEDULE, 'cab-1'],
      // No location: it joins the cabinet holding the supplies.
      ['CTL-1', 'dmx-controller', 'l1dmx', FROM_SCHEDULE, 'cab-1'],
    ]);
    expect(value.project.equipment.find((item) => item.tag === 'DEC-1')?.dmx).toEqual({
      universe: 1,
      startAddress: 'auto',
    });
    // Supplies and controls keep separate counts.
    expect(scheduleControlDrift(value, context)).toEqual({ missing: 0, extra: 0 });
    expect(syncScheduleControls(value, context, cabinetFor)).toEqual({ added: 0, removed: 0 });
    expect(syncScheduleSupplies(value, context, cabinetFor)).toEqual({ added: 0, removed: 0 });

    // One decoder fewer on the schedule drops the idle one; the busy one keeps its runs.
    expect(autoPowerControls(value, context)).toBe(2);
    assignRuns(value, context, ['a1linear:1:1'], 'DEC-1', 'CH1');
    const fewer = {
      ...context,
      lines: controlLines.map((line) => (line.key === 'k1dec' ? { ...line, qty: 1 } : line)),
    };
    expect(syncScheduleControls(value, fewer, cabinetFor)).toEqual({ added: 0, removed: 1 });
    expect(value.project.equipment.map((item) => item.tag)).toEqual(['PS-1', 'PS-2', 'DEC-1', 'CTL-1']);
    expect(run(value, 'a1linear:1:1').assignment).toEqual({ equipmentId: 'DEC-1', port: 'CH1' });
    valid(value);
  });

  it('names schedule lines whose product is incomplete instead of dropping them silently', () => {
    const lines = [...controlLines, { ...controlLines.at(-1)!, key: 'm1bad', lineId: 'M1', accessoryItem: 'TEST-PSU-BAD' }];
    expect(scheduleIncompleteLines({ ...context, lines })).toEqual([{ lineId: 'M1', itemCode: 'TEST-PSU-BAD' }]);
  });
});

describe('power for controls', () => {
  it('feeds AC controls from the cabinet circuit and DC controls from a supply in the same cabinet', () => {
    const { value, cabinet, circuit, psu, decoder } = powered();
    const controller = addControl(value, context, cabinet, 'ctl:TEST-DMX-2U');
    expect(value.project.equipment.find((item) => item.id === controller)?.fedFrom).toEqual({ ref: circuit });
    expect(value.project.equipment.find((item) => item.id === decoder)).toMatchObject({
      fedFrom: { ref: psu, port: 'OUT1' },
      feedLengthFt: PATCH_FT,
    });
    expect(controlFeedOptions(value, context, decoder).map((option) => option.value)).toEqual([`${psu}::OUT1`]);
    expect(controlFeedOptions(value, context, controller).map((option) => option.value)).toEqual([circuit]);
    expect(() => setControlFeed(value, context, controller, `${psu}::OUT1`)).toThrow('cannot take power from there');
    // A supply in another cabinet is not offered.
    const hall = addCabinet(value, 'space-hall', defaults);
    const far = addSupply(value, context, hall, 'drv:TEST-PSU-96');
    expect(controlFeedOptions(value, context, decoder).some((option) => option.value.startsWith(far))).toBe(false);
    // The cabinet's feed length changes do not override a supply feed.
    setCabinetFeed(value, cabinet, 40, false);
    expect(value.project.equipment.find((item) => item.id === decoder)).toMatchObject({
      fedFrom: { ref: psu, port: 'OUT1' },
      feedLengthFt: PATCH_FT,
    });
    expect(value.project.equipment.find((item) => item.id === controller)?.feedLengthFt).toBe(40);
    valid(value);
  });

  it('refuses to power a decoder from an output that dims a zone', () => {
    const { value, cabinet, psu } = powered();
    const second = addControl(value, context, cabinet, 'ctl:TEST-DEC-4');
    const zone = addZone(value, '0-10V');
    setRunZone(value, context, ['a1linear:1:1'], zone);
    const other = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    assignRuns(value, context, ['a1linear:1:1'], other, 'OUT1');
    expect(() => setControlFeed(value, context, second, `${other}::OUT1`)).toThrow(
      'is dimmed with Zone 1; power DEC-2 from an undimmed output',
    );
    // And the other way round: a dimmed zone does not go on an output that powers a decoder.
    expect(assignmentProblem(value, context, ['a1linear:1:1'], psu, 'OUT1')).toBe(
      'PS-1/OUT1 powers DEC-1; a dimmed zone needs an output of its own',
    );
  });

  it('drops a supply feed when the control or its supply leaves the cabinet, and when the supply is removed', () => {
    const { value, psu, decoder } = powered();
    const hall = addCabinet(value, 'space-hall', defaults);
    moveControl(value, decoder, hall);
    expect(value.project.equipment.find((item) => item.id === decoder)?.fedFrom).toEqual({ ref: 'unassigned' });
    const again = powered();
    moveSupply(again.value, again.psu, addCabinet(again.value, 'space-hall', defaults));
    expect(again.value.project.equipment.find((item) => item.id === again.decoder)?.fedFrom).toEqual({
      ref: 'unassigned',
    });
    const third = powered();
    removeSupply(third.value, third.psu);
    expect(third.value.project.equipment.map((item) => [item.id, item.fedFrom])).toEqual([
      [third.decoder, { ref: 'unassigned' }],
    ]);
    expect(psu).toBe('PS-1');
  });
});

describe('decoder channels', () => {
  it('needs power first, then checks voltage, width, overlap, zone and current', () => {
    const value = design();
    const cabinet = addCabinet(value, kitchen, defaults);
    const decoder = addControl(value, context, cabinet, 'ctl:TEST-DEC-4');
    const problem = (keys: string[], port: string) => assignmentProblem(value, context, keys, decoder, port);
    expect(problem(['a1linear:1:1'], 'CH1')).toBe('Power DEC-1 from a supply output first');
    const psu = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    setControlFeed(value, context, decoder, `${psu}::OUT1`);

    expect(problem(['e1other:1:1'], 'CH1')).toBe('E1-1.1 is line voltage; feed it from a panel circuit, not a decoder');
    expect(problem(['a1linear:1:1'], 'CH5')).toBe('DEC-1 has no output CH5');
    rgb(value, 'b1tape:1:1');
    expect(problem(['b1tape:1:1'], 'CH1')).toBe('B1-1.1 needs 3 channels; CH1 has 1');
    expect(freeDecoderPort(value, context, decoder, 3)).toBe('CH1-3');
    assignRuns(value, context, ['b1tape:1:1'], decoder, 'CH1-3');
    expect(freeDecoderPort(value, context, decoder, 3)).toBeNull();
    expect(freeDecoderPort(value, context, decoder, 1)).toBe('CH4');
    expect(problem(['a1linear:1:1'], 'CH2')).toBe('DEC-1/CH2 overlaps CH1-3, which B1-1.1 uses');
    expect(decoderPortFor(value, context, ['a1linear:1:1'], decoder)).toBe('CH4');
    expect(() => decoderPortFor(value, context, ['a1linear:1:1', 'b1tape:1:1'], decoder)).toThrow(
      'Select runs with the same number of channels',
    );

    const zone = addZone(value, '0-10V', 'Dim');
    setRunZone(value, context, ['a1linear:1:1'], zone);
    expect(problem(['a1linear:1:1'], 'CH4')).toBe('Dim dims by 0-10V; DEC-1 dims by DMX');
    setRunZone(value, context, ['a1linear:1:1']);
    const dmx = addZone(value, 'DMX512', 'Colour');
    setRunZone(value, context, ['a1linear:1:1'], dmx);
    expect(problem(['a1linear:1:1'], 'CH4')).toBe('DEC-1 would feed more than one zone; give each zone its own decoder');
    setRunZone(value, context, ['b1tape:1:1'], dmx);
    expect(problem(['a1linear:1:1'], 'CH4')).toBeNull();

    // The decoder's load counts on the supply output that powers it.
    expect(outputLoads(value, psu, new Set(), context.catalog).get('OUT1')).toBe(21.6);
    assignRuns(value, context, ['a1linear:1:1'], decoder, 'CH4');
    expect(outputLoads(value, psu, new Set(), context.catalog).get('OUT1')).toBe(48);
    // 76.8 W usable on the supply's output: 48 W there already, so 43.3 W more is refused.
    run(value, 'b1tape:1:2').zoneId = dmx;
    expect(problem(['b1tape:1:2'], 'CH4')).toBe('PS-1/OUT1 would carry 91.3 W of its 76.8 W usable');
    // A zone method a decoder cannot dim is refused for the runs already on it.
    expect(() => updateZone(value, dmx, { method: '0-10V' }, context)).toThrow('Colour dims by 0-10V; DEC-1 dims by DMX');
    expect(value.zones.find((item) => item.id === dmx)?.method).toBe('DMX512');
    valid(value);
  });

  it('enforces per-channel current', () => {
    const { value, decoder } = powered();
    run(value, 'b1tape:1:2').watts = 130; // 5.4 A at 24 V on one channel
    expect(assignmentProblem(value, context, ['b1tape:1:2'], decoder, 'CH1')).toBe(
      'DEC-1/CH1 would draw 5.42 A per channel of its 5 A',
    );
  });

  it('auto-assigns DMX-zone runs to decoder channels, others to supplies', () => {
    const { value, decoder } = powered();
    const dmx = addZone(value, 'DMX512');
    setRunZone(value, context, ['a1linear:1:1', 'a1linear:1:2'], dmx);
    expect(assignmentProblem(value, context, ['a1linear:1:1'], decoder, 'CH1')).toBeNull();
    value.runs = value.runs.filter((item) => ['a1linear:1:1', 'a1linear:1:2', 'b1tape:1:1'].includes(item.key));
    expect(autoAssignRuns(value, context)).toBe(3);
    expect(run(value, 'a1linear:1:1').assignment?.equipmentId).toBe(decoder);
    expect(run(value, 'a1linear:1:2').assignment?.equipmentId).toBe(decoder);
    expect(new Set([run(value, 'a1linear:1:1').assignment?.port, run(value, 'a1linear:1:2').assignment?.port]).size).toBe(2);
    expect(run(value, 'b1tape:1:1').assignment?.equipmentId).not.toBe(decoder);
  });
});

describe('zones and their controls', () => {
  it('offers matching control outputs and lets go of one when the method changes', () => {
    const { value, cabinet } = powered();
    const controller = addControl(value, context, cabinet, 'ctl:TEST-DMX-2U');
    const dim = addControl(value, context, cabinet, 'ctl:TEST-DIM-010');
    const dmx = addZone(value, 'DMX512');
    const zone = value.zones.find((item) => item.id === dmx)!;
    expect(zoneControlOptions(value, context, zone).map((option) => option.value)).toEqual([
      `${controller}::U1`,
      `${controller}::U2`,
    ]);
    expect(() => setZoneControl(value, context, dmx, `${dim}::DIM`)).toThrow('does not send DMX512');
    setZoneControl(value, context, dmx, `${controller}::U2`);
    expect(zone.control).toEqual({ equipmentId: controller, port: 'U2' });
    updateZone(value, dmx, { method: 'CRMX-wireless' }, context);
    expect(zone.control).toEqual({ equipmentId: controller, port: 'U2' }); // still DMX512 out
    updateZone(value, dmx, { method: '0-10V' }, context);
    expect(zone.control).toBeUndefined();
    const phase = addZone(value, 'phase-forward');
    expect(() => setZoneControl(value, context, phase, `${dim}::DIM`)).toThrow('has no control output to choose');
    // Removing the control lets go of the zone.
    setZoneControl(value, context, dmx, `${dim}::DIM`);
    removeControl(value, dim);
    expect(zone.control).toBeUndefined();
    valid(value);
  });

  it('derives a DMX daisy chain through the zone’s decoders and a 0-10V star to its supplies', () => {
    const { value, cabinet, psu, decoder } = powered();
    const second = addControl(value, context, cabinet, 'ctl:TEST-DEC-4');
    const other = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    setControlFeed(value, context, second, `${other}::OUT1`);
    const controller = addControl(value, context, cabinet, 'ctl:TEST-DMX-2U');
    const dim = addControl(value, context, cabinet, 'ctl:TEST-DIM-010');
    const dmx = addZone(value, 'DMX512');
    const soft = addZone(value, '0-10V');
    setRunZone(value, context, ['a1linear:1:1', 'a1linear:1:2'], dmx);
    assignRuns(value, context, ['a1linear:1:1'], second, 'CH1');
    assignRuns(value, context, ['a1linear:1:2'], decoder, 'CH1');
    setRunZone(value, context, ['b1tape:1:1'], soft);
    const third = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    assignRuns(value, context, ['b1tape:1:1'], third, 'OUT1');
    setZoneControl(value, context, dmx, `${controller}::U1`);
    setZoneControl(value, context, soft, `${dim}::DIM`);

    const links = deriveControlLinks(value, context.catalog);
    expect(links.map((link) => [link.protocol, `${link.from.ref}/${link.from.port}`, `${link.to.ref}/${link.to.port ?? ''}`])).toEqual([
      ['DMX512', `${controller}/U1`, `${decoder}/DATA-IN`],
      ['DMX512', `${decoder}/DATA-OUT`, `${second}/DATA-IN`],
      ['0-10V', `${dim}/DIM`, `${third}/`],
    ]);
    expect(links.every((link) => link.lengthFt === PATCH_FT)).toBe(true);
    // A link drawn in engineering mode to a receiver wins over the derived one.
    value.project.controlLinks.push({ ...links[2]!, id: 'manual-1' });
    expect(deriveControlLinks(value, context.catalog).map((link) => link.to.ref)).toEqual([decoder, second]);
    expect(psu).toBe('PS-1');
  });

  it('feeds a converter’s control input from a DMX controller port', () => {
    const { value, cabinet, psu } = powered();
    const controller = addControl(value, context, cabinet, 'ctl:TEST-DMX-2U');
    const converter = addControl(value, context, cabinet, 'ctl:TEST-CONV-4');
    expect(controlInputOptions(value, context, converter).map((option) => option.value)).toEqual([
      `${controller}::U1`,
      `${controller}::U2`,
    ]);
    setControlInput(value, context, converter, `${controller}::U1`);
    expect(value.project.equipment.find((item) => item.id === converter)).toMatchObject({
      controlFrom: { ref: controller, port: 'U1' },
      controlLengthFt: PATCH_FT,
      dmx: { universe: 1, startAddress: 'auto' },
    });
    expect(() => setControlInput(value, context, controller, `${converter}::Out 1`)).toThrow();
    setDmx(value, converter, { universe: 2, startAddress: 9, terminatorPresent: true });
    expect(value.project.equipment.find((item) => item.id === converter)?.dmx).toEqual({
      universe: 2,
      startAddress: 9,
      terminatorPresent: true,
    });
    expect(() => setDmx(value, converter, { startAddress: 600 })).toThrow('1 to 512');
    expect(() => setDmx(value, psu, { universe: 1 })).toThrow('does not take a DMX address');
    valid(value);
  });
});

describe('control checks', () => {
  const limits = vdLimits({});
  const check = (value: Design) =>
    checkDesign({ design: value, products: catalog, lines: controlLines, wires, codeTables, limits });
  const codes = (value: Design) => check(value).messages.map((item) => `${item.severity}|${item.code}|${item.entityRef}`);

  it('runs the riser engine’s DMX checks on the derived chain and the designer’s control checks', () => {
    const { value, cabinet, decoder } = powered();
    const controller = addControl(value, context, cabinet, 'ctl:TEST-DMX-2U');
    const dmx = addZone(value, 'DMX512', 'Colour');
    setRunZone(value, context, ['a1linear:1:1', 'b1tape:1:1'], dmx);
    assignRuns(value, context, ['a1linear:1:1'], decoder, 'CH1');
    const psu = value.project.equipment.find((item) => item.tag === 'PS-1')!.id;
    assignRuns(value, context, ['b1tape:1:1'], psu, 'OUT1');
    let found = codes(value);
    expect(found).toContain(`warning|ZONE_NO_CONTROL|${dmx}`);
    expect(found).toContain(`warning|DMX_RUN_NO_DECODER|${dmx}`);
    expect(found).toContain(`info|CONTROL_UNUSED|${controller}`);
    // The decoder has an address but no DMX input yet.
    expect(found).toContain(`warning|DMX_TOPOLOGY|${decoder}`);

    setZoneControl(value, context, dmx, `${controller}::U1`);
    found = codes(value);
    expect(found).not.toContain(`warning|ZONE_NO_CONTROL|${dmx}`);
    expect(found).not.toContain(`info|CONTROL_UNUSED|${controller}`);
    expect(found).not.toContain(`warning|DMX_TOPOLOGY|${decoder}`);
    expect(found).toContain(`warning|DMX_NO_TERMINATOR|${decoder}`);
    setDmx(value, decoder, { terminatorPresent: true });
    expect(codes(value)).not.toContain(`warning|DMX_NO_TERMINATOR|${decoder}`);
    const result = check(value);
    expect(result.result.patch).toEqual([expect.objectContaining({ tag: 'DEC-1', universe: 1, startAddress: 1, footprint: 4 })]);
    expect(result.project.controlLinks.map((link) => link.id)).toEqual([`zone-${controller}-U1-1`]);
    expect(result.messages.filter((item) => item.code === 'PROTOCOL_MISMATCH')).toEqual([]);
  });

  it('reports overlapping DMX addresses and an unpowered control', () => {
    const { value, cabinet, decoder } = powered();
    const second = addControl(value, context, cabinet, 'ctl:TEST-DEC-4');
    setDmx(value, decoder, { startAddress: 1 });
    setDmx(value, second, { startAddress: 3 });
    const found = check(value).messages;
    expect(found.map((item) => item.code)).toContain('DMX_ADDRESS_OVERLAP');
    const unfed = found.find((item) => item.entityRef === second && item.code === 'UNRESOLVED_REF');
    expect(unfed).toMatchObject({ severity: 'warning', text: expect.stringContaining('DEC-2 has no power yet') });
  });

  it('counts devices on a 0-10V output against the port limit', () => {
    const { value, cabinet } = powered();
    const dim = addControl(value, context, cabinet, 'ctl:TEST-DIM-010');
    const soft = addZone(value, '0-10V');
    setRunZone(value, context, ['a1linear:1:1', 'a1linear:1:2'], soft);
    const a = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    const b = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    assignRuns(value, context, ['a1linear:1:1'], a, 'OUT1');
    assignRuns(value, context, ['a1linear:1:2'], b, 'OUT1');
    setZoneControl(value, context, soft, `${dim}::DIM`);
    expect(check(value).messages.some((item) => item.code === 'DEVICE_CAPACITY' && item.entityRef === dim)).toBe(true);
    expect(controlChecks(value, context.catalog).map((item) => item.code)).toEqual(['CONTROL_UNUSED']);
  });

  it('keeps line-voltage fixtures on circuits zoneable', () => {
    const { value, circuit } = powered();
    assignToCircuit(value, context, ['e1other:1:1'], circuit);
    const phase = addZone(value, 'phase-forward');
    expect(() => setRunZone(value, context, ['e1other:1:1'], phase)).not.toThrow();
    expect(run(value, 'e1other:1:1').zoneId).toBe(phase);
  });
});
