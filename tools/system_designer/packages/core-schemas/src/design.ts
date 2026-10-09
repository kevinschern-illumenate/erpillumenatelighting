import { z } from 'zod';
import {
  CountSchema,
  EnvironmentSchema,
  IdSchema,
  NonnegativeSchema,
  PositiveSchema,
} from './common';
import { ProjectSchema } from './project';

/**
 * The saved System Designer document (plan H5, schema version 1).
 *
 * The riser `ProjectSchema` stays the engine input; a design wraps it with the site, the runs expanded
 * from the schedule and the ERP context. `project.loads` is derived from `runs` (`deriveLoads`), never
 * edited directly.
 */
export const DESIGN_SCHEMA_VERSION = 1;

export const RunKeySchema = z.string().regex(/^[^:]+:\d+:\d+$/); // {line_key}:{build}:{run}
export const LengthProvenanceSchema = z.enum(['estimate', 'entered', 'measured', 'erp']);
export const EnvSchema = EnvironmentSchema;

export const SpaceSchema = z
  .object({
    id: IdSchema,
    name: z.string().min(1).max(120),
    level: z.string().max(60).default(''),
    type: z
      .enum([
        'kitchen',
        'living',
        'dining',
        'bedroom',
        'bath',
        'hall',
        'stair',
        'exterior',
        'mechanical',
        'closet',
        'other',
      ])
      .default('other'),
    archetype: z
      .enum(['cove', 'under-cabinet', 'toe-kick', 'shelving', 'niche', 'ceiling-reveal', 'stair', 'none'])
      .default('none'),
    env: EnvSchema.default('dry-concealed'),
  })
  .strict();
export type Space = z.infer<typeof SpaceSchema>;

export const CabinetSchema = z
  .object({
    id: IdSchema,
    tag: IdSchema,
    name: z.string().max(120),
    spaceId: IdSchema,
    locationRating: z.enum(['Dry', 'Damp', 'Wet']),
    env: EnvSchema,
    accessNote: z.string().max(300).default(''),
    sourceId: IdSchema.optional(),
    feedLengthFt: NonnegativeSchema.default(0),
    feedLengthProvenance: LengthProvenanceSchema.default('estimate'),
  })
  .strict();
export type Cabinet = z.infer<typeof CabinetSchema>;

export const CONFIGURED_DOCTYPES = [
  'ilL-Configured-Fixture',
  'ilL-Configured-Tape-Neon',
  'ilL-Configured-LED-Sheet',
  'ilL-Configured-Group',
] as const;

export const RunSourceSchema = z.discriminatedUnion('kind', [
  z
    .object({
      kind: z.literal('configured'),
      doctype: z.enum(CONFIGURED_DOCTYPES),
      name: IdSchema,
      configHash: IdSchema,
    })
    .strict(),
  z.object({ kind: z.literal('third-party') }).strict(), // D8
]);

export const FeedMethodSchema = z.enum(['end', 'double-end', 'center', 'multi-feed']);

export const RunSchema = z
  .object({
    key: RunKeySchema,
    lineKey: IdSchema,
    lineId: IdSchema,
    buildIndex: CountSchema,
    runIndex: CountSchema,
    groupId: IdSchema.optional(),
    source: RunSourceSchema,
    catalogId: IdSchema, // tape item id, or tp:{line_key} for third-party
    lengthFt: PositiveSchema.optional(), // ERP, read-only
    watts: PositiveSchema, // ERP or dealer (D8)
    feedMethod: FeedMethodSchema,
    feeds: CountSchema.optional(),
    spaceId: IdSchema,
    env: EnvSchema,
    homeRunLengthFt: NonnegativeSchema,
    homeRunProvenance: LengthProvenanceSchema,
    assignment: z.object({ equipmentId: IdSchema, port: IdSchema }).strict().optional(),
    zoneId: IdSchema.optional(),
  })
  .strict();
export type Run = z.infer<typeof RunSchema>;

export const ZoneSchema = z
  .object({
    id: IdSchema,
    name: z.string().max(120),
    color: z.string().regex(/^#[0-9a-fA-F]{6}$/), // no /i: JSON Schema patterns have no flags
    method: z.enum([
      'phase-forward',
      'phase-reverse',
      '0-10V',
      'DALI-2',
      'DMX512',
      'Lutron-QS',
      'Lutron-EcoSystem',
      'CRMX-wireless',
      'none',
    ]),
  })
  .strict();
export type Zone = z.infer<typeof ZoneSchema>;

export const OverrideSchema = z
  .object({
    code: IdSchema,
    entityRef: IdSchema,
    kind: z.enum(['acknowledge', 'staff-override']),
    reason: z.string().min(3).max(1000),
    by: z.string(),
    at: z.iso.datetime(),
  })
  .strict();
export type Override = z.infer<typeof OverrideSchema>;

export const DesignSchema = z
  .object({
    schemaVersion: z.literal(DESIGN_SCHEMA_VERSION),
    engineVersion: z.string(),
    catalogSnapshotHash: z.string().regex(/^[0-9a-f]{64}$/),
    schedule: z.object({ name: IdSchema, version: z.number().int().nonnegative() }).strict(),
    site: z
      .object({
        spaces: z.array(SpaceSchema),
        cabinets: z.array(CabinetSchema),
        floorPlans: z.array(z.unknown()).default([]), // FloorPlanSchema replaces unknown in WP-6.5 (schema v2)
      })
      .strict(),
    runs: z.array(RunSchema).max(1000),
    zones: z.array(ZoneSchema),
    project: ProjectSchema,
    views: z
      .object({
        saved3d: z.array(z.unknown()).default([]),
        presentation: z.unknown().optional(),
        riser: z.unknown().optional(),
      })
      .strict()
      .default({ saved3d: [] }),
    overrides: z.array(OverrideSchema).default([]),
  })
  .strict()
  .superRefine((design, ctx) => {
    const spaces = new Set(design.site.spaces.map((space) => space.id));
    const runKeys = new Set<string>();
    design.runs.forEach((run, index) => {
      if (runKeys.has(run.key))
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'key'], message: `Duplicate run key: ${run.key}` });
      runKeys.add(run.key);
      if (!spaces.has(run.spaceId))
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'spaceId'], message: `Unknown space: ${run.spaceId}` });
    });
    design.site.cabinets.forEach((cabinet, index) => {
      if (!spaces.has(cabinet.spaceId))
        ctx.addIssue({
          code: 'custom',
          path: ['site', 'cabinets', index, 'spaceId'],
          message: `Unknown space: ${cabinet.spaceId}`,
        });
    });
  });
export type Design = z.infer<typeof DesignSchema>;

/** JSON Schema for the server (`designs.validate_design_json`). Cross-reference rules stay Zod/Python-only. */
export function designJsonSchema() {
  return z.toJSONSchema(DesignSchema, { target: 'draft-2020-12', unrepresentable: 'any' });
}
