import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { Design, Override } from '@ill/core-schemas/design';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { Line } from '@ill/core-schemas/open-design';
import type { Project, ValidationMessage } from '@ill/core-schemas/project';
import type { CodeTable } from '@ill/core-schemas/reference-data';
import type { WireType } from '@ill/core-schemas/wire';
import { calculate } from './calculate';
import { DATA_BY_DEALER_NOTE, dealerItems, loadIdFor, withDerivedLoads } from './derive';
import { message, round, uniqueMessages } from './messages';
import type { EngineResult, RunResult } from './model';
import { reviewHints } from './power';
import { runLabel } from './runs';
import { awgSize, powerTypes } from './wireSelect';

/**
 * Design checks (plan §11, H8.3, WP-3.5): the riser engine on the design's derived loads, run-level
 * checks, and the designer's own Appendix C checks. Voltage-drop targets come from Settings (D5); a
 * project may tighten them, and only an Applications Engineer override loosens them.
 */

export type VdTargetKey = 'vdTargetLowVoltagePct' | 'vdTargetLineVoltagePct' | 'vdTargetLandscapePct';
export type VdLimits = Record<VdTargetKey, number>;

export const VD_TARGETS: readonly { key: VdTargetKey; label: string; setting: string; fallback: number }[] = [
  { key: 'vdTargetLowVoltagePct', label: 'Class 2 low voltage', setting: 'vd_target_class2_pct', fallback: 3 },
  { key: 'vdTargetLineVoltagePct', label: 'Line voltage', setting: 'vd_target_line_pct', fallback: 3 },
  { key: 'vdTargetLandscapePct', label: 'Landscape', setting: 'vd_target_landscape_pct', fallback: 5 },
];

export const LOOSENED = 'VD_TARGET_LOOSENED';
const PROJECT_REF = 'project';

/** The Settings targets (D5), the most a project may use without a staff override. */
export function vdLimits(settings: Record<string, unknown>): VdLimits {
  const limits = {} as VdLimits;
  for (const target of VD_TARGETS) {
    const value = settings[target.setting];
    limits[target.key] = typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : target.fallback;
  }
  return limits;
}

const loosenedOverride = (design: Design) =>
  design.overrides.find((item) => item.code === LOOSENED && item.kind === 'staff-override');

/** Targets the engine uses: the project's where tighter, the Settings' otherwise, unless staff loosened them. */
export function effectiveTargets(design: Design, limits: VdLimits): VdLimits {
  const loosened = Boolean(loosenedOverride(design));
  const targets = {} as VdLimits;
  for (const { key } of VD_TARGETS)
    targets[key] = loosened ? design.project.settings[key] : Math.min(design.project.settings[key], limits[key]);
  return targets;
}

export interface Actor {
  by: string;
  at: string;
  /** Applications Engineer (`design_review`): may loosen targets and override errors. */
  staff: boolean;
}

/** Set a VD target. Tightening is always allowed; loosening past Settings needs staff and a reason. */
export function setVdTarget(
  design: Design,
  key: VdTargetKey,
  value: number,
  limits: VdLimits,
  actor: Actor,
  reason?: string,
) {
  if (!Number.isFinite(value) || value <= 0 || value > 100) throw new Error('Enter a target between 0 and 100%');
  if (value > limits[key]) {
    if (!actor.staff)
      throw new Error(`The target can be ${limits[key]}% or tighter; ask ilLumenate to review a looser target`);
    if (!reason || reason.trim().length < 3) throw new Error('Give a reason for loosening the target');
    design.overrides = design.overrides.filter((item) => item.code !== LOOSENED);
    design.overrides.push({
      code: LOOSENED,
      entityRef: PROJECT_REF,
      kind: 'staff-override',
      reason: reason.trim().slice(0, 1000),
      by: actor.by,
      at: actor.at,
    });
  }
  design.project.settings[key] = value;
  if (VD_TARGETS.every((target) => design.project.settings[target.key] <= limits[target.key]))
    design.overrides = design.overrides.filter((item) => item.code !== LOOSENED);
}

/**
 * Accept a check with a reason (§11.5). Dealers may acknowledge warnings; errors need an Applications
 * Engineer override. Notes need nothing.
 */
export function acknowledge(design: Design, check: ValidationMessage, reason: string, actor: Actor) {
  if (check.severity === 'info') throw new Error('Notes need no acknowledgement');
  if (check.severity === 'error' && !actor.staff)
    throw new Error('Errors must be fixed; ilLumenate can review an exception');
  if (reason.trim().length < 3) throw new Error('Give a reason');
  design.overrides = design.overrides.filter(
    (item) => !(item.code === check.code && item.entityRef === check.entityRef),
  );
  design.overrides.push({
    code: check.code,
    entityRef: check.entityRef,
    kind: check.severity === 'error' ? 'staff-override' : 'acknowledge',
    reason: reason.trim().slice(0, 1000),
    by: actor.by,
    at: actor.at,
  });
}

