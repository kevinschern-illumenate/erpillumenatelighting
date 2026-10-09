import { describe, expect, it } from 'vitest';
import { titleBlockLogo, flattenContour } from './brand';
import { translate, PrimitiveSchema, type Contour } from './model';
import { seedTitleBlocks } from '@ill/data/seeds';
import { demoProject } from '@ill/data/demo';
import { frameSheet } from './sheet/compose';
import type { Sheet } from './model';
import { serializeDxf } from '@ill/serializers/dxf/dxf';
import { serializeSvg } from '@ill/serializers/svg';

describe('supplied vector branding', () => {
  it('fits every title block with clear space and retains compound letter counters', () => {
    for (const template of seedTitleBlocks) {
      const region = template.fields.find((f) => f.name === 'brandLogo')!.region;
      const logo = titleBlockLogo(region);
      expect(logo).toHaveLength(26);
      expect(logo.filter((p) => p.kind === 'filledPath' && p.contours.length > 1)).toHaveLength(5);
      for (const p of logo) {
        expect(PrimitiveSchema.safeParse(p).success).toBe(true);
        if (p.kind !== 'filledPath') throw new Error('Logo must remain vector paths');
        for (const c of p.contours)
          for (const pt of flattenContour(c)) {
            expect(pt.x).toBeGreaterThan(region.x + 0.04);
            expect(pt.x).toBeLessThan(region.x + region.width - 0.04);
            expect(pt.y).toBeGreaterThan(region.y + 0.06);
            expect(pt.y).toBeLessThan(region.y + region.height - 0.06);
          }
      }
    }
  });
  it('preserves vector logos and letter holes in SVG and tiled native CAD exports', () => {
    const template = seedTitleBlocks[0]!;
    const sheet: Sheet = {
      id: 'brand',
      number: 'L-1',
      title: 'Riser',
      size: template.sheetSize,
      widthIn: template.widthIn,
      heightIn: template.heightIn,
      prims: [],
      nodes: [],
      blocks: [],
      layoutWarnings: [],
    };
    const project = demoProject();
    frameSheet(sheet, project, 1);
    const svg = serializeSvg(sheet);
    expect(svg.match(/fill-rule="nonzero"/g)).toHaveLength(26);
    expect(svg).not.toContain('<image');
    const dxf = serializeDxf([sheet, { ...sheet, id: 'brand2', number: 'L-2' }]);
    expect(dxf.match(/\r\nHATCH\r\n/g)).toHaveLength(52);
    expect(dxf.match(/\r\n91\r\n2\r\n92\r\n2\r\n/g)).toHaveLength(10);
    const logo = sheet.prims.find((p) => p.kind === 'filledPath')!;
    if (logo.kind !== 'filledPath') throw new Error('Logo missing');
    const moved = translate(logo, 38, 0);
    if (moved.kind !== 'filledPath') throw new Error('Wrong geometry');
    expect(moved.contours[0]!.start.x).toBe(logo.contours[0]!.start.x + 38);
    project.meta.brand = '206';
    sheet.prims = [];
    frameSheet(sheet, project, 1);
    expect(sheet.prims.some((p) => p.kind === 'filledPath')).toBe(false);
    expect(sheet.prims.some((p) => p.kind === 'text' && p.value === '206 LIGHTING')).toBe(true);
  });
  it('flattens closed curves within plotted CAD tolerance without collapsing a loop', () => {
    const contour: Contour = {
      start: { x: 0, y: 0 },
      segments: [
        { kind: 'cubic', control1: { x: 0, y: 1 }, control2: { x: 1, y: 1 }, to: { x: 1, y: 0 } },
        { kind: 'line', to: { x: 0, y: 0 } },
      ],
    };
    const points = flattenContour(contour);
    expect(points.length).toBeGreaterThan(30);
    expect(points.at(-1)).toEqual({ x: 1, y: 0 });
    for (let i = 0; i <= 100; i++) {
      const t = i / 100,
        u = 1 - t;
      const x = 3 * u * t * t + t * t * t,
        y = 3 * u * u * t + 3 * u * t * t;
      const distance = Math.min(
        ...points.slice(1).map((b, j) => {
          const a = points[j]!,
            dx = b.x - a.x,
            dy = b.y - a.y;
          const q = Math.max(
            0,
            Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy)),
          );
          return Math.hypot(x - a.x - q * dx, y - a.y - q * dy);
        }),
      );
      expect(distance).toBeLessThanOrEqual(0.0001);
    }
  });
});
