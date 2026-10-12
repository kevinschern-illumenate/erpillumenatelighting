import { describe, it, expect } from 'vitest';
import { demoProject } from '@ill/data/demo';
import { seedLibrary } from '@ill/data/library';
import { calculate } from '@ill/engine/calculate';
import { buildDrawing } from './build';
import { flattenSheet, type Point } from './model';
import { parallelConflict, segmentsOf, segmentBlocked, crossing } from './layout/router';
import { textBounds } from './text';

describe('riser drafting quality', () => {
  it('keeps cable lanes and equipment clear in both flows on every paper size', async () => {
    for (const flow of ['LR', 'TB'] as const)
      for (const size of ['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D'] as const) {
        const p = demoProject(),
          library = seedLibrary();
        p.settings.sheet = { size, flow };
        const drawing = await buildDrawing(p, library, calculate(p, library));
        for (const sheet of drawing.sheets) {
          const wires = sheet.connections ?? [];
          for (const c of wires)
            for (const seg of segmentsOf(c.points)) {
              expect(
                segmentBlocked(seg.a, seg.b, sheet.nodes),
                `${flow} ${size} ${c.runId} crosses node`,
              ).toBe(false);
              for (const other of wires.filter((o) => o.runId !== c.runId))
                for (const s of segmentsOf(other.points))
                  expect(
                    parallelConflict(seg, s),
                    `${flow} ${size} ${c.runId} / ${other.runId}`,
                  ).toBe(false);
            }
        }
      }
  });
  it('lands every cable on its equipment outline and keeps independent cables separated', async () => {
    const project = demoProject(),
      library = seedLibrary();
    const result = calculate(project, library);
    const drawing = await buildDrawing(project, library, result);
    for (const sheet of drawing.sheets) {
      const connections = sheet.connections ?? [];
      const onOutline = (id: string, p: Point) => {
        const box = sheet.nodes.find((n) => n.id === id);
        if (!box) return;
        const onX = Math.abs(p.x - box.x) < 1e-6 || Math.abs(p.x - box.x - box.width) < 1e-6;
        const onY = Math.abs(p.y - box.y) < 1e-6 || Math.abs(p.y - box.y - box.height) < 1e-6;
        expect(onX || onY, `${id} terminal on outline`).toBe(true);
        expect(p.x).toBeGreaterThanOrEqual(box.x - 1e-6);
        expect(p.x).toBeLessThanOrEqual(box.x + box.width + 1e-6);
        expect(p.y).toBeGreaterThanOrEqual(box.y - 1e-6);
        expect(p.y).toBeLessThanOrEqual(box.y + box.height + 1e-6);
      };
      for (const c of connections) {
        onOutline(c.fromId, c.points[0]!);
        onOutline(c.toId, c.points.at(-1)!);
        for (const seg of segmentsOf(c.points)) {
          expect(segmentBlocked(seg.a, seg.b, sheet.nodes), `${c.runId} crosses equipment`).toBe(
            false,
          );
          for (const other of connections.filter((o) => o.runId !== c.runId))
            for (const s of segmentsOf(other.points))
              expect(parallelConflict(seg, s), `${c.runId} / ${other.runId} share a lane`).toBe(
                false,
              );
        }
      }
      const flat = flattenSheet(sheet);
      for (const p of flat.filter((p) => p.kind === 'text' && p.role === 'wire-tag')) {
        if (p.kind !== 'text') continue;
        for (const c of connections)
          for (const s of segmentsOf(c.points))
            expect(segmentBlocked(s.a, s.b, [textBounds(p)]), `${p.value} crosses ${c.runId}`).toBe(
              false,
            );
      }
      for (let i = 0; i < connections.length; i++)
        for (const a of segmentsOf(connections[i]!.points))
          for (const b of connections.slice(i + 1).flatMap((c) => segmentsOf(c.points))) {
            const cross = crossing(a, b);
            if (cross)
              expect(
                flat.some(
                  (p) =>
                    p.kind === 'arc' &&
                    p.role === 'wire' &&
                    Math.abs(p.x - cross.x) < 1e-6 &&
                    Math.abs(p.y - cross.y) < 1e-6,
                ),
              ).toBe(true);
          }
    }
    const riser = drawing.sheets.find((s) => s.nodes.length)!;
    expect(riser.connections).toHaveLength(result.runs.length);
    expect(riser.nodes.find((n) => n.id === 'ps-1')!.x).toBe(
      riser.nodes.find((n) => n.id === 'ps-2')!.x,
    );
    expect(riser.nodes.find((n) => n.id === 'ps-1')!.x).toBe(
      riser.nodes.find((n) => n.id === 'ps-3')!.x,
    );
    expect(riser.connections!.find((c) => c.toId === 'ps-2')!.fromPort).toBe('AC-THRU');
    for (const run of result.runs)
      expect(
        flattenSheet(riser).some(
          (p) => p.kind === 'text' && p.role === 'wire-tag' && p.value.includes(run.tag),
        ),
        `${run.tag} is labeled`,
      ).toBe(true);
  });
});