export function withdrawAcknowledgement(design: Design, code: string, entityRef: string) {
  design.overrides = design.overrides.filter((item) => !(item.code === code && item.entityRef === entityRef));
}

/** Listings accepted for in-wall low-voltage cable (Appendix B.2): CL2 or CL3 and their riser/plenum grades. */
export const IN_WALL_LISTINGS = /^CL[23][RP]?$/;

export interface CheckInput {
  design: Design;
  products: readonly CatalogItem[];
  /** Schedule lines, for third-party dealer data (D8). */
  lines: readonly Line[];
  wires: readonly WireType[];
  codeTables: readonly CodeTable[];
  limits: VdLimits;
  /** The server's D4 answer for the schedule. */
  reviewRequired?: boolean;
  /** The schedule changed since the design was built (H8.4). */
  outOfSync?: boolean;
}

export interface DesignMessage extends ValidationMessage {
  override?: Override;
}

export interface DesignCheck {
  result: EngineResult;
  messages: DesignMessage[];
  targets: VdLimits;
  /** Home-run results by run key. */
  runs: Record<string, RunResult>;
  /** Wires chosen to satisfy the in-wall rule, by engine run id. */
  inWall: Record<string, string>;
}

const SEVERITY = { error: 0, warning: 1, info: 2 } as const;

function projectFor(design: Design, targets: VdLimits): Project {
  const project = withDerivedLoads(design).project;
  return { ...project, settings: { ...project.settings, ...targets } };
}

