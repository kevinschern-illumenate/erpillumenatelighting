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

export type StepId = (typeof STEPS)[number]['id'];
export type Mode = 'guided' | 'engineering';
