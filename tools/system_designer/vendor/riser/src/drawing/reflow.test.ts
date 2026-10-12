import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { seedTitleBlocks } from '../data/seeds';
import { buildDrawing } from './build';
import { flattenSheet, type Sheet } from './model';
import { primitiveBounds } from './layout/bounds';
import { parallelConflict, segmentBlocked, segmentsOf, intersects } from './layout/router';
import { textBounds } from './text';

function manyLoads(count: number) {
  const project = demoProject();
  project.loads = Array.from({ length: count }, (_, i) => ({
    ...project.loads[0]!,
    id: `many-${i}`,
    typeTag: `T${i + 1}`,
    lengthFt: 1,
  }));
  return project;
}

function checkGeometry(sheet: Sheet) {
  const area = seedTitleBlocks.find((t) => t.sheetSize === sheet.size)!.drawingArea;
  const flat = flattenSheet(sheet);
  for (const p of flat.filter((p) => p.entityId || p.runId || p.layer === 'E-ANNO-ENCL')) {
    const b = primitiveBounds(p);
    expect(b.x).toBeGreaterThanOrEqual(area.x - 1e-6);
    expect(b.y).toBeGreaterThanOrEqual(area.y - 1e-6);
    expect(b.x + b.width).toBeLessThanOrEqual(area.x + area.width + 1e-6);
    expect(b.y + b.height).toBeLessThanOrEqual(area.y + area.height + 1e-6);
    if (p.kind === 'text') expect(p.heightIn).toBeGreaterThanOrEqual(3 / 32);
  }
  for (const [i, node] of sheet.nodes.entries())
    expect(sheet.nodes.slice(i + 1).some((other) => intersects(node, other, 0.05))).toBe(false);
  const wires = sheet.connections ?? [];
  for (const [i, wire] of wires.entries()) {
    for (const [id, point, continued] of [
      [wire.fromId, wire.points[0]!, wire.fromContinuation],
      [wire.toId, wire.points.at(-1)!, wire.toContinuation],
    ] as const) {
      if (continued) continue;
      const node = sheet.nodes.find((n) => n.id === id)!;
      expect(node).toBeDefined();
      expect(
        Math.abs(point.x - node.x) < 1e-6 ||
          Math.abs(point.x - node.x - node.width) < 1e-6 ||
          Math.abs(point.y - node.y) < 1e-6 ||
          Math.abs(point.y - node.y - node.height) < 1e-6,
      ).toBe(true);
    }
    for (const segment of segmentsOf(wire.points)) {
      expect(segmentBlocked(segment.a, segment.b, sheet.nodes)).toBe(false);
      for (const other of wires.slice(i + 1))
        for (const s of segmentsOf(other.points)) expect(parallelConflict(segment, s)).toBe(false);
      for (const label of flat.filter((p) => p.kind === 'text' && p.role === 'continuation-label'))
        if (label.kind === 'text')
          expect(segmentBlocked(segment.a, segment.b, [textBounds(label)])).toBe(false);
    }
  }
}

