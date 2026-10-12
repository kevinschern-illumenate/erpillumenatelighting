import {
  PDFDocument,
  PDFName,
  appendBezierCurve,
  beginText,
  closePath,
  endMarkedContent,
  endText,
  fill,
  lineTo,
  moveTo,
  popGraphicsState,
  pushGraphicsState,
  rectangle,
  setDashPattern,
  setFillingGrayscaleColor,
  setFillingRgbColor,
  setFontAndSize,
  setLineWidth,
  setStrokingGrayscaleColor,
  setStrokingRgbColor,
  setTextMatrix,
  showText,
  stroke,
  type PDFOperator,
} from '@cantoo/pdf-lib';
import { seedLayers } from '@ill/data/seeds';
import { flattenSheet, type Drawing, type Primitive } from '@ill/drawing/model';
import type { Project } from '@ill/core-schemas/project';
import { embedFonts, type FontBytes } from './fonts';
import { createLayers } from './ocg';
import { fontEmSize } from '@ill/drawing/text';

function path(p: Exclude<Primitive, { kind: 'text' }>): PDFOperator[] {
  const pt = (x: number) => x * 72;
  if (p.kind === 'line')
    return [moveTo(pt(p.from.x), pt(p.from.y)), lineTo(pt(p.to.x), pt(p.to.y)), stroke()];
  if (p.kind === 'rect') return [rectangle(pt(p.x), pt(p.y), pt(p.width), pt(p.height)), stroke()];
  if (p.kind === 'filledPath')
    return [
      ...p.contours.flatMap((c) => [
        moveTo(pt(c.start.x), pt(c.start.y)),
        ...c.segments.map((s) =>
          s.kind === 'line'
            ? lineTo(pt(s.to.x), pt(s.to.y))
            : appendBezierCurve(
                pt(s.control1.x),
                pt(s.control1.y),
                pt(s.control2.x),
                pt(s.control2.y),
                pt(s.to.x),
                pt(s.to.y),
              ),
        ),
        closePath(),
      ]),
      fill(),
    ];
  if (p.kind === 'polyline' || p.kind === 'hatch')
    return [
      moveTo(pt(p.points[0]!.x), pt(p.points[0]!.y)),
      ...p.points.slice(1).map((v) => lineTo(pt(v.x), pt(v.y))),
      ...(p.kind === 'hatch' || p.closed ? [closePath()] : []),
      p.kind === 'hatch' ? fill() : stroke(),
    ];
  const start = p.kind === 'arc' ? p.startDeg : 0,
    end = p.kind === 'arc' ? p.endDeg : 360;
  const sweep = end > start ? end - start : end + 360 - start;
  const count = Math.ceil(sweep / 90);
  const step = ((sweep / count) * Math.PI) / 180;
  let a = (start * Math.PI) / 180;
  const ops = [moveTo(pt(p.x + p.radius * Math.cos(a)), pt(p.y + p.radius * Math.sin(a)))];
  for (let i = 0; i < count; i++) {
    const b = a + step,
      k = (4 / 3) * Math.tan((b - a) / 4),
      r = p.radius;
    ops.push(
      appendBezierCurve(
        pt(p.x + r * (Math.cos(a) - k * Math.sin(a))),
        pt(p.y + r * (Math.sin(a) + k * Math.cos(a))),
        pt(p.x + r * (Math.cos(b) + k * Math.sin(b))),
        pt(p.y + r * (Math.sin(b) - k * Math.cos(b))),
        pt(p.x + r * Math.cos(b)),
        pt(p.y + r * Math.sin(b)),
      ),
    );
    a = b;
  }
  if (p.kind === 'circle') ops.push(closePath());
  ops.push(stroke());
  return ops;
}
/** The riser generator's own name; the System Designer passes `DESIGNER_CREATOR` (plan D2). */
export const RISER_CREATOR = 'ilLumenate Lighting Riser Generator v1.2.0';
export const DESIGNER_CREATOR = 'ilLumenate System Designer';
export interface PdfOptions {
  creator?: string;
  /** Searchable keywords such as the design, revision and build hash. */
  keywords?: string[];
}
/** `#RRGGBB` as PDF colour components. */
const rgb = (hex: string): [number, number, number] => [
  parseInt(hex.slice(1, 3), 16) / 255,
  parseInt(hex.slice(3, 5), 16) / 255,
  parseInt(hex.slice(5, 7), 16) / 255,
];
const dataUrlBytes = (src: string) =>
  Uint8Array.from(atob(src.slice(src.indexOf(',') + 1)), (c) => c.charCodeAt(0));
