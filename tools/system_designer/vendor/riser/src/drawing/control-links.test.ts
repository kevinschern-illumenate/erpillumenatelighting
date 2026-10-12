import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { EquipmentSchema, LoadSchema, ControlLinkSchema } from '../schemas/project';
import { calculate } from '../engine/calculate';
import { controlPortOptions } from '../engine/ports';
import { buildDrawing } from './build';
import { controlName } from './layout/continuations';
import { flattenSheet } from './model';
import { segmentBlocked, segmentsOf } from './layout/router';
import { textBounds } from './text';

function controlSystem() {
  const project = demoProject(),
    library = seedLibrary();
  project.equipment.push(
    EquipmentSchema.parse({
      ...project.equipment.find((e) => e.id === 'dec-2')!,
      id: 'dec-3',
      tag: 'DEC-3',
      fedFrom: { ref: 'PS-3', port: 'OUT1' },
      controlFrom: { ref: 'DEC-2', port: 'DATA-OUT' },
      enclosure: 'Cabinet B',
    }),
    EquipmentSchema.parse({
      id: 'dim',
      tag: 'DIM-1',
      catalogId: 'dmx-0-10v-converter',
      category: 'dmx-0-10v-converter',
      qty: 1,
      location: 'Controls',
      enclosure: 'Controls',
      fedFrom: { ref: 'PS-3', port: 'OUT1' },
      feedLengthFt: 8,
      env: 'riser',
      controlFrom: { ref: 'DEC-3', port: 'DATA-OUT' },
      controlLengthFt: 25,
      dmx: { universe: 1, startAddress: 'auto', terminatorPresent: true },
    }),
  );
  project.loads = Array.from({ length: 12 }, (_, i) =>
    LoadSchema.parse({
      ...project.loads[2]!,
      id: `tape-${i}`,
      typeTag: `T${i + 1}`,
      lengthFt: 1,
      fedFrom: { ref: `DEC-${Math.floor(i / 4) + 1}`, port: `CH${(i % 4) + 1}` },
    }),
  );
  project.loads.push(
    LoadSchema.parse({
      id: 'downlight',
      typeTag: 'DL1',
      zone: 'Downlights',
      catalogId: 'downlight-line',
      qty: 2,
      fedFrom: { ref: 'LP-1/12' },
      homeRunLengthFt: 20,
      feedMethod: 'end',
      env: 'raceway',
    }),
  );
  project.controlLinks = [
    ControlLinkSchema.parse({
      id: 'dim-downlight',
      protocol: '0-10V',
      from: { ref: 'DIM-1', port: 'DIM1' },
      to: { ref: 'downlight' },
      lengthFt: 35,
      env: 'plenum',
    }),
  ];
  return { project, library };
}

