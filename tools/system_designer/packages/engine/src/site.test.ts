import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { expandRuns } from './expand';
import {
  addCabinet,
  addCircuit,
  distanceDefaults,
  mergeSpaces,
  pickLength,
  removeCabinet,
  removeCircuit,
  renameSpace,
  setCabinetEnvironment,
  setCabinetFeed,
  setHomeRuns,
  setRunEnvironment,
  setSpaceEnvironment,
  updateCabinet,
  updateCircuit,
} from './site';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));
const opened = read('open-design/expected.json');
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const defaults = distanceDefaults({ default_distance_adjacent_ft: 30 });

function design(): Design {
  const { spaces, runs } = expandRuns(lines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  return { ...base, site: { ...base.site, spaces, cabinets: [] }, runs };
}

const kitchen = 'space-kitchen';
const valid = (value: Design) => expect(() => DesignSchema.parse(value)).not.toThrow();

describe('site model', () => {
  it('uses Settings distances with the plan defaults as fallback', () => {
    expect(defaults).toEqual({ sameSpaceFt: 10, adjacentFt: 30, otherLevelFt: 40 });
    expect(pickLength('adjacent', defaults)).toBe(30);
    expect(distanceDefaults({ default_distance_same_space_ft: -1 }).sameSpaceFt).toBe(10);
  });

  it('cascades a space environment to the cabinets and runs that follow it', () => {
    const value = design();
    const cabinet = addCabinet(value, kitchen, defaults);
    const own = value.runs.find((run) => run.spaceId === kitchen)!;
    setRunEnvironment(value, [own.key], 'plenum');
    // Runs whose build sets another environment (a wet-rated product) keep it.
    const followers = value.runs.filter((run) => run.spaceId === kitchen && run.env === 'dry-concealed');
    const fixed = value.runs.filter((run) => run.spaceId === kitchen && run.env !== 'dry-concealed');
    setSpaceEnvironment(value, kitchen, 'damp');
    const space = value.site.spaces.find((item) => item.id === kitchen)!;
    expect(space).toMatchObject({ env: 'wet', envChoice: 'damp' });
    expect(value.site.cabinets.find((item) => item.id === cabinet)).toMatchObject({
      env: 'wet',
      envChoice: 'damp',
      locationRating: 'Damp',
    });
    expect(followers.length).toBeGreaterThan(0);
    expect(followers.every((run) => run.envChoice === 'damp' && run.env === 'wet')).toBe(true);
    expect(fixed.map((run) => run.key)).toContain(own.key);
    expect(fixed.every((run) => run.envChoice !== 'damp')).toBe(true);
    expect(value.runs.find((run) => run.key === own.key)).toMatchObject({ env: 'plenum', envChoice: 'plenum' });
    setCabinetEnvironment(value, cabinet, 'in-wall');
    expect(value.site.cabinets[0]).toMatchObject({ env: 'dry-concealed', envChoice: 'in-wall', locationRating: 'Dry' });
    valid(value);
  });

  it('renames and merges spaces, moving runs and cabinets', () => {
    const value = design();
    const [first, second] = value.site.spaces;
    renameSpace(value, first!.id, '  Main kitchen ', 'Level 1');
    expect(value.site.spaces[0]).toMatchObject({ name: 'Main kitchen', level: 'Level 1' });
    expect(() => renameSpace(value, first!.id, ' ')).toThrow('Enter a space name');
    const cabinet = addCabinet(value, second!.id, defaults);
    mergeSpaces(value, second!.id, first!.id);
    expect(value.site.spaces.map((item) => item.id)).not.toContain(second!.id);
    expect(value.runs.some((run) => run.spaceId === second!.id)).toBe(false);
    expect(value.site.cabinets.find((item) => item.id === cabinet)?.spaceId).toBe(first!.id);
    expect(() => mergeSpaces(value, first!.id, first!.id)).toThrow();
    valid(value);
  });

  it('numbers cabinets, wires them to circuits and refuses to drop occupied ones', () => {
    const value = design();
    const a = addCabinet(value, kitchen, defaults);
    const b = addCabinet(value, kitchen, defaults);
    expect(value.site.cabinets.map((item) => item.tag)).toEqual(['C-1', 'C-2']);
    expect(() => updateCabinet(value, b, { tag: 'C-1' })).toThrow('Another cabinet is already C-1');
    const circuit = addCircuit(value);
    updateCircuit(value, circuit, { panel: 'LP-2', breakerA: 15 });
    updateCabinet(value, a, { sourceId: circuit, accessNote: 'Above pantry' });
    expect(value.site.cabinets[0]).toMatchObject({ sourceId: circuit, accessNote: 'Above pantry' });
    expect(value.project.sources[0]).toMatchObject({ tag: 'CKT-1', panel: 'LP-2', breakerA: 15, voltage: 120 });
    expect(() => updateCabinet(value, a, { sourceId: 'nope' })).toThrow('Unknown circuit');
    updateCabinet(value, a, { sourceId: undefined });
    expect(value.site.cabinets[0]).not.toHaveProperty('sourceId');
    updateCabinet(value, a, { sourceId: circuit });
    removeCircuit(value, circuit);
    expect(value.site.cabinets[0]).not.toHaveProperty('sourceId');

    value.project.equipment.push({
      id: 'PS-1',
      tag: 'PS-1',
      catalogId: 'drv:TEST',
      category: 'psu',
      qty: 1,
      location: 'Kitchen',
      enclosure: a,
      fedFrom: { ref: 'CKT-9' },
      feedLengthFt: 0,
      env: 'dry-concealed',
    });
    expect(() => removeCabinet(value, a)).toThrow('Move the supply out of this cabinet first');
    removeCabinet(value, b);
    expect(value.site.cabinets.map((item) => item.id)).toEqual([a]);
  });

  it('records distance provenance: quick picks are estimates, typed values are entered', () => {
    const value = design();
    const keys = value.runs.slice(0, 2).map((run) => run.key);
    setHomeRuns(value, keys, pickLength('other-level', defaults), true);
    expect(value.runs.slice(0, 2).map((run) => [run.homeRunLengthFt, run.homeRunProvenance])).toEqual([
      [40, 'estimate'],
      [40, 'estimate'],
    ]);
    setHomeRuns(value, keys.slice(0, 1), 27.5, false);
    expect(value.runs[0]).toMatchObject({ homeRunLengthFt: 27.5, homeRunProvenance: 'entered' });
    expect(() => setHomeRuns(value, keys, -1, false)).toThrow();
    const cabinet = addCabinet(value, kitchen, defaults);
    setCabinetFeed(value, cabinet, 55, false);
    expect(value.site.cabinets[0]).toMatchObject({ feedLengthFt: 55, feedLengthProvenance: 'entered' });
    valid(value);
  });
});
