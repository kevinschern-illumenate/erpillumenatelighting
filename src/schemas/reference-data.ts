import { z } from 'zod';
import {
  AwgSchema,
  EditionSchema,
  IdSchema,
  NonnegativeSchema,
  PositiveSchema,
  ProvenanceSchema,
  SheetSizeSchema,
  TextSchema,
  uniqueList,
} from './common';

const CodeSourceSchema = z
  .object({
    standard: z.literal('NFPA 70'),
    edition: EditionSchema,
    table: IdSchema,
    reference: z.string().min(1),
    url: z.url(),
    verification: z.enum(['user-supplied-unverified', 'corroborated', 'user-verified']),
    supportingUrls: z.array(z.url()),
    checkedOn: z.iso.date(),
  })
  .strict();
const tableBase = {
  id: IdSchema,
  source: CodeSourceSchema,
  comment: z.string().min(1),
  material: z.literal('Cu'),
};
export const ResistanceTableSchema = z
  .object({
    ...tableBase,
    kind: z.literal('resistance'),
    units: z.literal('ohm/kft'),
    referenceTempC: z.literal(75),
    coating: z.literal('uncoated'),
    rows: uniqueList(
      z
        .object({ awg: AwgSchema, solid: PositiveSchema.optional(), stranded: PositiveSchema })
        .strict(),
      (r) => r.awg,
    ).min(1),
  })
  .strict();
export const AmpacityTableSchema = z
  .object({
    ...tableBase,
    kind: z.literal('ampacity'),
    units: z.literal('A'),
    ambientTempC: z.literal(30),
    maxCurrentCarryingConductors: z.literal(3),
    rows: uniqueList(
      z
        .object({
          awg: AwgSchema,
          at60C: PositiveSchema,
          at75C: PositiveSchema,
          at90C: PositiveSchema,
          smallConductorOcpdLimitA: PositiveSchema.optional(),
        })
        .strict()
        .refine(
          (r) => r.at60C <= r.at75C && r.at75C <= r.at90C,
          'Ampacity columns must be nondecreasing',
        ),
      (r) => r.awg,
    ).min(1),
  })
  .strict();
export const FixtureWireTableSchema = z
  .object({
    ...tableBase,
    kind: z.literal('fixture-wire'),
    units: z.literal('A'),
    applicationNote: z.string().min(1),
    rows: uniqueList(
      z.object({ awg: AwgSchema, ampacityA: PositiveSchema }).strict(),
      (r) => r.awg,
    ).min(1),
  })
  .strict();
export const EffectiveZTableSchema = z
  .object({
    ...tableBase,
    kind: z.literal('effective-z'),
    units: z.literal('ohm/kft'),
    referenceTempC: z.literal(75),
    frequencyHz: z.literal(60),
    powerFactor: z.literal(0.85),
    raceway: z.enum(['PVC', 'aluminum', 'steel']),
    status: z.enum(['unavailable', 'available']),
    rows: uniqueList(
      z.object({ awg: AwgSchema, effectiveZOhmPerKft: PositiveSchema }).strict(),
      (r) => r.awg,
    ),
  })
  .strict()
  .refine(
    (table) => (table.status === 'available' ? table.rows.length > 0 : table.rows.length === 0),
    'Unavailable impedance tables must be empty; available tables require values',
  );
export const CodeTableSchema = z.discriminatedUnion('kind', [
  ResistanceTableSchema,
  AmpacityTableSchema,
  FixtureWireTableSchema,
  EffectiveZTableSchema,
]);
export type CodeTable = z.infer<typeof CodeTableSchema>;
export const CodeTableLibrarySchema = uniqueList(CodeTableSchema, (t) => t.id);

