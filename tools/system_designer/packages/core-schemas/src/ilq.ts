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

/** Which front end wrote the package (WP 1.1). Absent on 0.4.x AutoCAD packages; the server derives it. */
export const ILQ_SOURCE_TOOLS = ['autocad', 'dxf', 'bluebeam', 'web'] as const;
export const ILQ_SOURCE_INPUTS = ['ilq', 'dxf', 'pdf', 'csv'] as const;
export const IlqSourceSchema = z
  .object({
    tool: z.enum(ILQ_SOURCE_TOOLS),
    version: Text(40),
    platform: Text(80).nullish(),
    input: z.enum(ILQ_SOURCE_INPUTS),
  })
  .strict();
export type IlqSource = z.infer<typeof IlqSourceSchema>;

/**
 * How far a sheet's scale can be trusted (WP 1.3): `verified` was calibrated in the tool (ILSCALE, a
 * calibrated PDF viewport), `declared` only has units set, `unverified` has neither.
 */
export const SCALE_STATUSES = ['verified', 'declared', 'unverified'] as const;
export const IlqScaleSchema = z
  .object({
    status: z.enum(SCALE_STATUSES),
    /** Drawing inches per page unit, when the tool knows it. */
    ratio: z.number().finite().positive().nullish(),
    unit: Text(20).nullish(),
    /** A known length the user confirmed against the drawing. */
    check_dimension_in: Inches.nullish(),
  })
  .strict();

/** A sheet: an AutoCAD layout or level, or a PDF page (A7). */
export const IlqSheetSchema = z
  .object({
    id: CadIdSchema,
    label: Text(120).default(''),
    page: z.number().int().min(1).max(500).nullish(),
    scale: IlqScaleSchema,
  })
  .strict();
export type IlqSheet = z.infer<typeof IlqSheetSchema>;

/** How a run's id was assigned, so a re-import can trust an `xdata` match more than a `proposed` one (G2). */
export const RUN_IDENTITIES = ['xdata', 'dxf_handle', 'markup_name', 'csv_row', 'proposed'] as const;

/** Counted items (supply locations, controls, third-party fixtures) from tools that only count (C4). */
export const IlqCountSchema = z
  .object({
    item: z.string().trim().min(1).max(140),
    kind: z.enum(['psu', 'control', 'other']),
    qty: z.number().int().min(1).max(100_000),
    sheet: CadIdSchema.nullish(),
    room: CadIdSchema.nullish(),
    tag: CadIdSchema.nullish(),
  })
  .strict();
export type IlqCount = z.infer<typeof IlqCountSchema>;

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
    sheet: CadIdSchema.nullish(),
    identity: z.enum(RUN_IDENTITIES).nullish(),
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

/** Zone control methods: the System Designer's zone methods (`ZoneSchema.method`). */
export const ZONE_METHODS = [
  'phase-forward',
  'phase-reverse',
  '0-10V',
  'DALI-2',
  'DMX512',
  'CRMX-wireless',
  'Lutron-QS',
  'Lutron-EcoSystem',
  'none',
] as const;

/** A controller, decoder or other control placed in the drawing (controls in v1, PRD question 7). */
export const IlqControlSchema = z
  .object({
    id: CadIdSchema,
    handle: HandleSchema,
    item_code: z.string().trim().min(1).max(140),
    cabinet: CadIdSchema.nullish(),
    room: CadIdSchema.nullish(),
    dmx: z
      .object({
        universe: z.number().int().min(1).max(63999),
        start_address: z.union([z.number().int().min(1).max(512), z.literal('auto')]).default('auto'),
      })
      .strict()
      .nullish(),
    /** Another control this one takes its signal from (a DMX controller feeding a decoder). */
    control_from: CadIdSchema.nullish(),
    notes: Text(1000).nullish(),
    erp: IlqErpKeysSchema.default({}),
  })
  .strict();
export type IlqControl = z.infer<typeof IlqControlSchema>;

/** Runs dimmed together, and the control output that dims them. */
export const IlqZoneSchema = z
  .object({
    id: CadIdSchema,
    name: z.string().trim().min(1).max(120),
    method: z.enum(ZONE_METHODS),
    control: z.object({ id: CadIdSchema, port: z.string().trim().min(1).max(60) }).strict().nullish(),
    runs: z.array(CadIdSchema).max(1000).default([]),
  })
  .strict();