/** Run the engine and the designer checks on a design. Pure: the same input gives the same answer. */
export function checkDesign(input: CheckInput): DesignCheck {
  const { design } = input;
  const targets = effectiveTargets(design, input.limits);
  const library: LibrarySnapshot = {
    schemaVersion: 1,
    products: [...input.products, ...dealerItems(input.lines)],
    wires: [...input.wires],
    codeTables: [...input.codeTables],
  };
  let project = projectFor(design, targets);
  let result = calculate(project, library);

  // In-wall runs need CL2/CL3-listed cable (Appendix B.2): pick the lightest listed wire that passes.
  const loadKey = new Map(design.runs.map((run) => [loadIdFor(run), run]));
  const inWallLoads = new Set(design.runs.filter((run) => run.envChoice === 'in-wall').map(loadIdFor));
  const listing = new Map(input.wires.map((wire) => [wire.id, wire.listing]));
  const inWall: Record<string, string> = {};
  const extra: ValidationMessage[] = [];
  for (const run of result.runs) {
    if (!inWallLoads.has(run.entityRef) && !inWallLoads.has(run.to.id)) continue;
    if (run.wireTypeId && IN_WALL_LISTINGS.test(listing.get(run.wireTypeId) ?? '')) continue;
    if (design.project.wireOverrides[run.runId]) {
      extra.push(
        message('NO_VALID_WIRE', 'error', run.entityRef, `${run.tag}: in-wall cable must be CL2 or CL3 listed.`),
      );
      continue;
    }
    const listed = run.candidates
      .filter((candidate) => candidate.eligible && IN_WALL_LISTINGS.test(listing.get(candidate.wireTypeId) ?? ''))
      .sort((a, b) => (a.awg ? awgSize(a.awg) : 0) - (b.awg ? awgSize(b.awg) : 0));
    if (listed[0]) inWall[run.runId] = listed[0].wireTypeId;
    else
      extra.push(
        message(
          'NO_VALID_WIRE',
          'error',
          run.entityRef,
          `${run.tag}: no CL2 or CL3 listed cable in the catalog passes for this in-wall run.`,
        ),
      );
  }
  if (Object.keys(inWall).length) {
    const overrides = { ...project.wireOverrides };
    for (const [runId, wireTypeId] of Object.entries(inWall))
      overrides[runId] = { wireTypeId, parallelSets: 1, parallelCommonConductors: 1 };
    project = { ...project, wireOverrides: overrides };
    result = calculate(project, library);
  }

  const spaceNames = new Map(design.site.spaces.map((space) => [space.id, space.name]));
  const unassigned = new Map<string, string[]>();
  const dealerLines = new Map<string, string>();
  for (const run of design.runs) {
    if (!run.assignment) unassigned.set(run.spaceId, [...(unassigned.get(run.spaceId) ?? []), runLabel(run)]);
    if (run.source.kind === 'third-party') dealerLines.set(run.lineKey, run.lineId);
  }
  for (const [spaceId, labels] of unassigned)
    extra.push(
      message(
        'RUN_UNASSIGNED',
        'warning',
        spaceId,
        `${spaceNames.get(spaceId) ?? spaceId}: ${labels.length === 1 ? `${labels[0]} is` : `${labels.length} runs are`} not on a supply or circuit yet${labels.length > 1 ? ` (${labels.slice(0, 4).join(', ')}${labels.length > 4 ? ', …' : ''})` : ''}.`,
      ),
    );
  for (const [lineKey, lineId] of dealerLines)
    extra.push(
      message(
        'DATA_BY_DEALER',
        'info',
        `line:${lineKey}`,
        `Line ${lineId}: watts, voltage and dimming were entered by the dealer.`,
      ),
    );
  // A supply not yet on a panel circuit is a planning gap, not a broken reference.
  const unfed = new Map(
    design.project.equipment.filter((item) => item.fedFrom.ref === 'unassigned').map((item) => [item.id, item.tag]),
  );
  result = {
    ...result,
    messages: result.messages.map((item) =>
      item.code === 'UNRESOLVED_REF' && unfed.has(item.entityRef)
        ? { ...item, severity: 'warning', text: `${unfed.get(item.entityRef)} is not on a panel circuit yet.` }
        : item,
    ),
  };
  const used = new Set(design.project.equipment.map((item) => item.enclosure));
  for (const cabinet of design.site.cabinets)
    if (used.has(cabinet.id) && !cabinet.accessNote.trim())
      extra.push(
        message(
          'SUPPLY_NO_ACCESS',
          'warning',
          cabinet.id,
          `${cabinet.tag}: add an access note so installers can reach the supplies.`,
        ),
      );
  const loosened = loosenedOverride(design);
  if (loosened)
    extra.push(
      message(LOOSENED, 'info', PROJECT_REF, `Voltage-drop targets loosened by ilLumenate: ${loosened.reason}`),
    );
  if (input.outOfSync)
    extra.push(
      message(
        'SCHEDULE_OUT_OF_SYNC',
        'warning',
        PROJECT_REF,
        'The schedule changed since this design was built. Apply the changes on the Start step.',
      ),
    );
  const hints = reviewHints(design);
  if (input.reviewRequired || hints.length)
    extra.push(
      message(
        'REVIEW_REQUIRED',
        'info',
        PROJECT_REF,
        `ilLumenate reviews this design before ordering${hints.length ? `: ${hints.join(', ')}` : ''}.`,
      ),
    );

  const overrides = new Map(design.overrides.map((item) => [`${item.code}|${item.entityRef}`, item]));
  const messages: DesignMessage[] = uniqueMessages([...result.messages, ...extra])
    .map((item) => {
      const override = overrides.get(`${item.code}|${item.entityRef}`);
      return override && item.code !== LOOSENED ? { ...item, override } : item;
    })
    .sort((a, b) => SEVERITY[a.severity] - SEVERITY[b.severity] || a.entityRef.localeCompare(b.entityRef));

  const runs: Record<string, RunResult> = {};
  for (const run of result.runs) {
    const source = loadKey.get(run.entityRef) ?? loadKey.get(run.to.id);
    if (source && (powerTypes as readonly string[]).includes(run.type) && !runs[source.key]) runs[source.key] = run;
  }
  return { result, messages, targets, runs, inWall };
}

/** The next heavier wire that passes, for the "Use a heavier wire" fix; null when there is none. */
export function heavierWire(run: RunResult): string | null {
  const current = run.candidates.find((candidate) => candidate.wireTypeId === run.wireTypeId);
  const size = current?.awg ? awgSize(current.awg) : -1;
  const options = run.candidates
    .filter((candidate) => candidate.awg && awgSize(candidate.awg) > size && candidate.reasons.length === 0)
    .sort((a, b) => awgSize(a.awg!) - awgSize(b.awg!));
  return options[0]?.wireTypeId ?? null;
}

/** Pin a run's wire (an engine run id); `undefined` returns it to automatic selection. */
export function setRunWire(design: Design, runId: string, wireTypeId: string | undefined) {
  if (wireTypeId) design.project.wireOverrides[runId] = { wireTypeId, parallelSets: 1, parallelCommonConductors: 1 };
  else delete design.project.wireOverrides[runId];
}

/** "3.2%" style voltage-drop text; "—" when the engine could not size the run. */
export const percentText = (value: number | null) => (value === null ? '—' : `${round(value, 2)}%`);

export { DATA_BY_DEALER_NOTE };
