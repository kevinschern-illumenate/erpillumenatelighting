import { z } from 'zod';
import {
  AwgSchema,
  CountSchema,
  EditionSchema,
  EnvironmentSchema,
  EquipmentCategorySchema,
  IdSchema,
  NonnegativeSchema,
  PercentSchema,
  PortRefSchema,
  PositiveSchema,
  ProtocolSchema,
  SheetSizeSchema,
  TextSchema,
  uniqueList,
} from './common';
import { CatalogSpecOverridesSchema } from './catalog';

export const ProjectMetaSchema = z
  .object({
    name: z.string().max(160),
    number: z.string().max(80),
    client: z.string().max(160),
    siteAddress: z.string().max(300),
    designer: z.string().max(100),
    checker: z.string().max(100),
    date: z.iso.date(),
    brand: z.enum(['illumenate', '206']),
    sheetPrefix: z.string().min(1).max(12),
    stamp: z.enum(['NONE', 'FOR REFERENCE', 'NOT FOR CONSTRUCTION', 'PRELIMINARY']),
  })
  .strict();
export const ProjectSettingsSchema = z
  .object({
    necEdition: EditionSchema.default('2023'),
    terminationTempC: z.union([z.literal(60), z.literal(75), z.literal(90)]).default(75),
    vdTargetLineVoltagePct: PositiveSchema.max(100).default(3),
    vdTargetLowVoltagePct: PositiveSchema.max(100).default(3),
    vdTargetLandscapePct: PositiveSchema.max(100).default(5),
    vdMethod: z.enum(['lumped-at-end', 'distributed']).default('lumped-at-end'),
    acVdMethod: z.enum(['dc-resistance', 'effective-z']).default('dc-resistance'),
    psuDeratePct: PositiveSchema.max(100).default(80),
    continuousLoadFactor: z.number().finite().min(1).default(1.25),
    breakerLoadLimitPct: PositiveSchema.max(100).default(80),
    tapeLengthMarginPct: PercentSchema.default(0),
    minAwgLineVoltage: AwgSchema.default('12'),
    dmxMaxUnitLoads: PositiveSchema.default(32),
    dmxMaxLengthFt: PositiveSchema.default(1000),
    spiMaxDataFt: PositiveSchema.default(15),
    units: z.enum(['ft', 'm']).default('ft'),
    drawingFont: z.enum(['Arimo', 'RobotoCondensed']).default('Arimo'),
    showSchedules: z.boolean().default(true),
    sheet: z
      .object({ size: SheetSizeSchema.default('ARCH_D'), flow: z.enum(['LR', 'TB']).default('LR') })
      .strict()
      .default({ size: 'ARCH_D', flow: 'LR' }),
    wireWastePct: PercentSchema.default(10),
    dmxAutoPatchRoundTo: CountSchema.max(512).default(1),
    wireLabelTemplate: z
      .string()
      .min(1)
      .max(300)
      .default('{tag} · {wireLabel} · {lengthFt} ft · VD {vdPct}%'),
    parallelConductorPolicy: z.enum(['manual-review-required']).default('manual-review-required'),
  })
  .strict();
export type ProjectSettings = z.infer<typeof ProjectSettingsSchema>;

export const SourceSchema = z
  .object({
    id: IdSchema,
    tag: IdSchema,
    panel: IdSchema,
    circuit: IdSchema,
    voltage: z.union([
      z.literal(120),
      z.literal(208),
      z.literal(240),
      z.literal(277),
      z.literal(347),
      z.literal(480),
    ]),
    phase: z.enum(['1PH', '3PH']),
    breakerA: PositiveSchema,
    poles: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    switching: z
      .enum(['none', 'relay', 'phase-forward', 'phase-reverse', '0-10V', 'lutron-module'])
      .optional(),
    notes: TextSchema.optional(),
  })
  .strict();
