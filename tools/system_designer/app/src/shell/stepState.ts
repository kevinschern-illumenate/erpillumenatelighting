import { stepForCode } from './checkTargets';
import type { Check } from './open';
import { GRIDS_TAB, STEPS, type StepId } from './steps';

/** What the step rail shows for a step (SD-2.1). */
export type StepStatus = 'error' | 'warning' | 'done' | 'todo';
export interface StepState {
  status: StepStatus;
  errors: number;
  warnings: number;
}

/**
 * Each step's state from the open checks: errors first, then warnings, then whether the designer has
 * been there. A step with nothing to fix that has been visited is done.
 */
export function stepStates(checks: readonly Check[], visited: ReadonlySet<StepId>): Record<StepId, StepState> {
  const states = {} as Record<StepId, StepState>;
  for (const step of [...STEPS, GRIDS_TAB]) states[step.id] = { status: 'todo', errors: 0, warnings: 0 };
  for (const check of checks) {
    const state = states[stepForCode(check.code)];
    if (check.severity === 'error') state.errors += 1;
    else if (check.severity === 'warning') state.warnings += 1;
  }
  for (const [id, state] of Object.entries(states) as [StepId, StepState][])
    state.status = state.errors ? 'error' : state.warnings ? 'warning' : visited.has(id) ? 'done' : 'todo';
  return states;
}

/** Words for a step's state, read after its name by screen readers. */
export function stepStateLabel(state: StepState): string {
  const parts: string[] = [];
  if (state.errors) parts.push(`${state.errors} ${state.errors === 1 ? 'error' : 'errors'}`);
  if (state.warnings) parts.push(`${state.warnings} ${state.warnings === 1 ? 'warning' : 'warnings'}`);
  if (!parts.length) return state.status === 'done' ? 'done' : 'not started';
  return parts.join(', ');
}
