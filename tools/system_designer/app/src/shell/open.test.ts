import { describe, expect, it } from 'vitest';
import { DesignSchema } from '@ill/core-schemas/design';
import { openFixture } from './fixture';
import { ENGINE_VERSION, newDesign, openingChecks, OpenDesignSchema, severityCounts, startingDesign } from './open';

describe('opening a schedule', () => {
  it('parses the open_design payload', () => {
    const open = OpenDesignSchema.parse(openFixture());
    expect(open.lines.length).toBeGreaterThan(5);
    expect(() => OpenDesignSchema.parse({ ...openFixture(), catalog_hash: 'x' })).toThrow();
  });

  it('starts a valid design from the schedule with the Settings targets', () => {
    const open = openFixture({
      settings: { ...openFixture().settings, vd_target_class2_pct: 2.5, nec_edition: '2026' },
    });
    const { design, skipped } = newDesign(open);
    expect(() => DesignSchema.parse(design)).not.toThrow();
    expect(design).toMatchObject({
      engineVersion: ENGINE_VERSION,
      catalogSnapshotHash: open.catalog_hash,
      schedule: { name: 'SCH-TEST', version: 2 },
      zones: [],
    });
    expect(design.project.meta.name).toBe('Test house');
    expect(design.project.settings).toMatchObject({ vdTargetLowVoltagePct: 2.5, necEdition: '2026' });
    expect(design.runs.length).toBeGreaterThan(0);
    expect(new Set(design.runs.map((run) => run.spaceId))).toEqual(new Set(design.site.spaces.map((s) => s.id)));
    expect(skipped.map((item) => item.key)).toContain('f1other');
  });

  it('keeps a saved design as it is', () => {
    const fresh = newDesign(openFixture()).design;
    const meta = {
      name: 'SYSD-1',
      revision: 'B',
      status: 'Draft',
      modified: '2026-10-09 12:00:00',
      schedule_version: 2,
      is_current: true,
      terms_accepted: true,
    };
    const started = startingDesign(openFixture({ design: { ...fresh, engineVersion: 'saved' }, design_meta: meta }));
    expect(started.design.engineVersion).toBe('saved');
    expect(started.meta).toEqual(meta);
  });

  it('lists the lines that need attention once each', () => {
    const open = openFixture();
    const checks = openingChecks(open, newDesign(open).skipped);
    expect(severityCounts(checks)).toEqual({ error: 0, warning: 2, info: 1 });
    expect(checks.find((check) => check.id === 'data:f1other')).toMatchObject({
      title: 'Line F1 · Hall',
      detail: 'Enter the watts for this fixture',
    });
    expect(checks.filter((check) => check.id.endsWith('f1other'))).toHaveLength(1);
  });
});
