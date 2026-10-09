import { z } from 'zod';
import { EditionSchema } from '@ill/core-schemas/common';
import { DESIGN_SCHEMA_VERSION, DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema } from '@ill/core-schemas/open-design';
import { ProjectSettingsSchema } from '@ill/core-schemas/project';
import { createDraft } from '@ill/core-schemas/workspace';
import { expandRuns, type ExpandOptions, type Skipped } from '@ill/engine/expand';
import type { ReconcileDiff } from '@ill/engine/reconcile';
import type { DesignMessage } from '@ill/engine/designCheck';
import { runChecks, runLabel } from '@ill/engine/runs';
import type { Deliverable, DesignMeta } from '../design/api';

/** Written into every saved design so a later engine can tell which one produced it. */
export const ENGINE_VERSION = 'system-designer-0.1.0';

const ReasonSchema = z.object({ code: z.string(), detail: z.string().nullish() });

/** What `open_design` returns (plan H6). Lines and builds are checked; the rest is read loosely. */
export const OpenDesignSchema = z.object({
  schedule: z.object({
    name: z.string(),
    schedule_name: z.string().nullish(),
    version: z.number().int().nonnegative(),
    is_locked: z.boolean(),
    status: z.string().nullish(),
    project: z.string().nullish(),
  }),
  lines: z.array(LineSchema),
  builds: BuildsSchema,
  design: z.unknown().nullable(),
  design_meta: z
    .object({
      name: z.string(),
      revision: z.string(),
      status: z.string(),
      modified: z.string(),
      schedule_version: z.number(),
      is_current: z.boolean(),
      terms_accepted: z.boolean().default(false),
      approved_by: z.string().nullish(),
    })
    .nullable(),
  reconcile: z.custom<ReconcileDiff>((value) => value === null || typeof value === 'object').nullable(),
  catalog_hash: z.string().regex(/^[0-9a-f]{64}$/),
  readiness: z.object({
    ready: z.array(z.string()),
    needs_data: z.array(z.object({ key: z.string(), reason: z.string() })),
    unconfigured: z.array(z.string()),
    catalog_gaps: z.array(z.object({ key: z.string(), catalogId: z.string().nullish(), reason: z.string() })),
    missing_line_keys: z.array(z.string()).default([]),
  }),
  review_requirement: z.object({
    required: z.boolean(),
    reasons: z.array(ReasonSchema),
    satisfied: z.boolean(),
  }),
  permissions: z.object({ can_edit: z.boolean(), can_review: z.boolean(), can_view_pricing: z.boolean() }),
  settings: z.record(z.string(), z.unknown()),
  newer_version: z.object({ name: z.string(), version: z.number() }).nullish(),
  /** The signed-in user, recorded on acknowledgements and overrides. */
  user: z.string().nullish(),
  /** What the riser title block names (plan §12.1); older servers send none. */
  title_block: z
    .object({
      project_name: z.string().default(''),
      project_number: z.string().default(''),
      site_address: z.string().default(''),
      customer: z.string().default(''),
      dealer_logo: z.string().nullish(),
    })
    .nullish(),
  /** Generated files already stored on this design. */
  deliverables: z.array(z.custom<Deliverable>((value) => typeof value === 'object' && value !== null)).default([]),
});
export type OpenDesign = z.infer<typeof OpenDesignSchema>;

