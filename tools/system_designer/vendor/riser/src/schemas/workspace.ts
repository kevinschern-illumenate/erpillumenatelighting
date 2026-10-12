import { z } from 'zod';
import { ProjectSchema, ProjectSettingsSchema } from './project';
import {
  DraftSchema as LegacyDraftSchema,
  createDraft as createLegacyDraft,
} from './legacy-workspace';
import notesJson from '../data/general-notes.seed.json';
import { NotesLibrarySchema } from './reference-data';

// UI names remain stable, but persisted projects now use the complete v1 Project schema.
export const DraftSchema = ProjectSchema;
export type Draft = z.infer<typeof DraftSchema>;
export const StoredDraftSchema = z
  .object({ id: z.uuid(), updatedAt: z.iso.datetime(), draft: DraftSchema })
  .strict()
  .refine((record) => record.id === record.draft.id, 'Draft ID does not match storage key');
export type StoredDraft = z.infer<typeof StoredDraftSchema>;

export function migrateDraft(input: unknown): Draft {
  const version = z.object({ schemaVersion: z.number().int() }).parse(input).schemaVersion;
  if (version === 1) return ProjectSchema.parse(input);
  if (version !== 0)
    throw new Error(`Unsupported draft version ${version}. This app supports versions 0 and 1.`);
  const legacy = LegacyDraftSchema.parse(input);
  return ProjectSchema.parse({
    schemaVersion: 1,
    id: legacy.id,
    meta: legacy.meta,
    settings: ProjectSettingsSchema.parse({
      sheet: { size: legacy.defaults.sheetSize, flow: legacy.defaults.flow },
      psuDeratePct: legacy.defaults.psuDeratePct,
    }),
    sources: [],
    equipment: [],
    loads: [],
    controlLinks: [],
    wireOverrides: {},
    layoutOverrides: {},
    wireTagMap: {},
    generalNotes: NotesLibrarySchema.parse(notesJson).map((note) => note.text),
    keyNotes: [],
    revisions: [],
    scratchNote: legacy.scratchNote,
  });
}
export function createDraft(): Draft {
  return migrateDraft(createLegacyDraft());
}