export async function serializePdf(
  drawing: Drawing,
  project: Project,
  fontBytes: FontBytes,
  options: PdfOptions = {},
): Promise<Uint8Array> {
  const document = await PDFDocument.create({ updateMetadata: false });
  const fonts = await embedFonts(document, fontBytes);
  document.setTitle(project.meta.name);
  document.setAuthor(project.meta.designer);
  document.setSubject(project.meta.number);
  document.setCreator(options.creator ?? RISER_CREATOR);
  if (options.keywords?.length) document.setKeywords(options.keywords);
  document.setProducer('ilLumenate Lighting vector drawing model');
  const date = new Date(`${project.meta.date}T00:00:00Z`);
  document.setCreationDate(date);
  document.setModificationDate(date);
  const flattened = drawing.sheets.map(flattenSheet);
  const layers = seedLayers.layers.filter(
    (l) => l.export && flattened.some((ps) => ps.some((p) => p.layer === l.name)),
  );
  const layerStart = createLayers(
    document,
    layers.map((l) => l.name),
  );
  for (const [pageIndex, sheet] of drawing.sheets.entries()) {
    const page = document.addPage([sheet.widthIn * 72, sheet.heightIn * 72]);
    page.node.setFontDictionary(PDFName.of('MAIN'), fonts.main.ref);
    page.node.setFontDictionary(PDFName.of('BOLD'), fonts.bold.ref);
    // Fills first, so outlines and text on any layer stay on top of them.
    for (const fills of [true, false])
      for (const [index, layer] of layers.entries()) {
        const prims = flattened[pageIndex]!.filter(
          (p) => p.layer === layer.name && (p.kind === 'hatch') === fills,
        );
        if (fills && !prims.length) continue;
        page.pushOperators(
          layerStart(page, index),
          pushGraphicsState(),
          setStrokingGrayscaleColor(0),
          setFillingGrayscaleColor(0),
        );
        for (const p of prims) {
          // A colour-coded sheet (the client diagram) paints each primitive's own colour.
          if (sheet.colored) {
            const color = p.color ? rgb(p.color) : null;
            page.pushOperators(
              ...(color
                ? [setStrokingRgbColor(...color), setFillingRgbColor(...color)]
                : [setStrokingGrayscaleColor(0), setFillingGrayscaleColor(0)]),
            );
          }
          const pattern = seedLayers.linetypes
            .find((l) => l.name === (p.linetype ?? layer.linetype))!
            .patternIn.map((n) => Math.max(0.005, Math.abs(n)) * 72);
          page.pushOperators(
            setLineWidth(((p.lineweightMm ?? layer.lineweightMm) * 72) / 25.4),
            setDashPattern(pattern, 0),
          );
          if (p.kind !== 'text') {
            page.pushOperators(...path(p));
            continue;
          }
          const font = fonts[p.font],
            size = fontEmSize(p.heightIn, fontBytes.name) * 72;
          for (const [i, value] of p.value.split('\n').entries()) {
            if (!value) continue;
            const width = font.widthOfTextAtSize(value, size);
            const offset = p.hAlign === 'center' ? width / 2 : p.hAlign === 'right' ? width : 0;
            const baseY =
              (p.y -
                (p.vAlign === 'top' ? p.heightIn : p.vAlign === 'middle' ? p.heightIn / 2 : 0)) *
              72;
            const leading = p.heightIn * 72 * 1.45;
            const x = p.rotation === 90 ? p.x * 72 + i * leading : p.x * 72 - offset;
            const y = p.rotation === 90 ? baseY - offset : baseY - i * leading;
            page.pushOperators(
              beginText(),
              setFontAndSize(p.font === 'bold' ? 'BOLD' : 'MAIN', size),
              p.rotation === 90
                ? setTextMatrix(0, 1, -1, 0, x, y)
                : setTextMatrix(1, 0, 0, 1, x, y),
              showText(font.encodeText(value)),
              endText(),
            );
          }
        }
        page.pushOperators(popGraphicsState(), endMarkedContent());
      }
    for (const image of sheet.images ?? []) {
      const bytes = dataUrlBytes(image.src);
      const embedded = image.src.startsWith('data:image/png')
        ? await document.embedPng(bytes)
        : await document.embedJpg(bytes);
      page.drawImage(embedded, {
        x: image.x * 72,
        y: image.y * 72,
        width: image.width * 72,
        height: image.height * 72,
      });
    }
  }
  return document.save({ useObjectStreams: false, addDefaultPage: false });
}