const num = (value: unknown, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback;

export function expandOptions(open: OpenDesign): ExpandOptions {
  return {
    groupThresholdQty: num(open.settings.group_threshold_qty, 4),
    defaultHomeRunFt: num(open.settings.default_distance_same_space_ft, 15),
  };
}

/** A first design for a schedule with no saved one: spaces and runs from the lines, Settings targets. */
export function newDesign(open: OpenDesign): { design: Design; skipped: Skipped[] } {
  const { spaces, runs, skipped } = expandRuns(open.lines, open.builds, expandOptions(open));
  const project = createDraft();
  const edition = EditionSchema.safeParse(open.settings.nec_edition);
  project.meta.name = open.schedule.schedule_name || open.schedule.name;
  project.settings = ProjectSettingsSchema.parse({
    ...project.settings,
    necEdition: edition.success ? edition.data : project.settings.necEdition,
    vdTargetLowVoltagePct: num(open.settings.vd_target_class2_pct, project.settings.vdTargetLowVoltagePct),
    vdTargetLineVoltagePct: num(open.settings.vd_target_line_pct, project.settings.vdTargetLineVoltagePct),
    vdTargetLandscapePct: num(open.settings.vd_target_landscape_pct, project.settings.vdTargetLandscapePct),
    wireWastePct: num(open.settings.wire_waste_pct, project.settings.wireWastePct),
  });
  const design = DesignSchema.parse({
    schemaVersion: DESIGN_SCHEMA_VERSION,
    engineVersion: ENGINE_VERSION,
    catalogSnapshotHash: open.catalog_hash,
    schedule: { name: open.schedule.name, version: open.schedule.version },
    site: { spaces, cabinets: [], floorPlans: [] },
    runs,
    zones: [],
    project,
  });
  return { design, skipped };
}

/** The saved design, or a new one; the second value lists lines that produced no runs. */
export function startingDesign(open: OpenDesign): { design: Design; meta: DesignMeta | null; skipped: Skipped[] } {
  if (open.design && open.design_meta)
    return { design: DesignSchema.parse(open.design), meta: open.design_meta, skipped: [] };
  return { ...newDesign(open), meta: null };
}

export type Severity = 'error' | 'warning' | 'info';
export interface Check {
  id: string;
  severity: Severity;
  title: string;
  detail: string;
}

const lineLabel = (open: OpenDesign, key: string) => {
  const line = open.lines.find((item) => item.key === key);
  return line ? `Line ${line.lineId || key}${line.location ? ` · ${line.location}` : ''}` : key;
};

/** Checks known when the schedule opens; the engine adds its own in the Check step. */
export function openingChecks(open: OpenDesign, skipped: Skipped[] = []): Check[] {
  const checks: Check[] = [];
  for (const item of open.readiness.needs_data)
    checks.push({ id: `data:${item.key}`, severity: 'warning', title: lineLabel(open, item.key), detail: item.reason });
  for (const item of open.readiness.catalog_gaps)
    checks.push({ id: `gap:${item.key}`, severity: 'warning', title: lineLabel(open, item.key), detail: item.reason });
  for (const key of open.readiness.unconfigured)
    checks.push({
      id: `unconfigured:${key}`,
      severity: 'info',
      title: lineLabel(open, key),
      detail: 'Configure this line on the schedule to include it in the design',
    });
  const listed = new Set(checks.map((check) => check.id.split(':').slice(1).join(':')));
  for (const item of skipped)
    if (!listed.has(item.key))
      checks.push({
        id: `skipped:${item.key}`,
        severity: 'warning',
        title: lineLabel(open, item.key),
        detail: item.reason,
      });
  return checks;
}

/** Run-level engine checks (plan §9.3) as panel checks; they follow every edit. */
export function runCheckItems(design: Design, builds: OpenDesign['builds']): Check[] {
  return runChecks(design, builds).map((item) => {
    const run = design.runs.find((candidate) => candidate.key === item.entityRef);
    return {
      id: `${item.code}:${item.entityRef}`,
      severity: item.severity,
      title: run ? `Run ${runLabel(run)}` : item.entityRef,
      detail: item.text,
    };
  });
}

/** A readable name for a check's subject: a run, supply, cabinet, space, line or the design. */
export function entityLabel(design: Design, ref: string): string {
  if (ref === 'project') return 'Design';
  if (ref.startsWith('load:')) {
    const run = design.runs.find((item) => `load:${item.key}` === ref);
    return run ? `Run ${runLabel(run)}` : ref;
  }
  if (ref.startsWith('line:')) {
    const run = design.runs.find((item) => `line:${item.lineKey}` === ref);
    return run ? `Line ${run.lineId}` : ref;
  }
  const equipment = design.project.equipment.find((item) => item.id === ref);
  if (equipment) return equipment.tag;
  const cabinet = design.site.cabinets.find((item) => item.id === ref);
  if (cabinet) return `Cabinet ${cabinet.tag}`;
  const space = design.site.spaces.find((item) => item.id === ref);
  if (space) return space.name;
  const source = design.project.sources.find((item) => item.id === ref);
  return source ? `Circuit ${source.tag}` : ref;
}

/** Engine and designer checks as panel checks. Acknowledged ones drop to notes; run-length repeats are skipped. */
export function engineCheckItems(messages: readonly DesignMessage[], design: Design, runChecked: ReadonlySet<string>) {
  const checks: Check[] = [];
  for (const item of messages) {
    if (
      (item.code === 'TAPE_RUN_TOO_LONG' || item.code === 'MAX_LENGTH_HINT') &&
      runChecked.has(item.entityRef.replace(/^load:/, ''))
    )
      continue;
    checks.push({
      id: `${item.code}:${item.entityRef}:${item.text}`,
      severity: item.override ? 'info' : item.severity,
      title: entityLabel(design, item.entityRef),
      detail: item.override ? `${item.text} Accepted: ${item.override.reason}` : item.text,
    });
  }
  return checks;
}

export function severityCounts(checks: Check[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { error: 0, warning: 0, info: 0 };
  for (const check of checks) counts[check.severity] += 1;
  return counts;
}
