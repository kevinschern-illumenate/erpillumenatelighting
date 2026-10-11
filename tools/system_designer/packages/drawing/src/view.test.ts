import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign } from '@ill/engine/designCheck';
import { riserProject, type RiserLayout, type RiserMeta } from '@ill/engine/riser';
import { serializeSvg } from '@ill/serializers/svg';
import { buildDrawing } from './build';
import { flattenSheet, type Drawing } from './model';
import { CLIENT_SECTIONS, RISER_SECTIONS, type DrawingOptions } from './options';

/** The view controls carried over from the standalone riser's Drawing page (hide details, schedules, flow). */
const golden = resolve(import.meta.dirname, '../../../fixtures/golden');
const input = JSON.parse(readFileSync(resolve(golden, 'third-party-mixed.input.json'), 'utf8'));

const meta: RiserMeta = {
  projectName: 'Harbor Lofts',
  projectNumber: 'ILL-PROJ-2026-00042',
  client: 'Bright Dealer Co',
  siteAddress: '12 Pier Rd',
  designer: 'Dana Dealer',
  checker: '',
  date: '2026-10-09',
  revision: 'A',
  stamp: 'PRELIMINARY',
  sheet: 'ANSI_B',
  approved: false,
};

async function draw(options: DrawingOptions = {}, layout?: RiserLayout): Promise<Drawing> {
  const check = checkDesign({
    design: input.design,
    products: input.products,
    lines: [],
    wires: input.wires,
    codeTables,
    limits: input.limits,
  });
  return buildDrawing(riserProject(check, { ...meta, layout }), check.library, check.result, options);
}

const prims = (drawing: Drawing) => drawing.sheets.flatMap(flattenSheet);
const texts = (drawing: Drawing) => prims(drawing).flatMap((p) => (p.kind === 'text' ? [p.value] : []));

describe('drawing view', () => {
  it('hides wire labels, model lines, tape lengths and card ratings without moving the devices', async () => {
    const full = await draw();
    const bare = await draw({ view: { wireLabels: false, models: false, lengths: false, ratings: false } });
    // Placed on the sheet itself; card attributes are flattened as annotations too.
    const placed = (drawing: Drawing, role: string) =>
      drawing.sheets.some((sheet) => sheet.prims.some((p) => p.role === role));
    for (const role of ['wire-tag', 'model', 'annotation']) {
      expect(placed(full, role), role).toBe(true);
      expect(placed(bare, role), role).toBe(false);
    }
    // A card's wattage, not a schedule's.
    const watts = (drawing: Drawing) =>
      prims(drawing).some((p) => p.kind === 'text' && p.entityId && / W$/.test(p.value));
    expect(watts(full)).toBe(true);
    expect(watts(bare)).toBe(false);
    expect(bare.sheets[0]!.nodes).toEqual(full.sheets[0]!.nodes);
    // Every serializer draws the same sheet, so a download matches the preview.
    const tag = full.sheets[0]!.prims.find((p) => p.role === 'wire-tag');
    const line = tag?.kind === 'text' ? tag.value.split('\n')[0]! : '';
    expect(line).not.toBe('');
    expect(serializeSvg(full.sheets[0]!)).toContain(`>${line}<`);
    expect(serializeSvg(bare.sheets[0]!)).not.toContain(`>${line}<`);
  });

  it('leaves off the schedule sections a dealer hides, and every schedule page when all are hidden', async () => {
    const full = await draw();
    expect(texts(full)).toContain('BILL OF MATERIALS');
    const some = await draw({ view: { hide: ['BILL OF MATERIALS', 'SYMBOL LEGEND'] } });
    expect(texts(some)).not.toContain('BILL OF MATERIALS');
    expect(texts(some)).not.toContain('SYMBOL LEGEND');
    expect(texts(some)).toContain('WIRE SCHEDULE');
    const none = await draw({ view: { hide: [...RISER_SECTIONS] } });
    expect(none.sheets.every((sheet) => sheet.nodes.length)).toBe(true);
    expect(texts(none)).not.toContain('LINE LEGEND');
  });

  it('gives the diagrams the whole sheet without schedules and draws power top to bottom on request', async () => {
    const off = await draw({}, { schedules: false });
    expect(texts(off)).not.toContain('WIRE SCHEDULE');
    const down = await draw({}, { flow: 'TB' });
    const across = await draw();
    expect(down.sheets[0]!.nodes).not.toEqual(across.sheets[0]!.nodes);
  });

  it('drops the client schedule page when every section is hidden', async () => {
    const page = await draw({ style: 'client' });
    expect(page.sheets.some((sheet) => sheet.title === 'FIXTURE SCHEDULE & ORDERING')).toBe(true);
    const none = await draw({ style: 'client', view: { hide: [...CLIENT_SECTIONS] } });
    expect(none.sheets.some((sheet) => sheet.title === 'FIXTURE SCHEDULE & ORDERING')).toBe(false);
    expect(none.sheets.length).toBe(page.sheets.length - 1);
  });
});
