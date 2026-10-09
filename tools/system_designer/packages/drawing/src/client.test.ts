import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { inflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign } from '@ill/engine/designCheck';
import { riserProject, type RiserMeta } from '@ill/engine/riser';
import { serializePdf } from '@ill/serializers/pdf/pdf';
import { serializeSvg } from '@ill/serializers/svg';
import { buildDrawing } from './build';
import { PRODUCT_COLORS, WIRE_COLORS } from './client';
import { flattenSheet, type Drawing } from './model';
import type { DrawingOptions } from './options';

/** Single-line low-voltage wire on both styles, and the client diagram (colour, part numbers, schedule). */
const golden = resolve(import.meta.dirname, '../../../fixtures/golden');
const fonts = resolve(import.meta.dirname, '../../serializers/fonts');
const fontBytes = {
  regular: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Regular.ttf'))),
  bold: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Bold.ttf'))),
  name: 'Arimo' as const,
};
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

async function draw(name: string, options: DrawingOptions = {}) {
  const input = JSON.parse(readFileSync(resolve(golden, `${name}.input.json`), 'utf8'));
  const check = checkDesign({
    design: input.design,
    products: input.products,
    lines: [],
    wires: input.wires,
    codeTables,
    limits: input.limits,
  });
  const project = riserProject(check, meta);
  const drawing = await buildDrawing(project, check.library, check.result, options);
  return { drawing, project, result: check.result };
}
const texts = (drawing: Drawing, sheets = drawing.sheets) =>
  sheets.flatMap((sheet) =>
    flattenSheet(sheet).flatMap((p) => (p.kind === 'text' ? [p.value.replace(/\n/g, ' ')] : [])),
  );

describe('low-voltage wire', () => {
  it('draws a double-end feed as one line whose callout counts the conductors', async () => {
    const { drawing, result } = await draw('cove-24v-single');
    const lv = result.runs.filter((run) => run.type === 'class2-dc');
    expect(lv.length).toBeGreaterThan(1);
    const connections = drawing.sheets.flatMap((sheet) => sheet.connections ?? []);
    const drawnLv = connections.filter((c) => lv.some((run) => run.runId === c.runId));
    expect(drawnLv).toHaveLength(1);
    const callout = texts(drawing).find((value) => value.includes(`${lv.length} ×`));
    expect(callout).toMatch(/COND/);
    expect(callout).toContain(lv.map((run) => run.tag).join(', '));
    // The schedules still list every cable.
    const all = texts(drawing).join('\n');
    for (const run of lv) expect(all).toContain(run.tag);
  });
});

describe('client diagram', () => {
  const options: DrawingOptions = {
    style: 'client',
    loads: { 'load:a1linear:1:1': { type: 'linear', partNumber: 'SH01-30K-W-48IN' } },
    fixtureSchedule: [
      {
        type: 'A1',
        product: 'Linear Fixture',
        partNumber: 'SH01-30K-W-48IN',
        qty: '1',
        location: 'Kitchen',
      },
    ],
  };

  it('shows the fixture part number, simple wire names and the schedule page, with no engineering tables', async () => {
    const { drawing, result } = await draw('third-party-mixed', options);
    const diagrams = drawing.sheets.filter((sheet) => sheet.nodes.length);
    const onDiagram = texts(drawing, diagrams).join('\n');
    expect(onDiagram).toContain('SH01-30K-W-48IN');
    const tape = result.runs.find((run) => run.to.id === 'load:a1linear:1:1')!;
    expect(onDiagram).not.toContain(tape.to.tag + ' · ');
    expect(onDiagram).toMatch(/LV Wire · 18 AWG · 2 conductors/);
    expect(onDiagram).toContain('LINEAR FIXTURE');
    expect(onDiagram).not.toMatch(/VD \d|CL3R|DATA BY DEALER/);
    const schedule = drawing.sheets.find((sheet) => sheet.title === 'FIXTURE SCHEDULE & ORDERING')!;
    const page = texts(drawing, [schedule]).join('\n');
    for (const value of [
      'COLOR KEY',
      'FIXTURE SCHEDULE',
      'WIRE',
      'Linear fixtures',
      'LV Wire · 18 AWG',
    ])
      expect(page).toContain(value);
    expect(page).not.toMatch(/LOAD SCHEDULE|CABLE SCHEDULE|SYMBOL LEGEND|\$/);
    // The dealer's own product goes by its model, never the designer's id.
    expect(texts(drawing).join('\n')).not.toContain('tp:');
    expect(drawing.sheets.every((sheet) => sheet.colored)).toBe(true);
  });

  it('colours products and wires, and leaves the riser monochrome', async () => {
    const client = (await draw('third-party-mixed', options)).drawing;
    const prims = client.sheets.flatMap(flattenSheet);
    expect(prims.some((p) => p.color === PRODUCT_COLORS.linear.fill && p.kind === 'hatch')).toBe(
      true,
    );
    expect(prims.some((p) => p.color === WIRE_COLORS.lv.color && p.kind === 'polyline')).toBe(true);
    const svg = client.sheets.map((sheet) => serializeSvg(sheet)).join('');
    expect(svg).toContain(`stroke="${WIRE_COLORS.lv.color}"`);
    expect(svg).toContain(`fill="${PRODUCT_COLORS.linear.fill}"`);
    const riser = (await draw('third-party-mixed')).drawing;
    expect(riser.sheets.some((sheet) => sheet.colored)).toBe(false);
    const plain = riser.sheets.map((sheet) => serializeSvg(sheet)).join('');
    expect(plain).not.toContain(WIRE_COLORS.lv.color);
  });

  it('writes colour operators only into a colour-coded PDF', async () => {
    const { drawing, project } = await draw('third-party-mixed', options);
    const riser = await draw('third-party-mixed');
    // Every page content stream (the ones that open a layer), inflated; font streams are skipped.
    const decode = (bytes: Uint8Array) => {
      const raw = Buffer.from(bytes);
      const out: string[] = [];
      for (let at = raw.indexOf('stream\n'); at >= 0; at = raw.indexOf('stream\n', at + 1)) {
        const end = raw.indexOf('endstream', at);
        try {
          out.push(inflateSync(raw.subarray(at + 7, end)).toString('latin1'));
        } catch {
          out.push(raw.subarray(at + 7, end).toString('latin1'));
        }
      }
      return out.filter((stream) => stream.startsWith('/OC')).join('\n');
    };
    const client = decode(await serializePdf(drawing, project, fontBytes));
    const plain = decode(await serializePdf(riser.drawing, riser.project, fontBytes));
    expect(/ rg\n/.test(client)).toBe(true);
    expect(/ (rg|RG)\n/.test(plain)).toBe(false);
  });
});
