import { describe, expect, it, beforeAll } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  PDFDocument,
  PDFArray,
  PDFRawStream,
  decodePDFRawStream,
  PDFName,
  PDFDict,
  PDFString,
} from '@cantoo/pdf-lib';
import DxfParser from 'dxf-parser';
import JSZip from 'jszip';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { calculate } from '../engine/calculate';
import { buildDrawing } from '../drawing/build';
import { flattenSheet, text, type Drawing, type Sheet } from '../drawing/model';
import { serializePdf } from './pdf/pdf';
import { serializeDxf, serializeDxfZip } from './dxf/dxf';

const project = demoProject();
project.meta.date = '2026-09-24';
const library = seedLibrary();
const result = calculate(project, library);
const fonts = {
  regular: new Uint8Array(readFileSync('public/fonts/Arimo-Regular.ttf')),
  bold: new Uint8Array(readFileSync('public/fonts/Arimo-Bold.ttf')),
};
let drawing: Drawing;
beforeAll(async () => {
  drawing = await buildDrawing(project, library, result);
});
describe('shared geometry exporters', () => {
  it('exports arcs, solid hatches, rotated paragraphs and condensed-font references', async () => {
    const sheet: Sheet = {
      id: 'primitives',
      number: 'P-1',
      title: 'Primitives',
      size: 'ANSI_B',
      widthIn: 17,
      heightIn: 11,
      fontFamily: 'RobotoCondensed',
      nodes: [],
      layoutWarnings: [],
      blocks: [],
      prims: [
        {
          kind: 'hatch',
          layer: 'E-POWR-EQPM',
          points: [
            { x: 1, y: 1 },
            { x: 2, y: 1 },
            { x: 2, y: 2 },
            { x: 1, y: 2 },
          ],
        },
        { kind: 'arc', layer: 'E-POWR-EQPM', x: 4, y: 4, radius: 1, startDeg: 300, endDeg: 30 },
        { kind: 'circle', layer: 'E-POWR-EQPM', x: 7, y: 4, radius: 1 },
        { ...text('Rotated (café) \\ literal', 6, 6), rotation: 90, hAlign: 'center' },
        { ...text('Long paragraph '.repeat(40), 8, 8), rotation: 90, multiline: true },
      ],
    };
    const doc = new DxfParser().parseSync(serializeDxf([sheet]))!;
    // dxf-parser does not implement HATCH; assert its boundary/solid records separately.
    expect(doc.entities.map((e) => e.type)).toEqual(['ARC', 'CIRCLE', 'TEXT', 'MTEXT']);
    expect(serializeDxf([sheet])).toContain('\r\nHATCH\r\n');
    expect(serializeDxf([sheet])).toContain('\r\n2\r\nSOLID\r\n70\r\n1\r\n');
    expect(serializeDxf([sheet])).toContain('RobotoCondensed-Regular.ttf');
    expect(serializeDxf([sheet])).toContain('\\U+00E9');
    const special = { ...drawing, sheets: [sheet] };
    const zip = await JSZip.loadAsync(
      await serializeDxfZip(special, {
        'RobotoCondensed-Regular.ttf': new Uint8Array([1, 2]),
        'OFL-RobotoCondensed.txt': 'Test license',
      }),
    );
    expect(zip.file('fonts/RobotoCondensed-Regular.ttf')).not.toBeNull();
    const bytes = await serializePdf(special, project, {
      regular: new Uint8Array(readFileSync('public/fonts/RobotoCondensed-Regular.ttf')),
      bold: new Uint8Array(readFileSync('public/fonts/RobotoCondensed-Bold.ttf')),
      name: 'RobotoCondensed',
    });
    expect((await PDFDocument.load(bytes)).getPages()[0]!.getSize()).toEqual({
      width: 1224,
      height: 792,
    });
  });
  it('embeds full named fonts, real OCGs, whole text strings and 1-inch geometry deterministically', async () => {
    const bytes = await serializePdf(drawing, project, fonts);
    expect(bytes).toEqual(await serializePdf(drawing, project, fonts));
    const doc = await PDFDocument.load(bytes, { updateMetadata: false });
    expect(doc.getPageCount()).toBe(drawing.sheets.length);
    const properties = doc.catalog.lookup(PDFName.of('OCProperties'), PDFDict);
    const groups = properties.lookup(PDFName.of('OCGs'), PDFArray);
    const names = groups
      .asArray()
      .map((ref) =>
        doc.context.lookup(ref, PDFDict).lookup(PDFName.of('Name'), PDFString).decodeText(),
      );
    expect(names).toContain('E-LITE-CTRL-DMX');
    expect(names).not.toContain('E-ANNO-QAFL');
    for (const [i, page] of doc.getPages().entries()) {
      expect(page.getSize()).toEqual({
        width: drawing.sheets[i]!.widthIn * 72,
        height: drawing.sheets[i]!.heightIn * 72,
      });
      const contents = page.node.Contents() as PDFArray;
      const text = contents
        .asArray()
        .map((ref) =>
          Buffer.from(
            decodePDFRawStream(doc.context.lookup(ref) as PDFRawStream).decode(),
          ).toString('latin1'),
        )
        .join('\n');
      expect(text).toContain('36 36 72 72 re');
      expect(text).toContain('/OC /OC0 BDC');
      expect(text).not.toMatch(/\bTJ\b|\bTc\b|\bTw\b|\bW\*?\s*\n|\bDo\b/);
      const expected = flattenSheet(drawing.sheets[i]!)
        .filter((p) => p.kind === 'text' && p.layer !== 'E-ANNO-QAFL')
        .flatMap((p) => (p.kind === 'text' ? p.value.split('\n').filter(Boolean) : [])).length;
      expect((text.match(/ Tj/g) ?? []).length).toBe(expected);
    }
    const raw = Buffer.from(bytes).toString('latin1');
    expect(raw).toContain('/BaseFont /Arimo-Regular');
    expect(raw).toContain('/FontFile2');
    expect(raw).not.toContain('/Subtype /Image');
    if (process.env.WRITE_EXAMPLES === '1') {
      const path = resolve('../../work/export-check');
      mkdirSync(path, { recursive: true });
      writeFileSync(resolve(path, 'example-riser.pdf'), bytes);
      writeFileSync(resolve(path, 'drawing.json'), JSON.stringify(drawing));
      writeFileSync(resolve(path, 'example-library.json'), JSON.stringify(library, null, 2));
      writeFileSync(resolve(path, 'engineering-results.json'), JSON.stringify(result, null, 2));
      writeFileSync(
        resolve(path, 'example.riser.json'),
        JSON.stringify({ ...project, wireTagMap: result.wireTagMap }, null, 2),
      );
    }
  }, 20000);
  it('round-trips DXF layers, symbols, attributes, inch units and tiled sheet offsets', () => {
    const value = serializeDxf(drawing.sheets);
    expect(value).toBe(serializeDxf(drawing.sheets));
    const doc = new DxfParser().parseSync(value)!;
    expect(doc.header.$INSUNITS).toBe(1);
    expect(doc.header.$MEASUREMENT).toBe(0);
    expect(doc.header.$LTSCALE).toBe(1);
    expect(doc.tables.layer.layers).toHaveProperty('E-LITE-CTRL-DMX');
    expect(doc.tables.layer.layers).not.toHaveProperty('E-ANNO-QAFL');
    const inserts = doc.entities.filter((e) => e.type === 'INSERT');
    const count = drawing.sheets.flatMap((s) => s.prims.filter((p) => p.kind === 'block')).length;
    expect(inserts.length).toBe(count);
    expect(value.match(/\r\nATTRIB\r\n/g)?.length).toBe(count * 8);
    expect(value).toContain('\r\nATTDEF\r\n');
    expect(value).toContain('arialbd.ttf');
    expect(value).toContain('E-ANNO-TTLB');
    expect(doc.entities.filter((e) => e.type === 'LWPOLYLINE').length).toBeGreaterThan(
      result.runs.length,
    );
    const modelSymbols = drawing.sheets.flatMap((s) =>
      s.prims.filter((p) => p.kind === 'block').map((p) => p.symbolId),
    );
    for (const id of modelSymbols) expect(doc.blocks).toHaveProperty(id);
    const rects = doc.entities.filter((e) => e.type === 'LWPOLYLINE') as unknown as {
      vertices: { x: number; y: number }[];
    }[];
    const refs = rects.filter(
      (e) =>
        e.vertices.length === 4 &&
        Math.abs(e.vertices[1]!.x - e.vertices[0]!.x - 1) < 1e-8 &&
        Math.abs(e.vertices[2]!.y - e.vertices[1]!.y - 1) < 1e-8,
    );
    expect(refs.length).toBe(drawing.sheets.length);
    if (drawing.sheets.length > 1)
      expect(refs[1]!.vertices[0]!.x - refs[0]!.vertices[0]!.x).toBe(38);
    if (process.env.WRITE_EXAMPLES === '1') {
      const path = resolve('../../work/export-check');
      mkdirSync(path, { recursive: true });
      writeFileSync(resolve(path, 'example-riser-tiled.dxf'), value);
    }
  });
  it('writes one deterministic DXF per sheet in a ZIP', async () => {
    const bytes = await serializeDxfZip(drawing);
    expect(bytes).toEqual(await serializeDxfZip(drawing));
    const zip = await JSZip.loadAsync(bytes);
    expect(Object.keys(zip.files)).toHaveLength(drawing.sheets.length);
    for (const entry of Object.values(zip.files))
      expect(new DxfParser().parseSync(await entry.async('string'))?.header.$INSUNITS).toBe(1);
    if (process.env.WRITE_EXAMPLES === '1') {
      const path = resolve('../../work/export-check');
      mkdirSync(path, { recursive: true });
      writeFileSync(resolve(path, 'example-riser-dxf.zip'), bytes);
      for (const sheet of drawing.sheets)
        writeFileSync(resolve(path, `${sheet.number}.dxf`), serializeDxf([sheet]));
    }
  });
});