export type IlqZone = z.infer<typeof IlqZoneSchema>;

export const IlqPackageSchema = z
  .object({
    schema: z.literal(ILQ_SCHEMA),
    toolkit: z.object({ version: Text(40), platform: Text(80) }).strict(),
    source: IlqSourceSchema.optional(),
    sheets: z.array(IlqSheetSchema).max(500).default([]),
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
            sheet: CadIdSchema.nullish(),
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
    controls: z.array(IlqControlSchema).max(500).default([]),
    counts: z.array(IlqCountSchema).max(2000).default([]),
    zones: z.array(IlqZoneSchema).max(500).default([]),
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
    const sheets = unique(pkg.sheets, 'sheets');
    const rooms = unique(pkg.rooms, 'rooms');
    const usedSheets = new Set<string>();
    const knownSheet = (sheet: string | null | undefined, path: (string | number)[]) => {
      if (!sheet) return;
      usedSheets.add(sheet);
      if (!sheets.has(sheet)) ctx.addIssue({ code: 'custom', path, message: `Unknown sheet: ${sheet}` });
    };
    pkg.rooms.forEach((room, index) => knownSheet(room.sheet, ['rooms', index, 'sheet']));
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
      knownSheet(run.sheet, ['runs', index, 'sheet']);
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
    const controls = unique(pkg.controls, 'controls');
    unique(pkg.zones, 'zones');
    for (const id of controls)
      if (runs.has(id) || psus.has(id) || cabinets.has(id))
        ctx.addIssue({ code: 'custom', path: ['controls'], message: `Control id is used elsewhere: ${id}` });
    pkg.controls.forEach((control, index) => {
      if (control.cabinet && !cabinets.has(control.cabinet))
        ctx.addIssue({ code: 'custom', path: ['controls', index, 'cabinet'], message: `Unknown cabinet: ${control.cabinet}` });
      if (control.room && !rooms.has(control.room))
        ctx.addIssue({ code: 'custom', path: ['controls', index, 'room'], message: `Unknown room: ${control.room}` });
      if (control.control_from && (!controls.has(control.control_from) || control.control_from === control.id))
        ctx.addIssue({ code: 'custom', path: ['controls', index, 'control_from'], message: `Unknown control: ${control.control_from}` });
      const handle = control.handle.toUpperCase();
      if (handles.has(handle))
        ctx.addIssue({ code: 'custom', path: ['controls', index, 'handle'], message: `Duplicate handle: ${control.handle}` });
      handles.add(handle);
    });
    const zoned = new Set<string>();
    pkg.zones.forEach((zone, index) => {
      if (zone.control && !controls.has(zone.control.id))
        ctx.addIssue({ code: 'custom', path: ['zones', index, 'control', 'id'], message: `Unknown control: ${zone.control.id}` });
      zone.runs.forEach((run, position) => {
        if (!runs.has(run))
          ctx.addIssue({ code: 'custom', path: ['zones', index, 'runs', position], message: `Unknown run: ${run}` });
        else if (zoned.has(run))
          ctx.addIssue({ code: 'custom', path: ['zones', index, 'runs', position], message: `Run is in two zones: ${run}` });
        zoned.add(run);
      });
    });
    pkg.counts.forEach((count, index) => {
      knownSheet(count.sheet, ['counts', index, 'sheet']);
      if (count.room && !rooms.has(count.room))
        ctx.addIssue({ code: 'custom', path: ['counts', index, 'room'], message: `Unknown room: ${count.room}` });
    });
    if (pkg.drawing.scale_verified)
      pkg.sheets.forEach((sheet, index) => {
        if (usedSheets.has(sheet.id) && sheet.scale.status !== 'verified')
          ctx.addIssue({
            code: 'custom',
            path: ['sheets', index, 'scale', 'status'],
            message: `Drawing says its scale is verified but sheet ${sheet.id} is ${sheet.scale.status}`,
          });
      });
    const ends = new Set([...runs, ...psus, ...cabinets, ...controls]);
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
