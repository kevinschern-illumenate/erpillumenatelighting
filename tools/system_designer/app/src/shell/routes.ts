import { GRIDS_TAB, STEPS, type StepId } from './steps';

/** Deep links (SD-2.7): #/power opens the Power step; the browser's back button walks the steps. */
const IDS = new Set<string>([...STEPS.map((step) => step.id), GRIDS_TAB.id]);

export function stepFromHash(hash: string): StepId | null {
  const id = hash.replace(/^#\/?/, '').split(/[/?]/)[0] ?? '';
  return IDS.has(id) ? (id as StepId) : null;
}

export const hashFor = (step: StepId) => `#/${step}`;

/** The last step a designer was on, per design, so a reopened design lands where they left it. */
const LAST_STEP_KEY = 'ill-sd:last-step:';
export function readLastStep(key: string): StepId | null {
  try {
    const value = globalThis.localStorage?.getItem(LAST_STEP_KEY + key);
    return value && IDS.has(value) ? (value as StepId) : null;
  } catch {
    return null;
  }
}
export function writeLastStep(key: string, step: StepId) {
  try {
    globalThis.localStorage?.setItem(LAST_STEP_KEY + key, step);
  } catch {
    // Storage may be unavailable; the designer then opens on Start.
  }
}
