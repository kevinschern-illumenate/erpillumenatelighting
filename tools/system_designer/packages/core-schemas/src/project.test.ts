import { describe, expect, it } from 'vitest';
import {
  ControlLinkSchema,
  EquipmentSchema,
  LoadSchema,
  ProjectSchema,
  ProjectSettingsSchema,
  SourceSchema,
} from './project';
import { createDraft, migrateDraft } from './workspace';
import { createDraft as createLegacy } from './legacy-workspace';

const source = {
  id: 'circuit1',
  tag: 'LP-1/12',
  panel: 'LP-1',
  circuit: '12',
  voltage: 120,
  phase: '1PH',
  breakerA: 20,
  poles: 1,
};
const load = {
  id: 'load1',
  typeTag: 'T1',
  zone: 'Lobby',
  catalogId: 'tape-tw',
  lengthFt: 20,
  fedFrom: { ref: 'PS-1', port: 'OUT1' },
  homeRunLengthFt: 30,
  feedMethod: 'end',
  env: 'plenum',
};
const equipment = {
  id: 'psu1',
  tag: 'PS-1',
  catalogId: 'psu-24v-96w',
  category: 'psu',
  qty: 1,
  location: 'Mech 101',
  fedFrom: { ref: 'LP-1/12' },
  feedLengthFt: 50,
  env: 'raceway',
};

describe('full project schema', () => {
  it('loads all requested defaults and keeps physical stored lengths in feet', () => {
    const s = ProjectSettingsSchema.parse({});
    expect(s).toMatchObject({
      necEdition: '2023',
      terminationTempC: 75,
      vdTargetLineVoltagePct: 3,
      vdTargetLowVoltagePct: 3,
      vdTargetLandscapePct: 5,
      vdMethod: 'lumped-at-end',
      acVdMethod: 'dc-resistance',
      psuDeratePct: 80,
      continuousLoadFactor: 1.25,
      breakerLoadLimitPct: 80,
      tapeLengthMarginPct: 0,
      minAwgLineVoltage: '12',
      dmxMaxUnitLoads: 32,
      dmxMaxLengthFt: 1000,
      spiMaxDataFt: 15,
      units: 'ft',
      wireWastePct: 10,
    });
    expect(ProjectSettingsSchema.safeParse({ psuDeratePct: 101 }).success).toBe(false);
    expect(ProjectSettingsSchema.safeParse({ continuousLoadFactor: 0.8 }).success).toBe(false);
    expect(ProjectSettingsSchema.safeParse({ fake: true }).success).toBe(false);
  });
  it('validates all entity shapes without discarding unresolved references needed by QA', () => {
    expect(SourceSchema.safeParse(source).success).toBe(true);
    expect(EquipmentSchema.safeParse(equipment).success).toBe(true);
    expect(LoadSchema.safeParse(load).success).toBe(true);
    const p = ProjectSchema.parse({
      ...createDraft(),
      sources: [source],
      equipment: [equipment],
      loads: [load],
    });
    expect(p.loads[0]!.fedFrom.ref).toBe('PS-1');
    expect(
      ControlLinkSchema.safeParse({
        id: 'link1',
        from: { ref: 'not-yet-entered' },
        to: { ref: 'DEC-1' },
        protocol: 'DMX512',
        lengthFt: 0,
        env: 'dry-concealed',
        universe: 1,
      }).success,
    ).toBe(true);
  });
  it('requires quantities, explicit feed count and valid paired control fields', () => {
    expect(LoadSchema.safeParse({ ...load, qty: 2 }).success).toBe(false);
    expect(LoadSchema.safeParse({ ...load, lengthFt: undefined }).success).toBe(false);
    expect(LoadSchema.safeParse({ ...load, feedMethod: 'multi-feed' }).success).toBe(false);
    expect(LoadSchema.safeParse({ ...load, feedMethod: 'multi-feed', feeds: 2 }).success).toBe(
      true,
    );
    expect(
      EquipmentSchema.safeParse({ ...equipment, controlFrom: { ref: 'CTRL-1' } }).success,
    ).toBe(false);
    expect(EquipmentSchema.safeParse({ ...equipment, controlLengthFt: 20 }).success).toBe(false);
  });
  it('rejects ID/tag collisions but permits repeated fixture type tags', () => {
    const p = createDraft();
    expect(
      ProjectSchema.safeParse({
        ...p,
        sources: [source],
        equipment: [{ ...equipment, id: 'LP-1/12' }],
      }).success,
    ).toBe(false);
    expect(ProjectSchema.safeParse({ ...p, sources: [source, source] }).success).toBe(false);
    expect(ProjectSchema.safeParse({ ...p, loads: [load, { ...load, id: 'load2' }] }).success).toBe(
      true,
    );
    expect(ProjectSchema.safeParse({ ...p, wireTagMap: { a: 'W-01', b: 'W-01' } }).success).toBe(
      false,
    );
  });
  it('migrates legacy metadata and customized defaults without mutating the original', () => {
    const legacy = createLegacy();
    legacy.meta.name = 'Existing project';
    legacy.defaults = { sheetSize: 'ANSI_B', flow: 'TB', psuDeratePct: 75 };
    legacy.scratchNote = 'Preserve me';
    const before = structuredClone(legacy);
    const project = migrateDraft(legacy);
    expect(project.schemaVersion).toBe(1);
    expect(project.id).toBe(legacy.id);
    expect(project.meta).toEqual(legacy.meta);
    expect(project.settings.sheet).toEqual({ size: 'ANSI_B', flow: 'TB' });
    expect(project.settings.psuDeratePct).toBe(75);
    expect(project.scratchNote).toBe('Preserve me');
    expect(project.generalNotes).toHaveLength(12);
    expect(legacy).toEqual(before);
  });
});