export const LayerNameSchema = z.enum([
  'E-ANNO-TTLB',
  'E-ANNO-TEXT',
  'E-ANNO-SCHD',
  'E-ANNO-TAGS',
  'E-POWR-EQPM',
  'E-LITE-CTRL-EQPM',
  'E-LITE-FIXT',
  'E-POWR-WIRE-LV',
  'E-LITE-WIRE-CL2',
  'E-LITE-CTRL-DMX',
  'E-LITE-CTRL-SIGL',
  'E-LITE-CTRL-LUTR',
  'E-LITE-CTRL-SPI',
  'E-LITE-CTRL-WRLS',
  'E-ANNO-ENCL',
  'E-ANNO-QAFL',
]);
export const LinetypeSchema = z.enum([
  'Continuous',
  'DASHED',
  'DASHED2',
  'DASHDOT',
  'PHANTOM',
  'HIDDEN',
  'DOT',
]);
export const LayerSchema = z
  .object({
    name: LayerNameSchema,
    description: IdSchema,
    linetype: LinetypeSchema,
    lineweightMm: PositiveSchema,
    color: z.string().regex(/^#[0-9a-fA-F]{6}$/),
    aciColor: z.number().int().min(1).max(255),
    export: z.boolean(),
  })
  .strict()
  .refine(
    (layer) => layer.name !== 'E-ANNO-QAFL' || !layer.export,
    'QA layer must never be exported',
  );
export const LayerLibrarySchema = z
  .object({
    layers: uniqueList(LayerSchema, (l) => l.name),
    linetypes: uniqueList(
      z
        .object({
          name: LinetypeSchema,
          patternIn: z.array(z.number().finite()),
          description: IdSchema,
        })
        .strict(),
      (l) => l.name,
    ),
  })
  .strict()
  .superRefine((library, ctx) => {
    const names = new Set(library.layers.map((l) => l.name));
    if (LayerNameSchema.options.some((l) => !names.has(l)))
      ctx.addIssue({ code: 'custom', path: ['layers'], message: 'Required layer is missing' });
    const patterns = new Set(library.linetypes.map((l) => l.name));
    if (library.layers.some((l) => !patterns.has(l.linetype)))
      ctx.addIssue({
        code: 'custom',
        path: ['linetypes'],
        message: 'A layer references an undefined linetype',
      });
  });
const RegionSchema = z
  .object({
    x: NonnegativeSchema,
    y: NonnegativeSchema,
    width: PositiveSchema,
    height: PositiveSchema,
  })
  .strict();
const TitleFieldNameSchema = z.enum([
  'brandLogo',
  'project',
  'number',
  'client',
  'address',
  'sheetTitle',
  'sheetNumber',
  'date',
  'scale',
  'drawnBy',
  'checkedBy',
  'revisions',
  'stamp',
]);
export const TitleBlockSchema = z
  .object({
    id: IdSchema,
    sheetSize: SheetSizeSchema,
    widthIn: PositiveSchema,
    heightIn: PositiveSchema,
    coordinateSystem: z.literal('paper-inches-lower-left'),
    marginIn: PositiveSchema,
    border: RegionSchema,
    drawingArea: RegionSchema,
    titleBlock: RegionSchema,
    fields: uniqueList(
      z
        .object({
          name: TitleFieldNameSchema,
          label: z.string(),
          region: RegionSchema,
          textHeightIn: PositiveSchema.min(3 / 32),
          defaultValue: z.string().optional(),
        })
        .strict(),
      (f) => f.name,
    ),
    referenceSquare: RegionSchema,
    logoStatus: z.enum(['awaiting-user-svg', 'provided-vector']),
    textStandards: z
      .object({
        body: z.literal(0.09375),
        tags: z.literal(0.125),
        sectionTitle: z.literal(0.1875),
        sheetTitle: z.literal(0.25),
      })
      .strict(),
  })
  .strict()
  .superRefine((template, ctx) => {
    const inside = (a: z.infer<typeof RegionSchema>, b: z.infer<typeof RegionSchema>) =>
      a.x >= b.x &&
      a.y >= b.y &&
      a.x + a.width <= b.x + b.width + 1e-8 &&
      a.y + a.height <= b.y + b.height + 1e-8;
    const page = { x: 0, y: 0, width: template.widthIn, height: template.heightIn };
    for (const key of ['border', 'drawingArea', 'titleBlock', 'referenceSquare'] as const)
      if (!inside(template[key], page))
        ctx.addIssue({ code: 'custom', path: [key], message: 'Region exceeds the sheet' });
    for (const name of TitleFieldNameSchema.options)
      if (!template.fields.some((f) => f.name === name))
        ctx.addIssue({ code: 'custom', path: ['fields'], message: `Missing title field ${name}` });
    template.fields.forEach((field, index) => {
      if (!inside(field.region, template.titleBlock))
        ctx.addIssue({
          code: 'custom',
          path: ['fields', index],
          message: 'Field exceeds title-block strip',
        });
    });
    if (template.referenceSquare.width !== 1 || template.referenceSquare.height !== 1)
      ctx.addIssue({
        code: 'custom',
        path: ['referenceSquare'],
        message: 'CAD reference square must be exactly 1 × 1 inch',
      });
    const a = template.drawingArea,
      b = template.titleBlock;
    if (a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y)
      ctx.addIssue({
        code: 'custom',
        path: ['drawingArea'],
        message: 'Drawing area overlaps the title block',
      });
  });
export type TitleBlock = z.infer<typeof TitleBlockSchema>;
export const NotesLibrarySchema = uniqueList(
  z
    .object({
      id: IdSchema,
      text: TextSchema,
      classification: z.enum([
        'manufacturer-instructions',
        'coordination',
        'company-default',
        'code-verification',
      ]),
      source: ProvenanceSchema,
      reviewRequired: z.literal(true),
    })
    .strict(),
  (n) => n.id,
);