export type Source = z.infer<typeof SourceSchema>;
export const EquipmentSchema = z
  .object({
    id: IdSchema,
    tag: IdSchema,
    catalogId: IdSchema,
    category: EquipmentCategorySchema,
    qty: CountSchema,
    location: z.string().min(1).max(300),
    enclosure: IdSchema.optional(),
    fedFrom: PortRefSchema,
    feedLengthFt: NonnegativeSchema,
    controlFrom: PortRefSchema.optional(),
    controlLengthFt: NonnegativeSchema.optional(),
    chainOrder: z.number().int().nonnegative().optional(),
    dmx: z
      .object({
        universe: CountSchema.max(63999),
        startAddress: z.union([CountSchema.max(512), z.literal('auto')]),
        terminatorPresent: z.boolean().optional(),
      })
      .strict()
      .optional(),
    env: EnvironmentSchema,
    specOverrides: CatalogSpecOverridesSchema.optional(),
    notes: TextSchema.optional(),
  })
  .strict()
  .superRefine((eq, ctx) => {
    if (eq.controlFrom && eq.controlLengthFt === undefined)
      ctx.addIssue({
        code: 'custom',
        path: ['controlLengthFt'],
        message: 'Control references require a cable/link length, including zero for no cable',
      });
    if (!eq.controlFrom && eq.controlLengthFt !== undefined)
      ctx.addIssue({
        code: 'custom',
        path: ['controlFrom'],
        message: 'Control length requires a control reference',
      });
  });
export type Equipment = z.infer<typeof EquipmentSchema>;
export const LoadSchema = z
  .object({
    id: IdSchema,
    typeTag: IdSchema,
    zone: z.string().max(300),
    enclosure: IdSchema.optional(),
    catalogId: IdSchema,
    qty: CountSchema.optional(),
    lengthFt: PositiveSchema.optional(),
    fedFrom: PortRefSchema,
    homeRunLengthFt: NonnegativeSchema,
    interFixtureLengthFt: NonnegativeSchema.optional(),
    feedMethod: z.enum(['end', 'double-end', 'center', 'multi-feed']),
    feeds: CountSchema.optional(),
    env: EnvironmentSchema,
    notes: TextSchema.optional(),
  })
  .strict()
  .superRefine((load, ctx) => {
    if ((load.qty === undefined) === (load.lengthFt === undefined))
      ctx.addIssue({
        code: 'custom',
        path: ['qty'],
        message: 'Specify fixture quantity OR tape length, not both or neither',
      });
    if (load.feedMethod === 'multi-feed' && (load.feeds === undefined || load.feeds < 2))
      ctx.addIssue({
        code: 'custom',
        path: ['feeds'],
        message: 'Multi-feed requires at least two feeds',
      });
    if (load.feedMethod !== 'multi-feed' && load.feeds !== undefined)
      ctx.addIssue({
        code: 'custom',
        path: ['feeds'],
        message: 'Explicit feed count belongs to multi-feed only',
      });
  });
export type Load = z.infer<typeof LoadSchema>;
export const ControlLinkSchema = z
  .object({
    id: IdSchema,
    from: PortRefSchema,
    to: PortRefSchema,
    protocol: ProtocolSchema,
    lengthFt: NonnegativeSchema,
    env: EnvironmentSchema,
    universe: CountSchema.max(63999).optional(),
    notes: TextSchema.optional(),
  })
  .strict();
export type ControlLink = z.infer<typeof ControlLinkSchema>;
export const WireOverrideSchema = z
  .object({
    wireTypeId: IdSchema,
    parallelSets: CountSchema.default(1),
    parallelCommonConductors: CountSchema.default(1),
    note: TextSchema.optional(),
  })
  .strict();
