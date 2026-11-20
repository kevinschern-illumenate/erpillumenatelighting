import { z } from 'zod';
import { EnvChoiceSchema } from './design';

/**
 * The draw-to-quote package (`ilq/2`, CAD toolkit plan 1.5): what was drawn in AutoCAD, never prices.
 *
 * The toolkit sends geometry and run styles; the portal import makes the schedule lines (configured
 * builds), so lengths here are raw path lengths in inches and the server snaps and splits them. The
 * `erp` keys come back in the import receipt and are written into the drawing's XData, so a re-import
 * updates the same lines. Python validates against the JSON Schema exported from this file.
 */
export const ILQ_SCHEMA = 'ilq/2';
export const ILQ_MAX_RUNS = 1000;
export const ILQ_MAX_BYTES = 5 * 1024 * 1024;

/** A CAD id: run, room, cabinet, PSU or wire tag (`L1-01`, `CAB-1`, `PS-01`, `W-01`). */
export const CadIdSchema = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/);
const HandleSchema = z.string().regex(/^[0-9A-Fa-f]{1,16}$/);
const HashSchema = z.string().regex(/^[0-9a-f]{64}$/);
const Text = (max: number) => z.string().max(max);
const Inches = z.number().finite().positive().max(1_000_000);

export const ILQ_FAMILIES = ['LED Tape', 'COB Tape', 'LED Neon', 'Linear Fixture', 'Extrusion Kit'] as const;
export const TAPE_FAMILIES = ['LED Tape', 'COB Tape', 'LED Neon'] as const;

const SelectionsSchema = z.record(z.string().max(80), z.unknown());

/** The style a run is drawn in: a configuration preset, or a template with its selections (D: Q4). */
export const IlqStyleSchema = z
  .object({
    preset: Text(140).optional(),
    family: z.enum(ILQ_FAMILIES),
    template: z.string().min(1).max(140),
    selections: SelectionsSchema.default({}),
    /** The preset's own segments: feed and leader defaults; drawn lengths replace theirs. */
    segments: z.array(z.record(z.string(), z.unknown())).max(50).optional(),
    /** Extrusion Kit styles: the tape built into the kit (Q5, a kit line plus a tape build). */
    tape: z
      .object({
        family: z.enum(TAPE_FAMILIES),
        template: z.string().min(1).max(140),
        selections: SelectionsSchema.default({}),
      })
      .strict()
      .optional(),
  })
  .strict();
export type IlqStyle = z.infer<typeof IlqStyleSchema>;

export const IlqSegmentSchema = z
  .object({
    path_length_in: Inches,
    /** Feed direction at the start of the first segment (the template's Feed Direction value). */
    start_feed: Text(60).nullish(),
    lead_length_in: z.number().finite().nonnegative().max(10_000).nullish(),
    end_type: z.enum(['ENDCAP', 'JUMPER']).default('ENDCAP'),
    jumper_length_in: z.number().finite().nonnegative().max(10_000).nullish(),
    /** Smallest arc radius on this segment's path, for the bend check; null when straight. */
    min_arc_radius_in: z.number().finite().positive().nullish(),
  })
  .strict();
export type IlqSegment = z.infer<typeof IlqSegmentSchema>;

export const IlqErpKeysSchema = z
  .object({
    line_key: Text(140).nullish(),
    configured_name: Text(140).nullish(),
    config_hash: Text(140).nullish(),
  })
  .strict();

export const IlqRunSchema = z
  .object({
    id: CadIdSchema,
    handle: HandleSchema,
    room: CadIdSchema.nullish(),
    /** The schedule Type (`line_id`) the run belongs to, e.g. `L1`. */
    fixture_type: z.string().trim().min(1).max(140),
    location: Text(140).nullish(),
    style: IlqStyleSchema,
    segments: z.array(IlqSegmentSchema).min(1).max(50),
    feed: z
      .object({
        method: z.enum(['end', 'double-end', 'center', 'multi-feed']).default('end'),
        point_handles: z.array(HandleSchema).max(20).default([]),
      })
      .strict()
      .default({ method: 'end', point_handles: [] }),
    cabinet: CadIdSchema.nullish(),
    psu_hint: Text(140).nullish(),
    notes: Text(1000).nullish(),
    erp: IlqErpKeysSchema.default({}),
  })
  .strict();
export type IlqRun = z.infer<typeof IlqRunSchema>;

