import type { StepId } from './steps';

/** Where each check code is fixed when the Check step cannot fix it in place (SD-2.2). */
const POWER = { step: 'power', label: 'Open Power' } as const;
const SPACES = { step: 'spaces', label: 'Open Spaces' } as const;
const RUNS = { step: 'runs', label: 'Open Runs' } as const;
const START = { step: 'start', label: 'Open Start' } as const;

export const FIX_STEP: Record<string, { step: StepId; label: string }> = {
  PSU_OVERLOAD: POWER,
  PSU_ABOVE_DERATE: POWER,
  CHANNEL_OVERCURRENT: POWER,
  BREAKER_OVERLOAD: POWER,
  CLASS2_OVER_100VA: POWER,
  VOLTAGE_MISMATCH: POWER,
  DRIVE_MISMATCH: POWER,
  PROTOCOL_MISMATCH: POWER,
  RUN_UNASSIGNED: POWER,
  UNRESOLVED_REF: POWER,
  INPUT_V_OUT_OF_RANGE: POWER,
  DEVICE_CAPACITY: POWER,
  DMX_ADDRESS_OVERLAP: POWER,
  DMX_ADDRESS_OVERFLOW: POWER,
  DMX_TOPOLOGY: POWER,
  DMX_NO_TERMINATOR: POWER,
  ZONE_NO_CONTROL: POWER,
  DMX_RUN_NO_DECODER: POWER,
  CONTROL_UNUSED: POWER,
  SUPPLY_NO_ACCESS: SPACES,
  NO_VALID_WIRE: SPACES,
  VD_OVER_TARGET: SPACES,
  TAPE_UNDERVOLTAGE: SPACES,
  TAPE_RUN_TOO_LONG: RUNS,
  MAX_LENGTH_HINT: RUNS,
  INVALID_SPEC: RUNS,
  SCHEDULE_OUT_OF_SYNC: START,
  DATA: START,
  GAP: START,
  UNCONFIGURED: START,
  SKIPPED: START,
};

/** The step a check belongs to: where it is fixed, or the Check step for design-wide results. */
export function stepForCode(code: string | undefined): StepId {
  return (code && FIX_STEP[code]?.step) || 'check';
}

/** CSS selector for the element that shows an entity on a step; steps tag them with data-entity. */
export function entitySelector(ref: string) {
  return `[data-entity~="${ref.replace(/["\\]/g, '\\$&')}"]`;
}

/** The entity refs runs are known by: key in the run-level checks, load:key and line:key in the engine's. */
export const runEntities = (runs: readonly { key: string; lineKey: string }[]) =>
  [...new Set(runs.flatMap((run) => [run.key, `load:${run.key}`, `line:${run.lineKey}`]))].join(' ');

/**
 * Scroll an entity into view on the current screen and flash it, so "Go to item" lands on the thing
 * the check is about. Returns false when the step does not show that entity.
 */
export function revealEntity(root: ParentNode, ref: string): boolean {
  const target = root.querySelector<HTMLElement>(entitySelector(ref));
  if (!target) return false;
  target.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  target.classList.remove('sd-flash');
  // Restart the animation when the same item is revealed twice.
  void target.offsetWidth;
  target.classList.add('sd-flash');
  const focusable = target.matches('button, a, input, select, textarea, [tabindex]')
    ? target
    : target.querySelector<HTMLElement>('button, a, input, select, textarea, [tabindex]');
  focusable?.focus({ preventScroll: true });
  setTimeout(() => target.classList.remove('sd-flash'), 2400);
  return true;
}
