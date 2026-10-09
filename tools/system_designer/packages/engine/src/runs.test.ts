import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { expandRuns } from './expand';
import { feedPositions, groupRuns, moveRuns, runChecks, runLabel, runRows, runType, splitGroup } from './runs';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));
const opened = read('open-design/expected.json');
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;

function design(): Design {
  const { spaces, runs } = expandRuns(lines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  return { ...base, site: { ...base.site, spaces, cabinets: [] }, runs };
}

const find = (value: Design, key: string) => value.runs.find((run) => run.key === key)!;

describe('run editor', () => {
  it('labels runs and names their product family', () => {
    const value = design();
    expect(runLabel(find(value, 'a1linear:2:1'))).toBe('A1-2.1');
    expect(runType(find(value, 'a1linear:2:1'), builds)).toBe('Linear fixture');
    expect(runType(find(value, 'c1sheet:1:1'), builds)).toBe('LED sheet');
    expect(runType(find(value, 'e1other:1:1'), builds)).toBe('Third-party');
  });

  it('places feeds along the strip by feed method', () => {
    expect(feedPositions({ feedMethod: 'end' })).toEqual([0]);
    expect(feedPositions({ feedMethod: 'double-end' })).toEqual([0, 1]);
    expect(feedPositions({ feedMethod: 'center' })).toEqual([0.5]);
    expect(feedPositions({ feedMethod: 'multi-feed', feeds: 3 })).toEqual([0, 0.5, 1]);
  });

  it('flags runs past the build maximum, hints near it, and checks feed counts', () => {
    const value = design();
    expect(runChecks(value, builds)).toEqual([]);
    find(value, 'b1tape:1:2').lengthFt = 20; // max 16 ft
    find(value, 'b1tape:1:1').lengthFt = 15;
    const run = find(value, 'a1linear:1:1');
    run.feedMethod = 'multi-feed';
    const checks = runChecks(value, builds);
    expect(checks.map((check) => [check.code, check.severity, check.entityRef])).toEqual([
      ['INVALID_SPEC', 'warning', 'a1linear:1:1'],
      ['MAX_LENGTH_HINT', 'info', 'b1tape:1:1'],
      ['TAPE_RUN_TOO_LONG', 'error', 'b1tape:1:2'],
    ]);
    expect(checks[2]?.text).toBe(
      'B1-1.2 is 20 ft; this build allows 16 ft from its feed. Feed it from both ends or split it in the configurator.',
    );
    run.feedMethod = 'double-end';
    run.feeds = 3;
    expect(runChecks(value, builds)[0]?.text).toBe('A1-1.1 is fed from both ends but lists 3.');
  });

  it('folds groups into one row, splits and regroups them', () => {
    const value = design();
    const rows = runRows(value.runs);
    const hall = rows.find((row) => row.groupId === 'grp-e1other')!;
    expect(hall.runs).toHaveLength(6);
    expect(hall.label).toBe('E1-1.1 … E1-6.1 (6 runs)');
    expect(rows.filter((row) => !row.groupId)).toHaveLength(value.runs.length - 6);

    splitGroup(value, 'grp-e1other');
    expect(value.runs.some((run) => run.groupId)).toBe(false);
    const keys = ['e1other:1:1', 'e1other:2:1', 'e1other:3:1'];
    expect(groupRuns(value, keys)).toBe('grp-e1other');
    expect(groupRuns(value, ['e1other:4:1', 'e1other:5:1'])).toBe('grp-e1other-2');
    expect(() => groupRuns(value, ['e1other:6:1'])).toThrow('Select at least two runs to group');
    expect(() => groupRuns(value, ['e1other:6:1', 'a1linear:1:1'])).toThrow('Only runs of one schedule line');
    expect(runRows(value.runs).filter((row) => row.groupId)).toHaveLength(2);
    expect(() => DesignSchema.parse(value)).not.toThrow();
  });

  it('refuses to group runs on different supplies and moves runs between spaces', () => {
    const value = design();
    splitGroup(value, 'grp-e1other');
    find(value, 'e1other:1:1').assignment = { equipmentId: 'PS-1', port: '1' };
    expect(() => groupRuns(value, ['e1other:1:1', 'e1other:2:1'])).toThrow('Unassign the runs');
    moveRuns(value, ['e1other:1:1'], 'space-kitchen');
    expect(find(value, 'e1other:1:1').spaceId).toBe('space-kitchen');
    expect(() => moveRuns(value, ['e1other:1:1'], 'nowhere')).toThrow('Unknown space');
  });
});
