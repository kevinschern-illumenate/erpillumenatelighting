import type { StepId } from './steps';

/** Keyboard shortcuts (SD-1.7); the help drawer lists them and the shell handles them. */
export const SHORTCUTS: { keys: string[]; action: string }[] = [
  { keys: ['Ctrl', 'S'], action: 'Save now' },
  { keys: ['Ctrl', 'Z'], action: 'Undo' },
  { keys: ['Ctrl', 'Y'], action: 'Redo' },
  { keys: ['['], action: 'Previous step' },
  { keys: [']'], action: 'Next step' },
  { keys: ['Ctrl', 'K'], action: 'Find a step or check' },
  { keys: ['\\'], action: 'Show or hide the checks panel' },
  { keys: ['?'], action: 'Open help' },
  { keys: ['Esc'], action: 'Close a dialog or menu' },
];

/** What to do on each step, in a sentence or two. */
export const STEP_TIPS: Record<StepId, string> = {
  start:
    'Check that every line on the schedule is ready. Lines that need data or are not configured are listed with what to do.',
  spaces:
    'Name each space, place the cabinets that hold supplies, and enter the distance from each space to its cabinet. Distances drive voltage drop.',
  runs: 'Every run from the schedule is listed with its length. Group identical copies and split runs that are too long.',
  power:
    'Drag runs onto supplies and channels, or use the menus. Load bars turn amber near the derating limit and red when overloaded.',
  check: 'Fix every error before you export. Warnings can be accepted with a reason that your reviewer sees.',
  views: 'Draw the riser and export the drawings. Save first so the drawings are kept with the design.',
  finish: 'Write the design back to the schedule, then request a review if one is required.',
  grids: 'Edit circuits, equipment and control links in tables. Changes here are the same design as the guided steps.',
};

export const TOUR_KEY = 'ill-sd:tour-done';
export const TOUR = [
  {
    title: 'Work through the steps',
    text: 'The steps on the left go from Start to Finish. Each shows when it has errors, warnings or is done.',
  },
  {
    title: 'Fix what the checks find',
    text: 'The Checks panel on the right updates as you edit. Choose Go to on any check to jump to the item.',
  },
  {
    title: 'Your work saves itself',
    text: 'Changes save automatically while you work, and are kept in this browser until they do. Ctrl+S saves now.',
  },
];
