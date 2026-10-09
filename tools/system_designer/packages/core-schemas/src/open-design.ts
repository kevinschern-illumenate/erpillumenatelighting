import { z } from 'zod';
import { EnvironmentSchema, IdSchema, NonnegativeSchema, PositiveSchema, ProtocolSchema } from './common';
import { CONFIGURED_DOCTYPES, FeedMethodSchema } from './design';

/**
 * What `system_design.api.open_design` sends (plan H6, WP-2.3): schedule lines and their configured
 * builds, already normalized by `system_design/expansion.py`. `@ill/engine/expand` turns them into runs.
 */
export const LineKindSchema = z.enum([
  'configured',
  'third-party',
  'accessory',
  'unconfigured',
  'writeback',
]);

export const ConfiguredRefSchema = z
  .object({ doctype: z.enum(CONFIGURED_DOCTYPES), name: IdSchema })
  .strict();

export const ThirdPartySchema = z
  .object({
    wattsEach: PositiveSchema.nullable(),
    inputVoltageV: PositiveSchema.nullable(),
    voltageClass: z.enum(['Low Voltage', 'Line Voltage']).nullable(),
    drive: z.enum(['CV', 'CC', 'Integral Driver']).nullable(),
    mA: PositiveSchema.nullable(),
    dimming: ProtocolSchema.nullable(),
    dimmingName: z.string().nullable(),
    manufacturer: z.string().nullable(),
    model: z.string().nullable(),
  })
  .strict();

export const LineSchema = z
  .object({
    key: z.string().regex(/^[^:]+$/),
    lineKey: z.string().nullable(),
    lineId: z.string().nullable(),
    idx: z.number().int().positive(),
    qty: z.number().int().nonnegative(),
    location: z.string(),
    kind: LineKindSchema,
    productType: z.string().nullable(),
    configured: ConfiguredRefSchema.nullable(),
    accessoryItem: z.string().nullable(),
    powerSupplyForLine: z.string().nullable(),
    designLineRole: z.string().nullable(),
    thirdParty: ThirdPartySchema.nullable(),
  })
  .strict();
export type Line = z.infer<typeof LineSchema>;

export const BuildRunSchema = z
  .object({
    runIndex: z.number().int().positive(),
    lengthFt: PositiveSchema.nullable(),
    watts: NonnegativeSchema,
    feedMethod: FeedMethodSchema,
    feeds: z.number().int().positive().optional(),
  })
  .strict();

export const BuildSchema = z
  .object({
    doctype: z.enum(CONFIGURED_DOCTYPES),
    name: IdSchema,
    family: z.enum(['linear', 'tape', 'sheet', 'group']),
    configHash: z.string().nullable(),
    /** The configured product's own part number (a fixture's, not its tape's). */
    partNumber: z.string().nullable().optional(),
    runs: z.array(BuildRunSchema),
    issues: z.array(z.string()),
    protocols: z.array(ProtocolSchema).optional(),
    catalogId: z.string().nullable(),
    environmentRating: z.string().nullable(),
    environment: EnvironmentSchema.nullable(),
    offering: z.string().nullable(),
    maxRunFtEffective: PositiveSchema.nullable(),
    totalWatts: NonnegativeSchema.nullable(),
    allocations: z.array(
      z
        .object({
          runKey: z.string(),
          supply: z.number().int().nullable(),
          output: z.number().int().nullable(),
          itemCode: z.string().nullable(),
        })
        .strict(),
    ),
  })
  .strict();
export type Build = z.infer<typeof BuildSchema>;

/** `builds[doctype][name]`. */
export const BuildsSchema = z.record(z.string(), z.record(z.string(), BuildSchema));
export type Builds = z.infer<typeof BuildsSchema>;
