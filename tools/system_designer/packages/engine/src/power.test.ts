import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { expandRuns } from './expand';
import {
  addSupply,
  addZone,
  assignmentProblem,
  assignRuns,
  capacity,
  catalogMap,
  fitSorted,
  FROM_CONFIGURATOR,
  moveSupply,
  outputLoads,
  placeConfiguratorSupplies,
  powerSpecs,
  removeSupply,
  removeZone,
  reviewHints,
  runElectrical,
  setRunZone,
  setSupplyCircuit,
  unassignRuns,
  type PowerContext,
} from './power';
import { addCabinet, addCircuit, distanceDefaults, removeCircuit, setCabinetEnvironment, setCabinetFeed } from './site';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));
const opened = read('open-design/expected.json');
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const items = (read('catalog/payload.json').items as unknown[]).map((item) => CatalogItemSchema.parse(item));
const context: PowerContext = { catalog: catalogMap(items), lines, builds };
const defaults = distanceDefaults({});

function design(): Design {
  const { spaces, runs } = expandRuns(lines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  return { ...base, site: { ...base.site, spaces, cabinets: [] }, runs, zones: [] };
}

const kitchen = 'space-kitchen';
const valid = (value: Design) => expect(() => DesignSchema.parse(value)).not.toThrow();

describe('power board', () => {
  it('sizes supplies from the ERP usable load factor', () => {
    const psu60 = powerSpecs(context.catalog.get('drv:TEST-PSU-60'))!;
    expect(capacity(psu60, 80)).toMatchObject({
      factor: 0.8,
      usableW: 48,
      outputs: [{ usableW: 24 }, { usableW: 24 }],
    });
    expect(powerSpecs(context.catalog.get('drv:TEST-PSU-BAD'))).toBeNull();
  });

  it('reads what each run needs: tape voltage, product protocols, third-party data', () => {
    const value = design();
    const find = (key: string) => value.runs.find((run) => run.key === key)!;
    expect(runElectrical(find('a1linear:1:1'), context)).toEqual({ voltage: 24, lineVoltage: false, protocols: [] });
    expect(runElectrical(find('d1group:1:1'), context).protocols).toEqual(['0-10V']);
    expect(runElectrical(find('e1other:1:1'), context)).toEqual({
      voltage: 120,
      lineVoltage: true,
      protocols: ['phase-forward'],
    });
  });

  it('assigns runs to outputs and refuses with a reason', () => {
    const value = design();
    const cabinet = addCabinet(value, kitchen, defaults);
    const psu60 = addSupply(value, context, cabinet, 'drv:TEST-PSU-60');
    const psu96 = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    expect(value.project.equipment.map((item) => [item.tag, item.enclosure, item.category])).toEqual([
      ['PS-1', cabinet, 'psu'],
      ['PS-2', cabinet, 'psu'],
    ]);
    const problem = (keys: string[], id: string, port: string) => assignmentProblem(value, context, keys, id, port);

    expect(problem(['a1linear:1:1'], psu60, 'OUT1')).toBe('PS-1/OUT1 would carry 26.4 W of its 24 W usable');
    expect(problem(['e1other:1:1'], psu96, 'OUT1')).toBe(
      'E1-1.1 is line voltage; feed it from a panel circuit, not a supply',
    );
    expect(problem(['d1group:1:1'], psu60, 'OUT1')).toBe('D1-1.1 dims by 0-10V; PS-1 accepts phase-forward');
    expect(problem(['a1linear:1:1'], psu60, 'OUT9')).toBe('PS-1 has no output OUT9');

    assignRuns(value, context, ['a1linear:1:1', 'a1linear:1:2'], psu96, 'OUT1');
    expect(outputLoads(value, psu96).get('OUT1')).toBe(52.8);
    expect(problem(['a1linear:2:1'], psu96, 'OUT1')).toBe('PS-2/OUT1 would carry 79.2 W of its 76.8 W usable');
    // Re-assigning runs already on the output does not count them twice.
    expect(problem(['a1linear:1:1'], psu96, 'OUT1')).toBeNull();
    expect(() => assignRuns(value, context, ['a1linear:2:1', 'a1linear:2:2'], psu96, 'OUT1')).toThrow('105.6 W');
    expect(outputLoads(value, psu96).get('OUT1')).toBe(52.8);

    unassignRuns(value, ['a1linear:1:2']);
    expect(outputLoads(value, psu96).get('OUT1')).toBe(26.4);
    removeSupply(value, psu96);
    expect(value.runs.some((run) => run.assignment)).toBe(false);
    valid(value);
  });

  it('keeps zones apart on outputs and checks the zone method against the supply', () => {
    const value = design();
    const cabinet = addCabinet(value, kitchen, defaults);
    const psu = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
    const dim = addZone(value, '0-10V', 'Kitchen dim');
    const phase = addZone(value, 'phase-forward');
    expect(value.zones.map((zone) => [zone.id, zone.name, zone.method])).toEqual([
      ['zone-1', 'Kitchen dim', '0-10V'],
      ['zone-2', 'Zone 2', 'phase-forward'],
    ]);
    setRunZone(value, context, ['a1linear:1:1'], dim);
    assignRuns(value, context, ['a1linear:1:1'], psu, 'OUT1');
    expect(assignmentProblem(value, context, ['a1linear:1:2'], psu, 'OUT1')).toBe(
      'PS-1/OUT1 would feed more than one zone; give each zone its own output',
    );
    expect(() => setRunZone(value, context, ['a1linear:1:1'], phase)).toThrow(
      'Zone 2 dims by phase-forward; PS-1 does not accept it',
    );
    expect(value.runs.find((run) => run.key === 'a1linear:1:1')?.zoneId).toBe(dim);
    expect(reviewHints(value)).toEqual([]);
    setRunZone(value, context, ['b1tape:1:1'], phase);
    expect(reviewHints(value)).toEqual(['Phase-cut dimming']);
    removeZone(value, phase);
    expect(value.runs.some((run) => run.zoneId === phase)).toBe(false);
    valid(value);
  });

  it('places the configurator supplies in a cabinet per space', () => {
    const value = design();
    const added = placeConfiguratorSupplies(value, context, (spaceId) => addCabinet(value, spaceId, defaults));
    // A1 copies 1 and 2 (PSU-96), the sheet (PSU-96) and the group (PSU-60); outputs the supply lacks stay open.
    expect(added).toBe(4);
    expect(value.project.equipment.every((item) => item.notes === FROM_CONFIGURATOR)).toBe(true);
    expect(value.site.cabinets.map((cabinet) => cabinet.spaceId)).toEqual(['space-kitchen', 'space-living-room']);
    expect(value.runs.find((run) => run.key === 'd1group:1:2')?.assignment).toEqual({
      equipmentId: 'PS-4',
      port: 'OUT2',
    });
    expect(value.runs.find((run) => run.key === 'a1linear:1:2')?.assignment).toBeUndefined();
    expect(placeConfiguratorSupplies(value, context, () => 'unused')).toBe(0);
    valid(value);
  });

  it('sorts eligible supplies by fit, then rank, never by anything else', () => {
    const candidates = [
      { catalogId: 'drv:TEST-PSU-96', rank: 2 },
      { catalogId: 'drv:TEST-PSU-60', rank: 1 },
      { catalogId: 'drv:TEST-PSU-BAD' },
    ];
    expect(fitSorted(candidates, context, 20, 20, 80).map((item) => [item.catalogId, item.fits])).toEqual([
      ['drv:TEST-PSU-60', true],
      ['drv:TEST-PSU-96', true],
    ]);
    expect(fitSorted(candidates, context, 60, 26.4, 80).map((item) => [item.catalogId, item.count])).toEqual([
      ['drv:TEST-PSU-96', 1],
      ['drv:TEST-PSU-60', Infinity],
    ]);
    expect(fitSorted(candidates, context, 160, 20, 80).map((item) => [item.catalogId, item.count])).toEqual([
      ['drv:TEST-PSU-96', 3],
      ['drv:TEST-PSU-60', 4],
    ]);
  });

  it('keeps supplies with their cabinet: environment, circuit, feed and moves', () => {
    const value = design();
    const a = addCabinet(value, kitchen, defaults);
    const b = addCabinet(value, 'space-hall', defaults);
    const circuit = addCircuit(value);
    const psu = addSupply(value, context, a, 'drv:TEST-PSU-96');
    expect(value.project.equipment[0]?.fedFrom).toEqual({ ref: 'unassigned' });
    setSupplyCircuit(value, psu, circuit);
    expect(value.project.equipment[0]?.fedFrom).toEqual({ ref: circuit });
    setCabinetEnvironment(value, a, 'damp');
    setCabinetFeed(value, a, 33, false);
    expect(value.project.equipment[0]).toMatchObject({ env: 'wet', feedLengthFt: 33 });
    removeCircuit(value, circuit);
    expect(value.project.equipment[0]?.fedFrom).toEqual({ ref: 'unassigned' });
    moveSupply(value, psu, b);
    expect(value.project.equipment[0]).toMatchObject({ enclosure: b, env: 'dry-concealed' });
    expect(() => addSupply(value, context, a, 'tape:TEST-TAPE-24:4.4:50')).toThrow('Choose a supply');
    valid(value);
  });
});
