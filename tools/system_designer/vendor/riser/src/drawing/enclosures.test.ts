import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { EquipmentSchema } from '../schemas/project';
import { buildDrawing } from './build';
import { flattenSheet, type Sheet } from './model';
import { textBounds } from './text';
import {
  ENCLOSURE_WIRE_CLEARANCE,
  intersects,
  parallelConflict,
  routeOrthogonal,
  segmentBlocked,
  segmentsOf,
  type Bounds,
} from './layout/router';

const contains = (outer: Bounds, inner: Bounds) =>
  inner.x >= outer.x &&
  inner.y >= outer.y &&
  inner.x + inner.width <= outer.x + outer.width &&
  inner.y + inner.height <= outer.y + outer.height;

function checkClearance(sheet: Sheet) {
  const borders = sheet.prims.flatMap((p) =>
    p.kind === 'rect' && p.layer === 'E-ANNO-ENCL'
      ? segmentsOf([
          { x: p.x, y: p.y },
          { x: p.x + p.width, y: p.y },
          { x: p.x + p.width, y: p.y + p.height },
          { x: p.x, y: p.y + p.height },
          { x: p.x, y: p.y },
        ])
      : [],
  );
  const headings = flattenSheet(sheet).filter(
    (p) => p.kind === 'text' && p.layer === 'E-ANNO-ENCL',
  );
  for (const c of sheet.connections ?? [])
    for (const segment of segmentsOf(c.points)) {
      for (const border of borders)
        expect(
          parallelConflict(segment, border, ENCLOSURE_WIRE_CLEARANCE),
          `${sheet.number}: ${c.runId} / enclosure edge`,
        ).toBe(false);
      for (const label of headings)
        if (label.kind === 'text')
          expect(segmentBlocked(segment.a, segment.b, [textBounds(label)])).toBe(false);
    }
}

describe('enclosure-aware drafting', () => {
  it('repositions mixed-circuit components and controls inside one outline per enclosure', async () => {
    const library = seedLibrary();
    for (const flow of ['LR', 'TB'] as const)
      for (const showSchedules of [true, false]) {
        const project = demoProject();
        project.settings.sheet = { size: 'ARCH_D', flow };
        project.settings.showSchedules = showSchedules;
        project.equipment.forEach((e) => (e.enclosure = ''));
        const initial = await buildDrawing(project, library, calculate(project, library));
        project.equipment.forEach(
          (e) =>
            (e.enclosure = ['ps-1', 'dec-2', 'con-1'].includes(e.id)
              ? 'Enclosure 1'
              : 'Enclosure 2'),
        );
        const drawing = await buildDrawing(project, library, calculate(project, library));
        for (const name of ['Enclosure 1', 'Enclosure 2']) {
          const ids = project.equipment.filter((e) => e.enclosure === name).map((e) => e.id);
          const sheets = drawing.sheets.filter((s) => s.nodes.some((n) => ids.includes(n.id)));
          expect(sheets, `${flow} / ${name}`).toHaveLength(1);
          const sheet = sheets[0]!;
          const members = sheet.nodes.filter((n) => ids.includes(n.id));
          expect(members).toHaveLength(ids.length);
          const outlines = sheet.prims.filter(
            (p) =>
              p.kind === 'rect' &&
              p.layer === 'E-ANNO-ENCL' &&
              members.every((n) => contains(p, n)),
          );
          expect(outlines, `${flow} / ${name} common outline`).toHaveLength(1);
          const outline = outlines[0]!;
          if (outline.kind === 'rect')
            expect(
              sheet.nodes.filter((n) => !ids.includes(n.id)).some((n) => intersects(outline, n)),
            ).toBe(false);
        }
        expect(drawing.warnings.some((w) => w.includes('outline split'))).toBe(false);
        expect(
          drawing.sheets
            .flatMap((s) => s.nodes)
            .some((n) => {
              const before = initial.sheets.flatMap((s) => s.nodes).find((b) => b.id === n.id)!;
              return n.x !== before.x || n.y !== before.y;
            }),
        ).toBe(true);
        drawing.sheets.forEach(checkClearance);
      }
  });

  it('keeps a fitting enclosure intact across pagination and preserves control-wire clearances after packing', async () => {
    const library = seedLibrary(),
      project = demoProject();
    project.equipment.forEach((e) => (e.enclosure = 'Enclosure 10'));
    project.equipment.push(
      EquipmentSchema.parse({
        id: 'dim',
        tag: 'DIM-1',
        catalogId: 'dmx-0-10v-converter',
        category: 'dmx-0-10v-converter',
        qty: 1,
        location: 'Controls',
        enclosure: 'Enclosure 10',
        fedFrom: { ref: 'PS-3', port: 'OUT1' },
        feedLengthFt: 8,
        env: 'riser',
        controlFrom: { ref: 'DEC-2', port: 'DATA-OUT' },
        controlLengthFt: 5,
        dmx: { universe: 1, startAddress: 'auto', terminatorPresent: true },
      }),
    );
    project.loads = Array.from({ length: 40 }, (_, i) => ({
      ...project.loads[0]!,
      id: `tape-${i}`,
      typeTag: `T${i + 1}`,
      lengthFt: 1,
    }));
    for (const flow of ['LR', 'TB'] as const)
      for (const showSchedules of [true, false]) {
        project.settings.sheet = { size: 'ARCH_D', flow };
        project.settings.showSchedules = showSchedules;
        const drawing = await buildDrawing(project, library, calculate(project, library));
        const sheets = drawing.sheets.filter((s) =>
          s.nodes.some((n) => project.equipment.some((e) => e.id === n.id)),
        );
        expect(sheets, `${flow} / schedules ${showSchedules}`).toHaveLength(1);
        expect(
          sheets[0]!.nodes.filter((n) => project.equipment.some((e) => e.id === n.id)),
        ).toHaveLength(7);
        expect(drawing.sheets.flatMap((s) => s.nodes)).toHaveLength(49);
        drawing.sheets.forEach(checkClearance);
      }
  });

  it('enforces parallel outline clearance while still allowing a perpendicular cable entry', () => {
    const border = { a: { x: 0, y: 2 }, b: { x: 8, y: 2 } };
    const along = routeOrthogonal(
      { x: 1, y: 2.05 },
      { x: 7, y: 2.05 },
      [],
      { x: 0, y: 0, width: 8, height: 4 },
      [],
      [border],
    );
    expect(along.length).toBeGreaterThan(2);
    expect(
      segmentsOf(along).some((s) => parallelConflict(s, border, ENCLOSURE_WIRE_CLEARANCE)),
    ).toBe(false);
    expect(
      routeOrthogonal(
        { x: 4, y: 1 },
        { x: 4, y: 3 },
        [],
        { x: 0, y: 0, width: 8, height: 4 },
        [],
        [border],
      ),
    ).toEqual([
      { x: 4, y: 1 },
      { x: 4, y: 3 },
    ]);
  });
});