export const ProjectSchema = z
  .object({
    schemaVersion: z.literal(1),
    id: z.uuid(),
    meta: ProjectMetaSchema,
    settings: ProjectSettingsSchema,
    sources: z.array(SourceSchema),
    equipment: z.array(EquipmentSchema),
    loads: z.array(LoadSchema),
    controlLinks: z.array(ControlLinkSchema),
    wireOverrides: z.record(IdSchema, WireOverrideSchema),
    layoutOverrides: z.record(
      IdSchema,
      z.object({ x: z.number().finite(), y: z.number().finite(), pinned: z.boolean() }).strict(),
    ),
    generalNotes: z.array(TextSchema),
    keyNotes: uniqueList(z.object({ id: IdSchema, text: TextSchema }).strict(), (v) => v.id),
    revisions: z.array(
      z
        .object({
          rev: IdSchema,
          date: z.iso.date(),
          description: TextSchema,
          by: z.string().max(100),
        })
        .strict(),
    ),
    wireTagMap: z.record(IdSchema, z.string().regex(/^W-\d{2,}$/)),
    scratchNote: TextSchema,
  })
  .strict()
  .superRefine((project, ctx) => {
    const ids = new Set<string>();
    const aliases = new Map<string, string>();
    for (const key of ['sources', 'equipment', 'loads', 'controlLinks'] as const) {
      project[key].forEach((entity, index) => {
        if (ids.has(entity.id))
          ctx.addIssue({
            code: 'custom',
            path: [key, index, 'id'],
            message: `Duplicate entity ID: ${entity.id}`,
          });
        ids.add(entity.id);
        // ID/tag collisions are ambiguous. Repeated load typeTags are intentional.
        for (const alias of new Set([entity.id, ...('tag' in entity ? [entity.tag] : [])])) {
          const owner = aliases.get(alias);
          if (owner && owner !== entity.id)
            ctx.addIssue({
              code: 'custom',
              path: [key, index],
              message: `Ambiguous ID/tag: ${alias}`,
            });
          aliases.set(alias, entity.id);
        }
      });
    }
    const tags = Object.values(project.wireTagMap);
    if (new Set(tags).size !== tags.length)
      ctx.addIssue({ code: 'custom', path: ['wireTagMap'], message: 'Wire tags must be unique' });
  });
export type Project = z.infer<typeof ProjectSchema>;

export const ValidationMessageSchema = z
  .object({
    code: z.enum([
      'INCOMPLETE_SPEC',
      'UNRESOLVED_REF',
      'CYCLE',
      'VOLTAGE_MISMATCH',
      'DRIVE_MISMATCH',
      'PROTOCOL_MISMATCH',
      'INPUT_V_OUT_OF_RANGE',
      'PSU_OVERLOAD',
      'CHANNEL_OVERCURRENT',
      'BREAKER_OVERLOAD',
      'TAPE_UNDERVOLTAGE',
      'NO_VALID_WIRE',
      'DMX_ADDRESS_OVERLAP',
      'DMX_ADDRESS_OVERFLOW',
      'PSU_ABOVE_DERATE',
      'CLASS2_OVER_100VA',
      'VD_OVER_TARGET',
      'TAPE_RUN_TOO_LONG',
      'TERMINAL_OVERSIZE',
      'DMX_UNIT_LOADS',
      'DMX_LENGTH',
      'DMX_NO_TERMINATOR',
      'SPI_DATA_LENGTH',
      'INRUSH_LIMIT',
      'PHASE_DIMMER_COMPAT_UNKNOWN',
      'EXAMPLE_PRODUCT_IN_USE',
      'MAX_LENGTH_HINT',
      'SUGGEST_SPLIT_FEED',
      'CODE_TABLE_UNAVAILABLE',
      'WIRE_REQUIRES_VERIFICATION',
      'INVALID_SPEC',
      'INVALID_PORT',
      'DMX_TOPOLOGY',
      'PARALLEL_REVIEW_REQUIRED',
      'DATA_LENGTH',
      'CC_COMPLIANCE',
      'INPUT_CURRENT_ESTIMATED',
      'QTY_DISTRIBUTION',
      'DEVICE_CAPACITY',
      // Added by the System Designer (plan Appendix C).
      'PROFILE_THERMAL_LIMIT',
      'SUPPLY_LOCATION_RATING',
      'SUPPLY_NO_ACCESS',
      'CABINET_HEAT',
      'DIMMER_MIN_LOAD',
      'DIMMER_LED_MAX',
      'DIMMER_SUPPLY_COUNT',
      'DIMMER_NEUTRAL',
      'VD_TARGET_LOOSENED',
      'SCHEDULE_OUT_OF_SYNC',
      'CONFIG_PLAN_REPLACED',
      'DATA_BY_DEALER',
      'REVIEW_REQUIRED',
      'RUN_UNASSIGNED',
    ]),
    severity: z.enum(['error', 'warning', 'info']),
    entityRef: IdSchema,
    text: z.string().min(1),
  })
  .strict();
export type ValidationMessage = z.infer<typeof ValidationMessageSchema>;
