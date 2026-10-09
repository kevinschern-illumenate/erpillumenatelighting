import type { Project } from '@ill/core-schemas/project';
import type { DesignCheck } from './designCheck';
import { DATA_BY_DEALER_NOTE } from './derive';

/**
 * The riser drawn from a design (plan §12.1, WP-3.7): the project the checks ran on, with the title
 * block filled from the ERP, the chosen sheet and stamp, and the notes engineering outputs carry.
 */

/** Stamps a riser may carry; REVIEWED BY ILLUMENATE only on an approved revision (plan §22.3). */
export const RISER_STAMPS = ['PRELIMINARY', 'NOT FOR CONSTRUCTION', 'FOR REFERENCE', 'REVIEWED BY ILLUMENATE'] as const;
export type RiserStamp = (typeof RISER_STAMPS)[number];
export const DEFAULT_STAMP: RiserStamp = 'PRELIMINARY';

export const RISER_SHEETS = [
  { size: 'ANSI_A', label: 'Letter (11 × 8.5 in)' },
  { size: 'ANSI_B', label: 'Tabloid (17 × 11 in)' },
  { size: 'ARCH_C', label: 'ARCH C (24 × 18 in)' },
  { size: 'ARCH_D', label: 'ARCH D (36 × 24 in)' },
  { size: 'ANSI_D', label: 'ANSI D (34 × 22 in)' },
] as const;
export type RiserSheet = (typeof RISER_SHEETS)[number]['size'];

export const DESIGN_AID_NOTE =
  'Design aid. Verify against product documentation and local code. Line-voltage work by a licensed electrician.';
export const dealerDataNote = (dealer: string) =>
  `Third-party product data entered by ${dealer.trim() || 'the dealer'}; not verified by ilLumenate.`;

export function allowedStamps(approved: boolean): RiserStamp[] {
  return RISER_STAMPS.filter((stamp) => approved || stamp !== 'REVIEWED BY ILLUMENATE');
}

export interface RiserMeta {
  projectName: string;
  projectNumber: string;
  /** The dealer (the schedule's customer). */
  client: string;
  siteAddress: string;
  designer: string;
  /** The Applications Engineer who approved the revision; blank before approval. */
  checker: string;
  /** ISO date. */
  date: string;
  /** Design revision letter. */
  revision: string;
  stamp: RiserStamp;
  sheet: RiserSheet;
  approved: boolean;
}

const cut = (value: string, max: number) => value.trim().slice(0, max);

/** The project to draw. A stamp the revision may not carry falls back to PRELIMINARY. */
export function riserProject(check: DesignCheck, meta: RiserMeta): Project {
  const project = check.project;
  const stamp = allowedStamps(meta.approved).includes(meta.stamp) ? meta.stamp : DEFAULT_STAMP;
  const notes = [...project.generalNotes];
  if (!notes.includes(DESIGN_AID_NOTE)) notes.unshift(DESIGN_AID_NOTE);
  const dealerNote = dealerDataNote(meta.client);
  if (project.loads.some((load) => load.notes === DATA_BY_DEALER_NOTE) && !notes.includes(dealerNote))
    notes.push(dealerNote);
  const revisions = project.revisions.some((item) => item.rev === meta.revision)
    ? project.revisions
    : [
        ...project.revisions,
        {
          rev: meta.revision,
          date: meta.date,
          description: `System Designer revision ${meta.revision}`,
          by: cut(meta.designer, 100),
        },
      ];
  return {
    ...project,
    meta: {
      ...project.meta,
      name: cut(meta.projectName, 160) || project.meta.name,
      number: cut(meta.projectNumber, 80),
      client: cut(meta.client, 160),
      siteAddress: cut(meta.siteAddress, 300),
      designer: cut(meta.designer, 100),
      checker: meta.approved ? cut(meta.checker, 100) : '',
      date: meta.date,
      stamp,
    },
    settings: { ...project.settings, sheet: { ...project.settings.sheet, size: meta.sheet } },
    generalNotes: notes,
    revisions,
  };
}
