import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { buildDrawing } from './build';
import { flattenSheet, type Sheet } from './model';
import { intersects, segmentBlocked, segmentsOf } from './layout/router';
import { sheetReferences } from './layout/continuations';
import { textBounds } from './text';

function checkContinuations(sheet: Sheet) {
  const flat = flattenSheet(sheet);
  const bubbles = flat.filter((p) => p.kind === 'circle' && p.role === 'continuation');
  for (const p of bubbles) {
    if (p.kind !== 'circle') continue;
    const box = { x: p.x - p.radius, y: p.y - p.radius, width: p.radius * 2, height: p.radius * 2 };
    expect(
      sheet.nodes.some((n) => intersects(box, n)),
      `${sheet.number}: bubble overlaps equipment`,
    ).toBe(false);
    for (const q of flat.filter((t) => t.kind === 'text')) {
      if (q.kind !== 'text' || (q.role === 'continuation' && q.runId === p.runId)) continue;
      expect(intersects(box, textBounds(q)), `${sheet.number}: bubble overlaps ${q.value}`).toBe(
        false,
      );
    }
    for (const c of sheet.connections ?? [])
      for (const seg of segmentsOf(c.points))
        expect(
          segmentBlocked(seg.a, seg.b, [box]),
          `${sheet.number}: ${c.runId} crosses bubble`,
        ).toBe(false);
    for (const q of bubbles) {
      if (q === p || q.kind !== 'circle') continue;
      expect(Math.hypot(p.x - q.x, p.y - q.y)).toBeGreaterThan(p.radius + q.radius + 0.05);
    }
    expect(
      flat.some(
        (q) =>
          q.kind === 'text' &&
          q.role === 'continuation-label' &&
          q.runId === p.runId &&
          /^(TO |FROM |CONT\.)/.test(q.value),
      ),
    ).toBe(true);
  }
  for (const label of flat.filter((p) => p.kind === 'text' && p.role === 'continuation-label')) {
    if (label.kind !== 'text') continue;
    expect(label.heightIn).toBeGreaterThanOrEqual(3 / 32);
    expect(sheet.nodes.some((n) => intersects(textBounds(label), n))).toBe(false);
    for (const c of sheet.connections ?? [])
      for (const seg of segmentsOf(c.points))
        expect(
          segmentBlocked(seg.a, seg.b, [textBounds(label)]),
          `${sheet.number}: ${c.runId} crosses ${label.value}`,
        ).toBe(false);
  }
}

