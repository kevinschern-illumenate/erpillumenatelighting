import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PDFDocument } from '@cantoo/pdf-lib';
import DxfParser from 'dxf-parser';
import JSZip from 'jszip';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign, type DesignCheck } from '@ill/engine/designCheck';
import { DESIGN_AID_NOTE, dealerDataNote, riserProject, type RiserMeta } from '@ill/engine/riser';
import { DESIGNER_CREATOR, serializePdf } from '@ill/serializers/pdf/pdf';
import { serializeDxf, serializeDxfZip } from '@ill/serializers/dxf/dxf';
import { serializeSvg } from '@ill/serializers/svg';
import { buildDrawing } from './build';
import { flattenSheet, type Drawing } from './model';
import { DATA_BY_DEALER_TAG } from './labels';

/** The riser drawn from a design (WP-3.7), on the golden third-party case: a dealer fixture beside ours. */
const golden = resolve(import.meta.dirname, '../../../fixtures/golden');
const input = JSON.parse(readFileSync(resolve(golden, 'third-party-mixed.input.json'), 'utf8'));
const fonts = resolve(import.meta.dirname, '../../serializers/fonts');
const fontBytes = {
  regular: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Regular.ttf'))),
  bold: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Bold.ttf'))),
  name: 'Arimo' as const,
};
// A 1 × 1 PNG standing in for a dealer logo.
const LOGO =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

const meta: RiserMeta = {
  projectName: 'Harbor Lofts',
  projectNumber: 'ILL-PROJ-2026-00042',
  client: 'Bright Dealer Co',
  siteAddress: '12 Pier Rd',
  designer: 'Dana Dealer',
  checker: 'Avery Engineer',
  date: '2026-10-09',
  revision: 'A',
  stamp: 'PRELIMINARY',
  sheet: 'ANSI_B',
  approved: false,
};

function check(): DesignCheck {
  return checkDesign({
    design: input.design,
    products: input.products,
    lines: [],
    wires: input.wires,
    codeTables,
    limits: input.limits,
  });
}

async function draw(
  changes: Partial<RiserMeta> = {},
  logo = false,
): Promise<{ drawing: Drawing; texts: string[] }> {
  const result = check();
  const project = riserProject(result, { ...meta, ...changes });
  const drawing = await buildDrawing(
    project,
    result.library,
    result.result,
    logo ? { dealerLogo: { src: LOGO, widthPx: 400, heightPx: 100 } } : {},
  );
  const texts = drawing.sheets.flatMap((sheet) =>
    flattenSheet(sheet).flatMap((p) => (p.kind === 'text' ? [p.value] : [])),
  );
  return { drawing, texts };
}

