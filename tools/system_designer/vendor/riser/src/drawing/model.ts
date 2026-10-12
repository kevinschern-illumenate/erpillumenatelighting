import { z } from 'zod';
import { LayerNameSchema, LinetypeSchema } from '../schemas/reference-data';
import { SheetSizeSchema } from '../schemas/common';

export const PointSchema = z.object({ x: z.number().finite(), y: z.number().finite() });
export const ContourSchema = z.object({
  start: PointSchema,
  segments: z
    .array(
      z.discriminatedUnion('kind', [
        z.object({ kind: z.literal('line'), to: PointSchema }),
        z.object({
          kind: z.literal('cubic'),
          control1: PointSchema,
          control2: PointSchema,
          to: PointSchema,
        }),
      ]),
    )
    .min(1),
});
const base = {
  layer: LayerNameSchema,
  lineweightMm: z.number().positive().optional(),
  linetype: LinetypeSchema.optional(),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{6}$/)
    .optional(),
  entityId: z.string().optional(),
  role: z
    .enum([
      'wire-tag',
      'dmx',
      'model',
      'annotation',
      'wire',
      'terminal',
      'continuation',
      'continuation-label',
    ])
    .optional(),
  runId: z.string().optional(),
};
export const TextSchema = z.object({
  ...base,
  kind: z.literal('text'),
  x: z.number(),
  y: z.number(),
  value: z.string(),
  heightIn: z.number().min(3 / 32),
  font: z.enum(['main', 'bold']),
  rotation: z.union([z.literal(0), z.literal(90)]),
  hAlign: z.enum(['left', 'center', 'right']),
  vAlign: z.enum(['bottom', 'middle', 'top']),
  multiline: z.boolean().optional(),
});
export const PrimitiveSchema = z.discriminatedUnion('kind', [
  z.object({ ...base, kind: z.literal('line'), from: PointSchema, to: PointSchema }),
  z.object({
    ...base,
    kind: z.literal('polyline'),
    points: z.array(PointSchema).min(2),
    closed: z.boolean().optional(),
  }),
  z.object({
    ...base,
    kind: z.literal('rect'),
    x: z.number(),
    y: z.number(),
    width: z.number().positive(),
    height: z.number().positive(),
  }),
  z.object({
    ...base,
    kind: z.literal('circle'),
    x: z.number(),
    y: z.number(),
    radius: z.number().positive(),
  }),
  z.object({
    ...base,
    kind: z.literal('arc'),
    x: z.number(),
    y: z.number(),
    radius: z.number().positive(),
    startDeg: z.number(),
    endDeg: z.number(),
  }),
  z.object({ ...base, kind: z.literal('hatch'), points: z.array(PointSchema).min(3) }),
  z.object({ ...base, kind: z.literal('filledPath'), contours: z.array(ContourSchema).min(1) }),
  TextSchema,
]);
export const AttributeSchema = z.object({
  tag: z.string(),
  default: z.string(),
  visible: z.boolean(),
  x: z.number(),
  y: z.number(),
  height: z.number().min(3 / 32),
  hAlign: z.enum(['left', 'center', 'right']).default('left'),
});
export const SymbolSchema = z.object({
  id: z.string(),
  label: z.string(),
  widthIn: z.number().positive(),
  heightIn: z.number().positive(),
  prims: z.array(PrimitiveSchema),
  ports: z.array(
    z.object({
      name: z.string(),
      side: z.enum(['W', 'E', 'N', 'S']),
      offset: z.number().nonnegative(),
    }),
  ),
  attributes: z.array(AttributeSchema),
});
export const BlockRefSchema = z.object({
  ...base,
  kind: z.literal('block'),
  symbolId: z.string(),
  x: z.number(),
  y: z.number(),
  rotation: z.union([z.literal(0), z.literal(90)]),
  scale: z.literal(1),
  attributes: z.record(z.string(), z.string()),
});
export const SheetSchema = z.object({
  id: z.string(),
  number: z.string(),
  title: z.string(),
  size: SheetSizeSchema,
  fontFamily: z.enum(['Arimo', 'RobotoCondensed']).optional(),
  widthIn: z.number(),
  heightIn: z.number(),
  prims: z.array(z.union([PrimitiveSchema, BlockRefSchema])),
  blocks: z.array(SymbolSchema),
  nodes: z.array(
    z.object({
      id: z.string(),
      x: z.number(),
      y: z.number(),
      width: z.number(),
      height: z.number(),
      pinned: z.boolean(),
    }),
  ),
  layoutWarnings: z.array(z.string()),
  connections: z
    .array(
      z.object({
        runId: z.string(),
        fromId: z.string(),
        toId: z.string(),
        fromPort: z.string(),
        toPort: z.string(),
        reference: z.string().optional(),
        fromContinuation: z.boolean().optional(),
        toContinuation: z.boolean().optional(),
        points: z.array(PointSchema).min(2),
      }),
    )
    .optional(),
});
export const DrawingSchema = z.object({
  sheets: z.array(SheetSchema),
  elapsedMs: z.number().nonnegative(),
  warnings: z.array(z.string()),
});
export type Point = z.infer<typeof PointSchema>;
export type Contour = z.infer<typeof ContourSchema>;
export type Primitive = z.infer<typeof PrimitiveSchema>;
export type TextPrim = z.infer<typeof TextSchema>;
export type BlockRef = z.infer<typeof BlockRefSchema>;
export type SymbolDef = z.infer<typeof SymbolSchema>;
export type Sheet = z.infer<typeof SheetSchema>;
export type Drawing = z.infer<typeof DrawingSchema>;
export type LayerName = z.infer<typeof LayerNameSchema>;
export function text(
  value: string,
  x: number,
  y: number,
  heightIn = 3 / 32,
  layer: LayerName = 'E-ANNO-TEXT',
  font: 'main' | 'bold' = 'main',
): TextPrim {
  return {
    kind: 'text',
    value,
    x,
    y,
    heightIn,
    layer,
    font,
    rotation: 0,
    hAlign: 'left',
    vAlign: 'bottom',
  };
}
export function line(x1: number, y1: number, x2: number, y2: number, layer: LayerName): Primitive {
  return { kind: 'line', from: { x: x1, y: y1 }, to: { x: x2, y: y2 }, layer };
}
export function symbolPort(symbol: SymbolDef, name: string): Point {
  const port = symbol.ports.find((p) => p.name === name) ?? symbol.ports[0]!;
  return port.side === 'W'
    ? { x: 0, y: port.offset }
    : port.side === 'E'
      ? { x: symbol.widthIn, y: port.offset }
      : port.side === 'N'
        ? { x: port.offset, y: symbol.heightIn }
        : { x: port.offset, y: 0 };
}
export function translate(prim: Primitive, dx: number, dy: number, rotate = 0): Primitive {
  const point = (p: Point): Point =>
    rotate === 90 ? { x: dx - p.y, y: dy + p.x } : { x: dx + p.x, y: dy + p.y };
  if (prim.kind === 'line') return { ...prim, from: point(prim.from), to: point(prim.to) };
  if (prim.kind === 'filledPath')
    return {
      ...prim,
      contours: prim.contours.map((c) => ({
        start: point(c.start),
        segments: c.segments.map((s) =>
          s.kind === 'line'
            ? { ...s, to: point(s.to) }
            : {
                ...s,
                to: point(s.to),
                control1: point(s.control1),
                control2: point(s.control2),
              },
        ),
      })),
    };
  if (prim.kind === 'polyline' || prim.kind === 'hatch')
    return { ...prim, points: prim.points.map(point) };
  if (prim.kind === 'rect' && rotate === 90)
    return {
      kind: 'polyline',
      layer: prim.layer,
      entityId: prim.entityId,
      points: [
        { x: prim.x, y: prim.y },
        { x: prim.x + prim.width, y: prim.y },
        { x: prim.x + prim.width, y: prim.y + prim.height },
        { x: prim.x, y: prim.y + prim.height },
      ].map(point),
      closed: true,
    };
  const p = point(prim);
  if (prim.kind === 'arc')
    return { ...prim, ...p, startDeg: prim.startDeg + rotate, endDeg: prim.endDeg + rotate };
  if (prim.kind === 'text') return { ...prim, ...p, rotation: rotate === 90 ? 90 : prim.rotation };
  return { ...prim, ...p };
}
export function flattenSheet(sheet: Sheet): Primitive[] {
  return sheet.prims.flatMap((prim): Primitive[] => {
    if (prim.kind !== 'block') return [prim];
    const symbol = sheet.blocks.find((b) => b.id === prim.symbolId);
    if (!symbol) throw new Error(`Missing symbol ${prim.symbolId}`);
    return [
      ...symbol.prims.map((p) =>
        translate({ ...p, entityId: prim.entityId }, prim.x, prim.y, prim.rotation),
      ),
      ...symbol.attributes
        .filter((a) => a.visible && (prim.attributes[a.tag] ?? a.default))
        .map((a) =>
          translate(
            {
              ...text(
                prim.attributes[a.tag] ?? a.default,
                a.x,
                a.y,
                a.height,
                'E-ANNO-TAGS',
                a.tag === 'TAG' ? 'bold' : 'main',
              ),
              hAlign: a.hAlign,
              entityId: prim.entityId,
              role: a.tag === 'DMX_ADDR' ? ('dmx' as const) : ('annotation' as const),
            },
            prim.x,
            prim.y,
            prim.rotation,
          ),
        ),
    ];
  });
}