describe('compact multi-sheet risers', () => {
  it('can omit schedules and legends without dropping the diagram or title block', async () => {
    const project = demoProject(),
      library = seedLibrary();
    project.settings.showSchedules = false;
    const result = calculate(project, library);
    const drawing = await buildDrawing(project, library, result);
    expect(drawing.sheets).toHaveLength(1);
    expect(drawing.sheets[0]!.nodes).toHaveLength(14);
    expect(drawing.sheets[0]!.connections).toHaveLength(result.runs.length);
    expect(drawing.sheets[0]!.prims.some((p) => p.layer === 'E-ANNO-TTLB')).toBe(true);
    expect(drawing.sheets[0]!.prims.some((p) => p.layer === 'E-ANNO-SCHD')).toBe(false);
  });

  it('routes dense decoders directly to local loads and uses straight leads only for remote loads', async () => {
    const project = demoProject(),
      library = seedLibrary();
    const decoder = library.products.find((p) => p.id === 'decoder-4ch')!;
    if (decoder.specs.kind !== 'decoder') throw new Error('Decoder required');
    decoder.specs.channels = 12;
    decoder.specs.dmxFootprint = 12;
    project.settings.showSchedules = false;
    project.loads = Array.from({ length: 24 }, (_, i) => ({
      ...project.loads[2]!,
      id: `tape-${i}`,
      typeTag: `T${i + 1}`,
      lengthFt: 1,
      fedFrom: { ref: i < 12 ? 'DEC-1' : 'DEC-2', port: `CH${(i % 12) + 1}` },
    }));
    const drawing = await buildDrawing(project, library, calculate(project, library));
    const leads = drawing.sheets.flatMap((s) =>
      (s.connections ?? []).filter((c) => c.toContinuation && c.fromId.startsWith('dec-')),
    );
    expect(leads.length).toBeGreaterThan(0);
    expect(drawing.sheets).toHaveLength(2);
    expect(drawing.sheets.flatMap((s) => s.nodes)).toHaveLength(32);
    for (const sheet of drawing.sheets)
      for (const c of sheet.connections ?? []) {
        if (c.reference)
          expect(
            sheet.nodes.some((n) => n.id === c.fromId) && sheet.nodes.some((n) => n.id === c.toId),
          ).toBe(false);
      }
    expect(leads.filter((c) => c.points.length === 2).length).toBe(leads.length);
    for (const sheet of drawing.sheets) checkContinuations(sheet);
  });
  it('protects every continuation bubble and sheet/cable label on all paper sizes and both flows', async () => {
    const library = seedLibrary();
    for (const flow of ['LR', 'TB'] as const)
      for (const size of ['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D'] as const) {
        const project = demoProject();
        project.settings.sheet = { size, flow };
        project.loads = Array.from({ length: 40 }, (_, i) => ({
          ...project.loads[0]!,
          id: `many-${i}`,
          typeTag: `T${i + 1}`,
          lengthFt: 1,
        }));
        const result = calculate(project, library);
        const drawing = await buildDrawing(project, library, result);
        expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(48);
        for (const sheet of drawing.sheets) checkContinuations(sheet);
        if (size === 'ARCH_D' && flow === 'LR') {
          expect(drawing.sheets.filter((s) => s.nodes.length)).toHaveLength(2);
          expect(drawing.sheets.length).toBeLessThanOrEqual(4);
          expect(drawing.warnings).toEqual([]);
          expect(drawing.sheets[0]!.prims.some((p) => p.layer === 'E-ANNO-SCHD')).toBe(true);
        }
        for (const run of result.runs) {
          const references = drawing.sheets
            .flatMap((s) => s.connections ?? [])
            .filter((c) => c.runId === run.runId && c.reference);
          if (references.length)
            expect(
              drawing.sheets
                .flatMap((s) => flattenSheet(s))
                .some(
                  (p) =>
                    p.kind === 'text' &&
                    p.role === 'continuation-label' &&
                    p.runId === run.runId &&
                    p.value.includes(run.tag),
                ),
            ).toBe(true);
        }
      }
  }, 30000);

  it('compresses sheet ranges without dropping references', () => {
    expect(sheetReferences([4, 0, 2, 1, 2, 8], 'EL-')).toBe('EL-1–EL-3, EL-5, EL-9');
  });

  it('packs mixed circuit groups while preserving power and DMX continuation identities', async () => {
    const project = demoProject();
    const library = seedLibrary();
    const source = project.sources[0]!,
      psu = project.equipment[0]!,
      decoder = project.equipment.find((e) => e.id === 'dec-1')!,
      controller = project.equipment.find((e) => e.id === 'con-1')!,
      load = project.loads[0]!;
    project.sources = [];
    project.equipment = [];
    project.loads = [];
    for (let i = 0; i < 12; i++) {
      project.sources.push({
        ...source,
        id: `source-${i}`,
        tag: `LP/ ${i + 1}`,
        circuit: `${i + 1}`,
      });
      project.equipment.push(
        {
          ...psu,
          id: `ps-${i}`,
          tag: `PS-${i + 1}`,
          enclosure: `Cabinet ${i + 1}`,
          fedFrom: { ref: `source-${i}` },
        },
        {
          ...decoder,
          id: `decoder-${i}`,
          tag: `DEC-${i + 1}`,
          enclosure: `Cabinet ${i + 1}`,
          fedFrom: { ref: `ps-${i}`, port: 'OUT1' },
          controlFrom: { ref: i ? `decoder-${i - 1}` : 'controller', port: 'DATA-OUT' },
          dmx: { universe: 1, startAddress: 'auto', terminatorPresent: i === 11 },
        },
      );
      for (let j = 0; j < 3; j++)
        project.loads.push({
          ...load,
          id: `load-${i}-${j}`,
          typeTag: `T${i + 1}.${j + 1}`,
          lengthFt: 1,
          fedFrom: { ref: `decoder-${i}`, port: 'CH1-4' },
        });
    }
    project.equipment.push({
      ...controller,
      id: 'controller',
      tag: 'CTRL',
      fedFrom: { ref: 'ps-0', port: 'OUT1' },
    });
    const result = calculate(project, library);
    const drawing = await buildDrawing(project, library, result);
    expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(73);
    for (const sheet of drawing.sheets) checkContinuations(sheet);
    const runIds = new Set(drawing.sheets.flatMap((s) => s.connections ?? []).map((c) => c.runId));
    expect(result.runs.every((r) => runIds.has(r.runId))).toBe(true);
  }, 30000);
});