export const IlqPackageSchema = z
  .object({
    schema: z.literal(ILQ_SCHEMA),
    toolkit: z.object({ version: Text(40), platform: Text(80) }).strict(),
    catalog: z
      .object({ snapshot_hash: HashSchema, hash: HashSchema.nullish(), generated_at: Text(40) })
      .strict(),
    target: z
      .object({
        schedule: Text(140).default(''),
        schedule_version: z.number().int().nonnegative().default(0),
        project: Text(140).default(''),
      })
      .strict(),
    drawing: z
      .object({
        file: z.string().min(1).max(260),
        rev: z.number().int().nonnegative(),
        hash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
        units: z.literal('in'),
        scale_verified: z.boolean(),
      })
      .strict(),
    rooms: z
      .array(
        z
          .object({
            id: CadIdSchema,
            name: z.string().trim().min(1).max(120),
            level: Text(60).default(''),
            env: EnvChoiceSchema.default('dry-concealed'),
          })
          .strict(),
      )
      .max(500)
      .default([]),
    cabinets: z
      .array(
        z
          .object({
            id: CadIdSchema,
            room: CadIdSchema.nullish(),
            location_rating: z.enum(['Dry', 'Damp', 'Wet']).default('Dry'),
            access_note: Text(300).default(''),
          })
          .strict(),
      )
      .max(200)
      .default([]),
    runs: z.array(IlqRunSchema).max(ILQ_MAX_RUNS),
    psus: z
      .array(
        z
          .object({
            id: CadIdSchema,
            cabinet: CadIdSchema.nullish(),
            item_code: Text(140).nullish(),
            runs: z.array(CadIdSchema).max(200).default([]),
          })
          .strict(),
      )
      .max(500)
      .default([]),
    wire_paths: z
      .array(
        z
          .object({
            id: CadIdSchema,
            from: CadIdSchema,
            to: CadIdSchema,
            kind: z.enum(['lv', 'line', 'data']),
            path_length_in: Inches,
          })
          .strict(),
      )
      .max(2000)
      .default([]),
    check: z
      .object({
        errors: z.number().int().nonnegative(),
        warnings: z.number().int().nonnegative(),
        overrides: z
          .array(z.object({ code: Text(60), ref: Text(60), note: z.string().min(3).max(1000) }).strict())
          .max(500)
          .default([]),
      })
      .strict(),
    other_lines: z
      .array(
        z
          .object({
            fixture_type: z.string().trim().min(1).max(140),
            qty: z.number().int().min(1).max(1_000_000),
            location: Text(140).nullish(),
            manufacturer_name: z.string().trim().min(1).max(140),
            fixture_model_number: Text(140).nullish(),
            watts_each: z.number().finite().nonnegative().nullish(),
            input_voltage_v: z.number().finite().positive().nullish(),
            voltage_class: z.enum(['Low Voltage', 'Line Voltage']).nullish(),
            notes: Text(1000).nullish(),
          })
          .strict(),
      )
      .max(500)
      .default([]),
  })
  .strict()
  .superRefine((pkg, ctx) => {
    const unique = (items: { id: string }[], path: string) => {
      const seen = new Set<string>();
      items.forEach((item, index) => {
        if (seen.has(item.id))
          ctx.addIssue({ code: 'custom', path: [path, index, 'id'], message: `Duplicate id: ${item.id}` });
        seen.add(item.id);
      });
      return seen;
    };
    const rooms = unique(pkg.rooms, 'rooms');
    const cabinets = unique(pkg.cabinets, 'cabinets');
    const runs = unique(pkg.runs, 'runs');
    const psus = unique(pkg.psus, 'psus');
    unique(pkg.wire_paths, 'wire_paths');
    const handles = new Set<string>();
    pkg.cabinets.forEach((cabinet, index) => {
      if (cabinet.room && !rooms.has(cabinet.room))
        ctx.addIssue({ code: 'custom', path: ['cabinets', index, 'room'], message: `Unknown room: ${cabinet.room}` });
    });
    pkg.runs.forEach((run, index) => {
      if (run.room && !rooms.has(run.room))
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'room'], message: `Unknown room: ${run.room}` });
      if (run.cabinet && !cabinets.has(run.cabinet))
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'cabinet'], message: `Unknown cabinet: ${run.cabinet}` });
      const handle = run.handle.toUpperCase();
      if (handles.has(handle))
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'handle'], message: `Duplicate handle: ${run.handle}` });
      handles.add(handle);
      if (run.style.family === 'Extrusion Kit' && !run.style.tape)
        ctx.addIssue({ code: 'custom', path: ['runs', index, 'style', 'tape'], message: 'A kit style needs its tape' });
    });
    pkg.psus.forEach((psu, index) => {
      if (psu.cabinet && !cabinets.has(psu.cabinet))
        ctx.addIssue({ code: 'custom', path: ['psus', index, 'cabinet'], message: `Unknown cabinet: ${psu.cabinet}` });
      psu.runs.forEach((run, position) => {
        if (!runs.has(run))
          ctx.addIssue({ code: 'custom', path: ['psus', index, 'runs', position], message: `Unknown run: ${run}` });
      });
    });
    const ends = new Set([...runs, ...psus, ...cabinets]);
    pkg.wire_paths.forEach((wire, index) => {
      for (const end of ['from', 'to'] as const)
        if (!ends.has(wire[end]))
          ctx.addIssue({ code: 'custom', path: ['wire_paths', index, end], message: `Unknown end: ${wire[end]}` });
    });
  });
export type IlqPackage = z.infer<typeof IlqPackageSchema>;

export function ilqJsonSchema() {
  return z.toJSONSchema(IlqPackageSchema, { target: 'draft-2020-12', unrepresentable: 'any', io: 'input' });
}
