import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { expandRuns } from './expand';
import { labelRuns } from './labels';
import { runLabel, runRows } from './runs';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const opened = JSON.parse(readFileSync(new URL('open-design/expected.json', fixtures), 'utf8'));
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const options = { groupThresholdQty: 99, defaultHomeRunFt: 10 };
const labels = (runs: { key: string; label?: string }[]) => Object.fromEntries(runs.map((run) => [run.key, run.label]));

describe('run labels', () => {
  it('use the schedule part number and count every run and copy of it', () => {
    const { runs } = expandRuns(lines, builds, options);
    expect(labels(runs)).toMatchObject({
      'a1linear:1:1': 'TEST-FX-LINEAR-30K-12FT.1',
      'a1linear:1:2': 'TEST-FX-LINEAR-30K-12FT.2',
      'a1linear:2:1': 'TEST-FX-LINEAR-30K-12FT.3',
      'a1linear:2:2': 'TEST-FX-LINEAR-30K-12FT.4',
      'b1tape:1:2': 'TEST-TN-24-30K-WET.2',
      // A multi-run group's runs carry their own members' part numbers, never the ILL-GRP code.
      'd1group:1:1': 'TEST-TN-24-30K-3FT.1',
      'd1group:1:2': 'TEST-TN-24-30K-6FT.1',
      'e1other:6:1': 'DL-4.6',
    });
    expect(new Set(runs.map(runLabel)).size).toBe(runs.length);
  });

  it('keep counting when two lines share a part number', () => {
    const twin = { ...lines.find((line) => line.key === 'a1linear')!, key: 'a2linear', lineId: 'A2', idx: 99, qty: 1 };
    const { runs } = expandRuns([...lines, twin], builds, options);
    expect(labels(runs)['a2linear:1:2']).toBe('TEST-FX-LINEAR-30K-12FT.6');
  });

  it('fall back to line, copy and run without a part number', () => {
    const bare: Builds = structuredClone(builds);
    for (const build of Object.values(bare['ilL-Configured-Group']!))
      build.runs = build.runs.map((run) => ({ ...run, partNumber: null }));
    const { runs } = expandRuns(lines, bare, options);
    const member = runs.find((run) => run.key === 'd1group:1:2')!;
    expect(member.label).toBeUndefined();
    expect(runLabel(member)).toBe('D1-1.2');
  });

  it('refresh a saved design without touching runs that already match', () => {
    const { runs } = expandRuns(lines, builds, options);
    const saved = runs.map((run) => {
      const copy = { ...run };
      delete copy.label;
      return copy;
    });
    const fresh = labelRuns(saved, lines, builds);
    expect(labels(fresh)).toEqual(labels(runs));
    const again = labelRuns(fresh, lines, builds);
    expect(again.every((run, index) => run === fresh[index])).toBe(true);
  });

  it('fold a group of one part number into a short span', () => {
    const { runs } = expandRuns(lines, builds, options);
    const hall = runs.filter((run) => run.lineKey === 'e1other').map((run) => ({ ...run, groupId: 'grp-e1' }));
    expect(runRows(hall)[0]!.label).toBe('DL-4.1–6 (6 runs)');
    const mixed = runs.filter((run) => run.lineKey === 'd1group').map((run) => ({ ...run, groupId: 'grp-d1' }));
    expect(runRows(mixed)[0]!.label).toBe('TEST-TN-24-30K-3FT.1 … TEST-TN-24-30K-6FT.1 (2 runs)');
  });
});
