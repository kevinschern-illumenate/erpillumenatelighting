import { produce, type Draft as Mutable } from 'immer';
import { describe, expect, it } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import type { Design } from '@ill/core-schemas/design';
import { addCabinet, addCircuit, distanceDefaults } from '@ill/engine/site';
import { parseCatalog } from '../design/catalog';
import { openFixture } from '../shell/fixture';
import { newDesign } from '../shell/open';
import { addRow, editCell, editSetting, gridRows, readCell, removeRows } from './grids';

const catalog = parseCatalog('d'.repeat(64), catalogPayload).items;

function base(): Design {
  const design = newDesign(openFixture()).design;
  const cabinet = addCabinet(design, 'space-kitchen', distanceDefaults({}));
  const source = addCircuit(design);
  design.site.cabinets.find((item) => item.id === cabinet)!.sourceId = source;
  design.project.equipment.push({
    id: 'PS-1',
    tag: 'PS-1',
    catalogId: 'drv:TEST-PSU-96',
    category: 'psu',
    qty: 1,
    location: 'Kitchen cabinet',
    enclosure: cabinet,
    fedFrom: { ref: source },
    feedLengthFt: 10,
    env: 'dry-concealed',
  });
  design.runs.find((run) => run.key === 'a1linear:1:1')!.assignment = { equipmentId: 'PS-1', port: 'OUT1' };
  return design;
}
const edit = (design: Design, recipe: (draft: Mutable<Design>) => void) => produce(design, recipe);

describe('engineering grids', () => {
  it('edits a cell through the project schema', () => {
    const design = edit(base(), (draft) => {
      editCell(draft, 'equipment', 'PS-1', 'feedLengthFt', '25', catalog);
      editCell(draft, 'equipment', 'PS-1', 'universe', '3', catalog);
      editCell(draft, 'equipment', 'PS-1', 'notes', '  Behind the pantry door ', catalog);
      editCell(draft, 'sources', 'src-1', 'breakerA', 15, catalog);
    });
    const supply = design.project.equipment[0]!;
    expect([supply.feedLengthFt, supply.dmx, supply.notes]).toEqual([
      25,
      { universe: 3, startAddress: 'auto' },
      'Behind the pantry door',
    ]);
    expect(design.project.sources[0]!.breakerA).toBe(15);
    expect(readCell(supply, 'fedFrom')).toBe('src-1');
    expect(readCell(supply, 'universe')).toBe(3);
  });

  it('refuses values the riser would reject, and leaves the design as it was', () => {
    const design = base();
    const attempt = (field: string, value: unknown, key: 'equipment' | 'sources' | 'loads' = 'equipment') => {
      try {
        edit(design, (draft) => editCell(draft, key, key === 'sources' ? 'src-1' : 'PS-1', field, value, catalog));
        return null;
      } catch (e) {
        return (e as Error).message;
      }
    };
    expect(attempt('feedLengthFt', 'far')).toBe('Enter a number for feed length (ft).');
    expect(attempt('feedLengthFt', '-3')).toMatch(/^feed length \(ft\): /);
    expect(attempt('catalogId', 'tape:TEST-TAPE-24:4.4:50')).toBe('Choose equipment, not tape or a fixture.');
    expect(attempt('catalogId', 'nope')).toBe('Choose a product from the ilLumenate catalog.');
    expect(attempt('tag', 'CKT-1')).toBe('CKT-1 is already used.');
    expect(attempt('voltage', '110', 'sources')).toMatch(/^voltage: /);
    expect(attempt('qty', '2', 'loads')).toBe('Loads come from the runs. Change them on the Runs step.');
    expect(design.project.equipment[0]!.feedLengthFt).toBe(10);
  });

  it('shows the loads the runs produce, read-only', () => {
    const design = base();
    const loads = gridRows(design, 'loads');
    expect(loads.length).toBe(design.runs.filter((run) => run.assignment).length);
    expect(loads[0]).toMatchObject({ fedFrom: { ref: 'PS-1', port: 'OUT1' } });
    expect(() => edit(design, (draft) => addRow(draft, 'loads', catalog))).toThrow('Change them on the Runs step');
  });

  it('adds rows and removes them with the guided steps’ cleanup', () => {
    let design = edit(base(), (draft) => {
      addRow(draft, 'equipment', catalog);
      addRow(draft, 'controlLinks', catalog);
    });
    expect(design.project.equipment.map((item) => item.tag)).toEqual(['PS-1', 'PS-2']);
    expect(design.project.controlLinks[0]).toMatchObject({ id: 'CL-1', from: { ref: 'PS-1' }, to: { ref: 'PS-2' } });
    design = edit(design, (draft) => removeRows(draft, 'equipment', ['PS-1']));
    expect(design.project.equipment.map((item) => item.id)).toEqual(['PS-2']);
    expect(design.project.controlLinks).toEqual([]);
    expect(design.runs.some((run) => run.assignment?.equipmentId === 'PS-1')).toBe(false);
    design = edit(design, (draft) => removeRows(draft, 'sources', ['src-1']));
    expect(design.project.sources).toEqual([]);
    expect(design.site.cabinets[0]!.sourceId).toBeUndefined();
  });

  it('lets dealers change presentation settings and keeps the safety margins for staff', () => {
    let design = edit(base(), (draft) => {
      editSetting(draft, 'necEdition', '2026', false);
      editSetting(draft, 'sheetFlow', 'TB', false);
      editSetting(draft, 'showSchedules', false, false);
    });
    expect([design.project.settings.necEdition, design.project.settings.sheet.flow]).toEqual(['2026', 'TB']);
    expect(design.project.settings.showSchedules).toBe(false);
    expect(() => edit(design, (draft) => editSetting(draft, 'psuDeratePct', '95', false))).toThrow(
      'Supply operating target (%) is set by ilLumenate.',
    );
    design = edit(design, (draft) => editSetting(draft, 'psuDeratePct', '90', true));
    expect(design.project.settings.psuDeratePct).toBe(90);
    expect(() => edit(design, (draft) => editSetting(draft, 'psuDeratePct', '120', true))).toThrow(
      /^Supply operating target \(%\): /,
    );
    design = edit(design, (draft) => editSetting(draft, 'terminationTempC', '60', true));
    expect(design.project.settings.terminationTempC).toBe(60);
  });
});