describe('visible control wiring', () => {
  it('offers named 0-10 V outputs and fixture dimming inputs and retains separate power and signal cables', () => {
    const { project, library } = controlSystem();
    expect(
      controlPortOptions(project, library.products, 'out', '0-10V', 'downlight'),
    ).toContainEqual(expect.objectContaining({ value: 'DIM-1::DIM1' }));
    expect(controlPortOptions(project, library.products, 'in', '0-10V', 'DIM-1')).toContainEqual(
      expect.objectContaining({
        value: 'downlight',
        label: expect.stringContaining('DL1 / DIM IN'),
      }),
    );
    const result = calculate(project, library);
    const signal = result.runs.find((r) => r.runId === 'control:dim-downlight')!;
    expect(signal).toMatchObject({
      type: '0-10v',
      protocol: '0-10V',
      lengthFt: 35,
      env: 'plenum',
      required: { signal: 2 },
    });
    expect(signal.wireTypeId).not.toBeNull();
    expect(result.runs.some((r) => r.to.id === 'downlight' && r.type === 'lv-branch')).toBe(true);
  });

  it('keeps every DMX and 0-10 V cable identified at both ends with and without schedules', async () => {
    const { project, library } = controlSystem();
    for (const showSchedules of [true, false])
      for (const flow of ['LR', 'TB'] as const) {
        project.settings.showSchedules = showSchedules;
        project.settings.sheet = { size: 'ANSI_B', flow };
        const result = calculate(project, library);
        const drawing = await buildDrawing(project, library, result);
        if (!showSchedules && flow === 'LR') {
          expect(
            drawing.sheets.filter((s) => s.nodes.some((n) => n.id === 'ps-3' || n.id === 'dec-3')),
          ).toHaveLength(1);
          expect(drawing.sheets.length).toBeLessThanOrEqual(6);
          expect(drawing.sheets[0]!.nodes.filter((n) => n.id.startsWith('src-'))).toHaveLength(2);
          expect(drawing.sheets[0]!.nodes.some((n) => n.id.startsWith('tape-'))).toBe(false);
        }
        const controls = result.runs.filter((r) => r.protocol);
        expect(controls).toHaveLength(5);
        expect(drawing.sheets.filter((s) => s.nodes.length).length).toBeGreaterThan(1);
        for (const run of controls) {
          const entries = drawing.sheets.flatMap((sheet) =>
            (sheet.connections ?? [])
              .filter((c) => c.runId === run.runId)
              .map((c) => ({ sheet, c })),
          );
          expect(entries.some(({ c }) => !c.fromContinuation)).toBe(true);
          expect(entries.some(({ c }) => !c.toContinuation)).toBe(true);
          for (const { sheet, c } of entries) {
            const flat = flattenSheet(sheet);
            const labels = flat.filter(
              (p) =>
                p.kind === 'text' &&
                p.runId === run.runId &&
                (p.role === 'continuation-label' || p.role === 'wire-tag'),
            );
            expect(labels.length, `${sheet.number} / ${run.tag} labeled`).toBeGreaterThan(0);
            expect(
              labels.some(
                (p) =>
                  p.kind === 'text' &&
                  p.value.includes(controlName(run)) &&
                  p.value.includes(run.tag),
              ),
            ).toBe(true);
            if (c.reference) {
              expect(entries).toHaveLength(2);
              expect(entries.every(({ c: other }) => other.reference === c.reference)).toBe(true);
              const remote = c.toContinuation ? run.to : run.from;
              expect(labels.some((p) => p.kind === 'text' && p.value.includes(remote.tag))).toBe(
                true,
              );
              const otherSheet = entries.find((e) => e !== undefined && e.c !== c)!.sheet;
              expect(
                labels.some(
                  (p) =>
                    p.kind === 'text' &&
                    (p.value.includes(otherSheet.number) ||
                      (otherSheet === sheet && p.value.startsWith('CONT.'))),
                ),
              ).toBe(true);
            }
            for (const label of labels)
              if (label.kind === 'text')
                for (const cable of sheet.connections ?? [])
                  for (const segment of segmentsOf(cable.points))
                    expect(segmentBlocked(segment.a, segment.b, [textBounds(label)])).toBe(false);
          }
          expect(drawing.warnings.some((w) => w.includes(`${run.tag}: callout moved`))).toBe(false);
        }
      }
  }, 30000);

  it('gives separate control cables from the same output their own outgoing references', async () => {
    const project = demoProject(),
      library = seedLibrary();
    project.settings.sheet = { size: 'ANSI_B', flow: 'LR' };
    project.settings.showSchedules = false;
    project.loads = [];
    const decoder = project.equipment.find((e) => e.id === 'dec-1')!;
    project.equipment = project.equipment.filter((e) => e.category !== 'dmx-decoder');
    project.equipment.push(
      ...Array.from({ length: 8 }, (_, i) => ({
        ...decoder,
        id: `receiver-${i}`,
        tag: `REC-${i + 1}`,
      })),
    );
    const result = calculate(project, library);
    const drawing = await buildDrawing(project, library, result);
    // Even a physically invalid DMX branch must retain both visible cables;
    // engineering validation separately flags the need for an isolated splitter.
    const outgoing = result.runs.filter((r) => r.from.id === 'con-1' && r.protocol === 'DMX512');
    expect(outgoing).toHaveLength(8);
    const references = outgoing.flatMap((run) => {
      const entries = drawing.sheets.flatMap((s) =>
        (s.connections ?? []).filter((c) => c.runId === run.runId),
      );
      expect(entries.some((c) => !c.fromContinuation)).toBe(true);
      expect(entries.some((c) => !c.toContinuation)).toBe(true);
      if (entries.length === 1) {
        expect(entries[0]!.reference).toBeUndefined();
        return [];
      }
      expect(entries).toHaveLength(2);
      expect(entries[0]!.reference).toBeTruthy();
      expect(entries[0]!.reference).toBe(entries[1]!.reference);
      return [entries[0]!.reference];
    });
    expect(references.length).toBeGreaterThanOrEqual(2);
    expect(new Set(references).size).toBe(references.length);
  });
});
