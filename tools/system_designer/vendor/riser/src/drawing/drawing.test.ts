import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { buildDrawing } from './build';
import { DrawingSchema, flattenSheet, SymbolSchema } from './model';
import { symbols } from './symbols';
import { serializeSvg } from '../serializers/svg';
import { textWidth, wrapText } from './text';
import { intersects, routeOrthogonal, segmentBlocked } from './layout/router';

describe('shared paper geometry', () => {
  it('keeps top-to-bottom stages in functional order and supports all paper sizes', async () => {
    for (const size of ['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D'] as const) {
      const p = demoProject();
      p.settings.sheet = { size, flow: 'TB' };
      const l = seedLibrary();
      const d = await buildDrawing(p, l, calculate(p, l));
      expect(d.sheets.flatMap((s) => s.nodes)).toHaveLength(14);
      for (const s of d.sheets) {
        const supply = s.nodes.find((n) => n.id === 'ps-1'),
          decoder = s.nodes.find((n) => n.id === 'dec-1');
        if (supply && decoder) expect(supply.y).toBeGreaterThan(decoder.y + decoder.height);
        for (const n of s.nodes) {
          expect(n.x).toBeGreaterThan(0);
          expect(n.y).toBeGreaterThan(0);
          expect(n.x + n.width).toBeLessThan(s.widthIn);
          expect(n.y + n.height).toBeLessThan(s.heightIn);
        }
      }
    }
  }, 30000);
  it('finds multi-turn pin detours and rejects an enclosed endpoint', () => {
    const area = { x: 0, y: 0, width: 10, height: 10 };
    const obstacles = [
      { x: 2, y: -1, width: 1, height: 8 },
      { x: 5, y: 3, width: 1, height: 8 },
      { x: 8, y: -1, width: 1, height: 8 },
    ];
    const route = routeOrthogonal({ x: 1, y: 1 }, { x: 9.5, y: 9 }, obstacles, area);
    expect(route.length).toBeGreaterThan(4);
    expect(route.slice(1).every((p, i) => !segmentBlocked(route[i]!, p, obstacles))).toBe(true);
    expect(() => routeOrthogonal({ x: 2.5, y: 2 }, { x: 9, y: 8 }, obstacles, area)).toThrow(
      'no clear',
    );
  });
  it('lays out 200 loads within two seconds at true plotted size', async () => {
    const project = demoProject();
    project.loads = Array.from({ length: 200 }, (_, i) => ({
      ...project.loads[0]!,
      id: `large-${i}`,
      typeTag: `T${i}`,
      lengthFt: 1,
    }));
    const library = seedLibrary();
    const drawing = await buildDrawing(project, library, calculate(project, library));
    expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(208);
    expect(drawing.elapsedMs).toBeLessThan(2000);
    for (const sheet of drawing.sheets)
      for (const p of flattenSheet(sheet))
        if (p.kind === 'polyline')
          for (const point of p.points) {
            expect(point.x).toBeGreaterThanOrEqual(0);
            expect(point.y).toBeGreaterThanOrEqual(0);
            expect(point.x).toBeLessThanOrEqual(sheet.widthIn);
            expect(point.y).toBeLessThanOrEqual(sheet.heightIn);
          }
  }, 30000);
  it('validates every symbol, attribute set and plotted text size', () => {
    expect(symbols.length).toBe(24);
    for (const symbol of symbols) {
      expect(SymbolSchema.safeParse(symbol).success).toBe(true);
      expect(symbol.attributes.map((a) => a.tag)).toEqual([
        'TAG',
        'MODEL',
        'VIN',
        'VOUT',
        'WATTS',
        'LOAD_PCT',
        'DMX_ADDR',
        'LOCATION',
      ]);
    }
    expect(
      wrapText('A very long model number with spaces', 0.8).every((l) => textWidth(l) <= 0.8),
    ).toBe(true);
  });
  it('routes around pinned obstacles using orthogonal segments', () => {
    const obstacles = [{ x: 2, y: 1, width: 2, height: 2 }];
    const path = routeOrthogonal({ x: 0, y: 2 }, { x: 6, y: 2 }, obstacles, {
      x: 0,
      y: 0,
      width: 8,
      height: 5,
    });
    expect(
      path.every(
        (p, i) =>
          i === 0 ||
          (!segmentBlocked(path[i - 1]!, p, obstacles) &&
            (p.x === path[i - 1]!.x || p.y === path[i - 1]!.y)),
      ),
    ).toBe(true);
  });
  it('lays out the complete demo, paginates schedules and serializes deterministic SVG', async () => {
    const project = demoProject(),
      library = seedLibrary(),
      result = calculate(project, library);
    const drawing = await buildDrawing(project, library, result);
    expect(DrawingSchema.safeParse(drawing).success).toBe(true);
    expect(drawing.sheets.flatMap((s) => s.nodes).length).toBe(14);
    for (const sheet of drawing.sheets) {
      for (let i = 0; i < sheet.nodes.length; i++)
        for (let j = i + 1; j < sheet.nodes.length; j++)
          expect(intersects(sheet.nodes[i]!, sheet.nodes[j]!)).toBe(false);
      expect(
        flattenSheet(sheet)
          .filter((p) => p.kind === 'text')
          .every((p) => p.heightIn >= 3 / 32),
      ).toBe(true);
      const svg = serializeSvg(sheet);
      expect(svg).not.toContain('E-ANNO-QAFL');
      expect(svg).toContain('1.000 in');
      expect(svg).toBe(serializeSvg(sheet));
    }
  }, 20000);
  it('paginates 40 loads without losing devices and honors persisted pins', async () => {
    const project = demoProject();
    project.loads = Array.from({ length: 40 }, (_, i) => ({
      ...project.loads[0]!,
      id: `many-${i}`,
      typeTag: `T${i}`,
      lengthFt: 1,
    }));
    const library = seedLibrary();
    const drawing = await buildDrawing(project, library, calculate(project, library));
    expect(drawing.sheets.filter((s) => s.nodes.length).length).toBeGreaterThan(1);
    expect(new Set(drawing.sheets.flatMap((s) => s.nodes.map((n) => n.id))).size).toBe(48);
    expect(
      drawing.sheets
        .flatMap((s) => flattenSheet(s))
        .some((p) => p.kind === 'text' && p.value.includes('TO L-')),
    ).toBe(true);
    const small = demoProject();
    small.layoutOverrides['ps-1'] = { x: 23, y: 12, pinned: true };
    const pinned = await buildDrawing(small, library, calculate(small, library));
    expect(pinned.sheets.flatMap((s) => s.nodes).find((n) => n.id === 'ps-1')).toMatchObject({
      x: 23,
      y: 12,
      pinned: true,
    });
  }, 30000);
});