describe('riser from a design', () => {
  it('fills the title block from the ERP and tags dealer data on the symbol and schedule', async () => {
    const { drawing, texts } = await draw();
    expect(drawing.sheets.every((sheet) => sheet.size === 'ANSI_B' && sheet.widthIn === 17)).toBe(
      true,
    );
    const all = texts.join('\n');
    for (const value of [
      'Harbor Lofts',
      'ILL-PROJ-2026-00042',
      'Bright Dealer Co',
      'Dana Dealer',
      'PRELIMINARY',
    ])
      expect(all).toContain(value);
    expect(all).not.toContain('Avery Engineer');
    // The dealer's fixture symbol and its LOAD SCHEDULE row both carry the tag.
    expect(
      texts.filter((value) => value.includes(DATA_BY_DEALER_TAG)).length,
    ).toBeGreaterThanOrEqual(2);
    expect(all).not.toContain('tp:e1other');
    expect(all).toContain('NEC 2023');
  });

  it('adds the design-aid note, and the dealer note only when a dealer entered data', () => {
    const project = riserProject(check(), meta);
    expect(project.generalNotes[0]).toBe(DESIGN_AID_NOTE);
    expect(project.generalNotes).toContain(dealerDataNote('Bright Dealer Co'));
    expect(project.revisions.at(-1)).toMatchObject({ rev: 'A', by: 'Dana Dealer' });
    const ours = check();
    ours.project = { ...ours.project, loads: ours.project.loads.filter((load) => !load.notes) };
    expect(riserProject(ours, meta).generalNotes).not.toContain(dealerDataNote('Bright Dealer Co'));
  });

  it('stamps REVIEWED BY ILLUMENATE and names the checker only on an approved revision', () => {
    const draft = riserProject(check(), { ...meta, stamp: 'REVIEWED BY ILLUMENATE' });
    expect(draft.meta.checker).toBe('');
    expect(draft.meta.stamp).toBe('PRELIMINARY');
    const approved = riserProject(check(), {
      ...meta,
      stamp: 'REVIEWED BY ILLUMENATE',
      approved: true,
    });
    expect([approved.meta.stamp, approved.meta.checker]).toEqual([
      'REVIEWED BY ILLUMENATE',
      'Avery Engineer',
    ]);
  });

  it('draws Letter sheets with the brand and dealer logos inside the title block', async () => {
    const { drawing } = await draw({ sheet: 'ANSI_A' }, true);
    for (const sheet of drawing.sheets) {
      expect([sheet.widthIn, sheet.heightIn]).toEqual([11, 8.5]);
      const [image] = sheet.images ?? [];
      expect(image).toBeDefined();
      expect(image!.x).toBeGreaterThanOrEqual(8.25);
      expect(image!.x + image!.width).toBeLessThanOrEqual(10.5);
      expect(image!.width / image!.height).toBeCloseTo(4);
      expect(flattenSheet(sheet).some((p) => p.kind === 'filledPath')).toBe(true);
    }
    const svg = serializeSvg(drawing.sheets[0]!, { creator: DESIGNER_CREATOR });
    expect(svg).toContain('<image href="data:image/png;base64,');
    expect(svg).toContain('<metadata>Creator: ilLumenate System Designer</metadata>');
  });

  it('embeds the System Designer as the PDF creator, with keywords and the logo', async () => {
    const { drawing } = await draw({}, true);
    const result = check();
    const bytes = await serializePdf(drawing, riserProject(result, meta), fontBytes, {
      creator: DESIGNER_CREATOR,
      keywords: ['design:SYSD-1', 'revision:A'],
    });
    const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
    expect(pdf.getCreator()).toBe('ilLumenate System Designer');
    expect(pdf.getTitle()).toBe('Harbor Lofts');
    expect(pdf.getKeywords()).toBe('design:SYSD-1 revision:A');
    expect(pdf.getPageCount()).toBe(drawing.sheets.length);
    expect(new TextDecoder('latin1').decode(bytes)).toContain('/Subtype /Image');
  });

  it('round-trips the DXF with its creator comment and no raster images', async () => {
    const { drawing, texts } = await draw({}, true);
    const dxf = serializeDxf([drawing.sheets[0]!], { creator: DESIGNER_CREATOR });
    expect(dxf.startsWith('999\r\nCreator: ilLumenate System Designer\r\n0\r\nSECTION')).toBe(true);
    expect(dxf).not.toContain('IMAGE');
    const parsed = new DxfParser().parseSync(dxf)!;
    const values = parsed.entities.flatMap((entity) =>
      'text' in entity ? [String(entity.text)] : [],
    );
    expect(values.some((value) => value.includes(DATA_BY_DEALER_TAG))).toBe(
      texts.some((value) => value.includes(DATA_BY_DEALER_TAG)),
    );
    expect(parsed.tables.layer.layers['E-ANNO-TTLB']).toBeDefined();
    const zip = await JSZip.loadAsync(
      await serializeDxfZip(drawing, {}, { creator: DESIGNER_CREATOR }),
    );
    const first = await zip.file(Object.keys(zip.files)[0]!)!.async('string');
    expect(first.startsWith('999\r\nCreator: ilLumenate System Designer')).toBe(true);
  });
});
