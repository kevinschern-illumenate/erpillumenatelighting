import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { RunSchema } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema } from '@ill/core-schemas/open-design';
import { expandRuns, spaceIdFor } from './expand';

// Built by system_design/expansion.py from fixtures/open-design/erp-records.json (WP-2.3 parity).
const fixture = JSON.parse(
  readFileSync(
    new URL('../../core-schemas/fixtures/open-design/expected.json', import.meta.url),
    'utf8',
  ),
);
const lines = LineSchema.array().parse(fixture.lines);
const builds = BuildsSchema.parse(fixture.builds);
const options = { groupThresholdQty: 6, defaultHomeRunFt: 10 };

describe('expandRuns', () => {
  const { runs, spaces, skipped } = expandRuns(lines, builds, options);
  const byLine = (key: string) => runs.filter((run) => run.lineKey === key);

  it('produces valid, unique run keys', () => {
    for (const run of runs) RunSchema.parse(run);
    expect(new Set(runs.map((run) => run.key)).size).toBe(runs.length);
  });

  it('repeats a linear build per copy with its tape catalog id', () => {
    expect(byLine('a1linear').map((run) => run.key)).toEqual([
      'a1linear:1:1',
      'a1linear:1:2',
      'a1linear:2:1',
      'a1linear:2:2',
    ]);
    const [first] = byLine('a1linear');
    expect(first).toMatchObject({
      catalogId: 'tape:TEST-TAPE-24:4.4:50',
      lengthFt: 6,
      watts: 26.4,
      env: 'dry-concealed',
      source: { kind: 'configured', doctype: 'ilL-Configured-Fixture', configHash: 'hash-linear' },
    });
  });

  it('keeps jumper-connected tape as one run', () => {
    expect(byLine('b1tape').map((run) => [run.lengthFt, run.watts, run.env])).toEqual([
      [4.9213, 21.6, 'wet'],
      [9.8425, 43.3, 'wet'],
    ]);
  });

  it('gives sheets and groups their runs', () => {
    expect(byLine('c1sheet').map((run) => [run.runIndex, run.lengthFt, run.watts])).toEqual([
      [1, undefined, 50],
      [2, undefined, 40],
    ]);
    expect(byLine('d1group').map((run) => run.watts)).toEqual([13.2, 26.4]);
    // An unknown ERP environment falls back to the space's environment.
    expect(byLine('d1group')[0]?.env).toBe('dry-concealed');
  });

  it('turns dealer-entered third-party lines into runs and groups large quantities', () => {
    const other = byLine('e1other');
    expect(other).toHaveLength(6);
    expect(other[0]).toMatchObject({
      catalogId: 'tp:e1other',
      source: { kind: 'third-party' },
      watts: 12,
      feedMethod: 'end',
      groupId: 'grp-e1other',
    });
    expect(byLine('a1linear')[0]?.groupId).toBeUndefined();
    expect(skipped).toEqual([{ key: 'f1other', reason: 'Enter the watts for this fixture' }]);
  });

  it('falls back to line id and position when line_key is missing', () => {
    expect(byLine('G1-7').map((run) => [run.key, run.feedMethod, run.spaceId])).toEqual([
      ['G1-7:1:1', 'center', 'unassigned'],
    ]);
  });

  it('ignores accessory, unconfigured and write-back lines and builds spaces from locations', () => {
    expect(runs.some((run) => ['h1acc', 'i1new', 'j1wire'].includes(run.lineKey))).toBe(false);
    expect(spaces.map((space) => space.id)).toEqual([
      'space-kitchen',
      'space-living-room',
      'space-hall',
      'unassigned',
    ]);
    expect(spaceIdFor('  ')).toBe('unassigned');
  });
});