describe('diagram-only reflow', () => {
  it('reclaims schedule space before routing and restores the scheduled layout at full size', async () => {
    const project = manyLoads(40),
      library = seedLibrary(),
      result = calculate(project, library);
    const scheduled = await buildDrawing(project, library, result);
    expect(scheduled.sheets.filter((s) => s.nodes.length)).toHaveLength(2);
    project.settings.showSchedules = false;
    const drawing = await buildDrawing(project, library, result);
    expect(drawing.sheets.length).toBeLessThan(scheduled.sheets.length);
    expect(drawing.sheets.flatMap((s) => s.nodes)).toHaveLength(48);
    expect(drawing.sheets[0]!.nodes.length).toBeGreaterThan(scheduled.sheets[0]!.nodes.length);
    expect(drawing.warnings).toEqual([]);
    const before = new Map(scheduled.sheets.flatMap((s) => s.nodes.map((n) => [n.id, n] as const)));
    for (const node of drawing.sheets.flatMap((s) => s.nodes)) {
      expect(node.width).toBe(before.get(node.id)!.width);
      expect(node.height).toBe(before.get(node.id)!.height);
    }
    expect(
      drawing.sheets[0]!.nodes.some(
        (n) => n.x !== before.get(n.id)!.x || n.y !== before.get(n.id)!.y,
      ),
    ).toBe(true);
    const labels = drawing.sheets
      .flatMap(flattenSheet)
      .filter((p) => p.kind === 'text' && p.role === 'continuation-label');
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.every((p) => p.kind === 'text' && /^(FROM|TO) L-/.test(p.value))).toBe(true);
    expect(drawing.sheets[0]!.prims.some((p) => p.layer === 'E-ANNO-SCHD')).toBe(false);
    drawing.sheets.forEach(checkGeometry);
    project.settings.showSchedules = true;
    expect((await buildDrawing(project, library, result)).sheets).toEqual(scheduled.sheets);
  });

  it('reflows 200 loads and updates every incoming and grouped outgoing sheet reference', async () => {
    const project = manyLoads(200),
      library = seedLibrary(),
      result = calculate(project, library);
    project.settings.showSchedules = false;
    const drawing = await buildDrawing(project, library, result);
    expect(drawing.sheets).toHaveLength(5);
    expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(208);
    const pageOf = new Map(
      drawing.sheets.flatMap((s) => s.nodes.map((n) => [n.id, s.number] as const)),
    );
    for (const sheet of drawing.sheets) {
      checkGeometry(sheet);
      for (const p of sheet.prims) {
        if (p.kind !== 'text' || p.role !== 'continuation-label' || !p.runId) continue;
        const run = result.runs.find((r) => r.runId === p.runId)!;
        if (p.value.startsWith('FROM'))
          expect(p.value.replaceAll('\n', ' ')).toContain(pageOf.get(run.from.id)!);
        const mentioned = p.value.match(/L-\d+/g) ?? [];
        expect(mentioned.every((number) => drawing.sheets.some((s) => s.number === number))).toBe(
          true,
        );
      }
    }
    const allConnections = drawing.sheets.flatMap((s) => s.connections ?? []);
    for (const run of result.runs) {
      const segments = allConnections.filter((c) => c.runId === run.runId);
      expect(segments.length).toBeGreaterThan(0);
      expect(segments.some((c) => !c.toContinuation)).toBe(true);
      if (segments.some((c) => c.fromContinuation)) {
        const reference = segments.find((c) => c.fromContinuation)!.reference;
        expect(allConnections.some((c) => c.toContinuation && c.reference === reference)).toBe(
          true,
        );
      }
    }
  }, 30000);

  it('preserves clearances across paper sizes and flow directions', async () => {
    const library = seedLibrary();
    for (const flow of ['LR', 'TB'] as const)
      for (const size of ['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D'] as const) {
        const project = manyLoads(24);
        project.settings.showSchedules = false;
        project.settings.sheet = { size, flow };
        const drawing = await buildDrawing(project, library, calculate(project, library));
        expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(32);
        for (const sheet of drawing.sheets) checkGeometry(sheet);
      }
  }, 30000);

  it('retains existing absolute pin positions while packing the other sections', async () => {
    const project = manyLoads(40),
      library = seedLibrary(),
      result = calculate(project, library);
    const initial = await buildDrawing(project, library, result);
    const node = initial.sheets.flatMap((s) => s.nodes).find((n) => n.id === 'ps-1')!;
    project.layoutOverrides[node.id] = { x: node.x, y: node.y, pinned: true };
    project.settings.showSchedules = false;
    const drawing = await buildDrawing(project, library, result);
    const pinned = drawing.sheets.flatMap((s) => s.nodes).find((n) => n.id === node.id)!;
    expect(pinned.x).toBe(node.x);
    expect(pinned.y).toBe(node.y);
    expect(pinned.pinned).toBe(true);
    for (const sheet of drawing.sheets) checkGeometry(sheet);
  });
});
