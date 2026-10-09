import { seedLayers } from '@ill/data/seeds';
import { flattenSheet, type Primitive, type Sheet } from '@ill/drawing/model';
import { fontEmSize } from '@ill/drawing/text';

export const escapeXml = (s: string) =>
  s
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
const n = (value: number) => Number(value.toFixed(6));
export type SvgOptions = {
  qa?: boolean;
  wireTags?: boolean;
  dmx?: boolean;
  monochrome?: boolean;
  interactive?: boolean;
  fontCss?: string;
  /** Written as the SVG's metadata, e.g. `ilLumenate System Designer`. */
  creator?: string;
};
export function serializeSvg(sheet: Sheet, options: SvgOptions = {}): string {
  const flat = flattenSheet(sheet);
  const body: string[] = [];
  function primitive(p: Primitive): string {
    const layer = seedLayers.layers.find((l) => l.name === p.layer)!;
    // A colour-coded sheet (the client diagram) keeps each primitive's own colour.
    const color =
      sheet.colored && p.color
        ? p.color
        : options.monochrome !== false && p.layer !== 'E-ANNO-QAFL'
          ? '#111111'
          : (p.color ?? layer.color);
    const weight = (p.lineweightMm ?? layer.lineweightMm) / 25.4;
    const dash = seedLayers.linetypes
      .find((l) => l.name === (p.linetype ?? layer.linetype))!
      .patternIn.map((v) => Math.max(0.005, Math.abs(v)));
    const style = `stroke="${color}" stroke-width="${n(weight)}" fill="none"${dash.length ? ` stroke-dasharray="${dash.map(n).join(' ')}"` : ''}`;
    const entity =
      options.interactive && p.entityId ? ` data-entity="${escapeXml(p.entityId)}"` : '';
    const attrs = `${style}${entity}`;
    const Y = (y: number) => n(sheet.heightIn - y);
    if (p.kind === 'line')
      return `<line x1="${n(p.from.x)}" y1="${Y(p.from.y)}" x2="${n(p.to.x)}" y2="${Y(p.to.y)}" ${attrs}/>`;
    if (p.kind === 'polyline' || p.kind === 'hatch')
      return `<${p.kind === 'hatch' || p.closed ? 'polygon' : 'polyline'} points="${p.points.map((v) => `${n(v.x)},${Y(v.y)}`).join(' ')}" ${p.kind === 'hatch' ? `fill="${color}"${entity}` : attrs}/>`;
    if (p.kind === 'rect')
      return `<rect x="${n(p.x)}" y="${Y(p.y + p.height)}" width="${n(p.width)}" height="${n(p.height)}" ${attrs}/>`;
    if (p.kind === 'filledPath') {
      const point = (v: { x: number; y: number }) => `${n(v.x)} ${Y(v.y)}`;
      const d = p.contours
        .map(
          (c) =>
            `M ${point(c.start)} ${c.segments
              .map((s) =>
                s.kind === 'line'
                  ? `L ${point(s.to)}`
                  : `C ${point(s.control1)} ${point(s.control2)} ${point(s.to)}`,
              )
              .join(' ')} Z`,
        )
        .join(' ');
      return `<path d="${d}" fill="${color}" fill-rule="nonzero"${entity}/>`;
    }
    if (p.kind === 'circle')
      return `<circle cx="${n(p.x)}" cy="${Y(p.y)}" r="${n(p.radius)}" ${attrs}/>`;
    if (p.kind === 'arc') {
      const a = (p.startDeg * Math.PI) / 180,
        b = (p.endDeg * Math.PI) / 180;
      const span = (((p.endDeg - p.startDeg) % 360) + 360) % 360;
      return `<path d="M ${n(p.x + p.radius * Math.cos(a))} ${Y(p.y + p.radius * Math.sin(a))} A ${n(p.radius)} ${n(p.radius)} 0 ${span > 180 ? 1 : 0} 0 ${n(p.x + p.radius * Math.cos(b))} ${Y(p.y + p.radius * Math.sin(b))}" ${attrs}/>`;
    }
    const anchor = p.hAlign === 'left' ? 'start' : p.hAlign === 'right' ? 'end' : 'middle';
    const y = p.y - (p.vAlign === 'top' ? p.heightIn : p.vAlign === 'middle' ? p.heightIn / 2 : 0);
    return `<g${entity}${p.rotation ? ` transform="rotate(-90 ${n(p.x)} ${Y(y)})"` : ''}>${p.value
      .split('\n')
      .map(
        (value, i) =>
          `<text x="${n(p.x)}" y="${Y(y - i * p.heightIn * 1.45)}" font-family="${sheet.fontFamily === 'RobotoCondensed' ? 'Roboto Condensed' : 'Arimo'}, Arial, sans-serif" font-size="${n(fontEmSize(p.heightIn, sheet.fontFamily))}" font-weight="${p.font === 'bold' ? 700 : 400}" text-anchor="${anchor}" fill="${color}" style="font-kerning:none;font-variant-ligatures:none">${escapeXml(value)}</text>`,
      )
      .join('')}</g>`;
  }
  // Fills first, so outlines and text on any layer stay on top of them.
  for (const fills of [true, false])
    for (const layer of seedLayers.layers) {
      if (!layer.export && !options.qa) continue;
      const prims = flat.filter(
        (p) =>
          p.layer === layer.name &&
          (p.kind === 'hatch') === fills &&
          (options.wireTags !== false || p.role !== 'wire-tag') &&
          (options.dmx !== false || p.role !== 'dmx'),
      );
      if (prims.length)
        body.push(`<g data-layer="${layer.name}">${prims.map(primitive).join('')}</g>`);
    }
  for (const image of sheet.images ?? [])
    body.push(
      `<image href="${escapeXml(image.src)}" x="${n(image.x)}" y="${n(sheet.heightIn - image.y - image.height)}" width="${n(image.width)}" height="${n(image.height)}" preserveAspectRatio="xMidYMid meet"/>`,
    );
  const metadata = options.creator
    ? `<metadata>${escapeXml(`Creator: ${options.creator}`)}</metadata>`
    : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(`${sheet.number} ${sheet.title}`)}" width="${sheet.widthIn}in" height="${sheet.heightIn}in" viewBox="0 0 ${sheet.widthIn} ${sheet.heightIn}" style="background:white">${metadata}${options.fontCss ? `<defs><style>${options.fontCss}</style></defs>` : ''}${body.join('')}</svg>`;
}
