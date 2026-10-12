import { describe, it, expect } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { EquipmentSchema, LoadSchema, ProjectSchema } from '../schemas/project';
import { calculate } from '../engine/calculate';
import { buildDrawing } from './build';
import { flattenSheet } from './model';
import { intersects, type Bounds } from './layout/router';

const before = (a: Bounds, b: Bounds, flow: 'LR' | 'TB') =>
  flow === 'LR' ? a.x + a.width < b.x : a.y > b.y + b.height;

describe('functional column layout', () => {
  it('places panels, enclosures, external supplies, external controls and loads in sequence', async () => {
    const library = seedLibrary();
    for (const flow of ['LR', 'TB'] as const) {
      const p = demoProject();
      p.settings.showSchedules = false;
      p.settings.sheet = { size: 'ARCH_D', flow };
      p.sources = p.sources.slice(0, 1);
      const supply = p.equipment[0]!,
        decoder = p.equipment.find((e) => e.id === 'dec-1')!;
      delete decoder.controlFrom;
      delete decoder.controlLengthFt;
      supply.enclosure = decoder.enclosure = 'CAB-1';
      p.equipment = [
        supply,
        decoder,
        EquipmentSchema.parse({
          ...supply,
          id: 'external-ps',
          tag: 'EXT-PS',
          enclosure: undefined,
          fedFrom: { ref: 'PS-1', port: 'AC-THRU' },
        }),
        EquipmentSchema.parse({
          id: 'dim',
          tag: 'DIM',
          catalogId: 'dmx-0-10v-converter',
          category: 'dmx-0-10v-converter',
          qty: 1,
          location: 'Room',
          fedFrom: { ref: 'EXT-PS', port: 'OUT1' },
          feedLengthFt: 5,
          env: 'riser',
        }),
      ];
      p.loads = [
        LoadSchema.parse({
          ...p.loads[4]!,
          id: 'downlight',
          typeTag: 'DL1',
          fedFrom: { ref: 'LP-1/12' },
        }),
      ];
      p.controlLinks = [
        {
          id: 'dim-link',
          protocol: '0-10V',
          from: { ref: 'DIM', port: 'DIM1' },
          to: { ref: 'downlight' },
          lengthFt: 10,
          env: 'riser',
        },
      ];
      const result = calculate(p, library),
        drawing = await buildDrawing(p, library, result);
      const nodes = new Map(drawing.sheets.flatMap((s) => s.nodes).map((n) => [n.id, n]));
      expect(nodes.size).toBe(6);
      // On a small vertical sheet this complete horizontal sequence may paginate.
      for (const sheet of drawing.sheets) {
        const ids = ['src-1', 'ps-1', 'dec-1', 'external-ps', 'dim', 'downlight'].filter((id) =>
          sheet.nodes.some((n) => n.id === id),
        );
        for (let i = 1; i < ids.length; i++)
          expect(
            before(nodes.get(ids[i - 1]!)!, nodes.get(ids[i]!)!, flow),
            `${flow}: ${ids[i - 1]} -> ${ids[i]}`,
          ).toBe(true);
        for (const c of sheet.connections ?? []) {
          const both =
            sheet.nodes.some((n) => n.id === c.fromId) && sheet.nodes.some((n) => n.id === c.toId);
          if (both) {
            expect(c.reference).toBeUndefined();
            expect(c.fromContinuation || c.toContinuation).toBe(false);
          }
        }
      }
      if (flow === 'LR') expect(drawing.sheets).toHaveLength(1);
      expect(
        drawing.sheets
          .flatMap(flattenSheet)
          .some((x) => x.kind === 'text' && x.value.startsWith('CONT.')),
      ).toBe(false);
    }
  });

  it('keeps assigned loads inside the enclosure after supplies and controls, including save/reload', async () => {
    const p = demoProject(),
      library = seedLibrary();
    p.settings.showSchedules = false;
    p.equipment.forEach((e) => (e.enclosure = 'CAB-1'));
    p.loads[0]!.enclosure = 'CAB-1';
    const restored = ProjectSchema.parse(JSON.parse(JSON.stringify(p)));
    expect(restored.loads[0]!.enclosure).toBe('CAB-1');
    const drawing = await buildDrawing(restored, library, calculate(restored, library));
    const sheet = drawing.sheets.find((s) => s.nodes.some((n) => n.id === 'load-1'))!;
    const member = sheet.nodes.find((n) => n.id === 'load-1')!,
      decoder = sheet.nodes.find((n) => n.id === 'dec-1')!,
      supply = sheet.nodes.find((n) => n.id === 'ps-1')!;
    expect(before(supply, decoder, 'LR')).toBe(true);
    expect(before(decoder, member, 'LR')).toBe(true);
    const outlines = sheet.prims.filter(
      (p) => p.kind === 'rect' && p.layer === 'E-ANNO-ENCL' && intersects(p, member),
    );
    expect(outlines).toHaveLength(1);
    const outline = outlines[0]!;
    if (outline.kind === 'rect') {
      expect(member.x + member.width).toBeLessThan(outline.x + outline.width);
      expect(
        sheet.nodes
          .filter((n) => n.id.startsWith('load-') && n.id !== 'load-1')
          .every((n) => !intersects(outline, n)),
      ).toBe(true);
    }
  });

  it('orders DMX receivers along their chain and aligns each supply with its decoder', async () => {
    const p = demoProject(),
      library = seedLibrary();
    p.settings.showSchedules = false;
    const drawing = await buildDrawing(p, library, calculate(p, library));
    expect(drawing.sheets).toHaveLength(1);
    const sheet = drawing.sheets[0]!,
      find = (id: string) => sheet.nodes.find((n) => n.id === id)!;
    expect(find('dec-1').y).toBeGreaterThan(find('dec-2').y);
    expect(find('ps-1').y).toBeGreaterThan(find('ps-2').y);
    expect(find('dec-1').x).toBe(find('dec-2').x);
    expect(find('ps-1').x).toBe(find('ps-2').x);
    expect(
      sheet.connections!.every((c) => !c.reference && !c.fromContinuation && !c.toContinuation),
    ).toBe(true);
  });
});
