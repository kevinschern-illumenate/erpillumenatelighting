/** The guided steps (plan H9). Engineering mode shows the same screens as tabs. */
export const STEPS = [
  { id: 'start', label: 'Start', summary: 'Check the schedule is ready and review what the design needs.' },
  { id: 'spaces', label: 'Spaces', summary: 'Name the spaces, place cabinets and set distances to them.' },
  {
    id: 'runs',
    label: 'Runs',
    summary: 'Review every run from the schedule, group identical copies and check run lengths.',
  },
  { id: 'power', label: 'Power', summary: 'Assign runs to supplies and circuits, and set dimming zones.' },
  { id: 'check', label: 'Check', summary: 'Fix voltage drop, loading and control issues before you export.' },
  { id: 'views', label: 'Views', summary: 'Export the riser and other drawings for this design.' },
  { id: 'finish', label: 'Finish', summary: 'Write the design back to the schedule and request a review.' },
] as const;

/** Engineering mode adds the riser's tables and every project setting (plan §7, WP-3.8). */
export const GRIDS_TAB = {
  id: 'grids',
  label: 'Grids',
  summary: 'Edit circuits, equipment and control links in tables, and the project settings.',
} as const;

export type StepId = (typeof STEPS)[number]['id'] | typeof GRIDS_TAB.id;
export type Mode = 'guided' | 'engineering';

/** A dealer's choice to show engineering mode, kept in this browser. Staff always have it. */
export const ENGINEERING_OPT_IN_KEY = 'ill-sd:engineering-opt-in';
export function readOptIn(): boolean {
  try {
    return globalThis.localStorage?.getItem(ENGINEERING_OPT_IN_KEY) === '1';
  } catch {
    return false;
  }
}
export function writeOptIn(value: boolean) {
  try {
    if (value) globalThis.localStorage?.setItem(ENGINEERING_OPT_IN_KEY, '1');
    else globalThis.localStorage?.removeItem(ENGINEERING_OPT_IN_KEY);
  } catch {
    // Private windows may refuse storage; the choice then lasts for this visit only.
  }
}
