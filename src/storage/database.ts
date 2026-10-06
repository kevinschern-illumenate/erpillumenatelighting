import Dexie, { type EntityTable } from 'dexie';
import { z } from 'zod';
import {
  migrateDraft,
  StoredDraftSchema,
  type Draft,
  type StoredDraft,
} from '../schemas/workspace';
import {
  StoredDraftSchema as LegacyStoredSchema,
  type StoredDraft as LegacyStoredDraft,
} from '../schemas/legacy-workspace';
import { CodeTableSchema, type CodeTable } from '../schemas/reference-data';

export const CodeTableOverrideSchema = z
  .object({ id: z.string().min(1), updatedAt: z.iso.datetime(), table: CodeTableSchema })
  .strict()
  .refine((row) => row.id === row.table.id, 'Table ID must match storage key');
type CodeTableOverride = z.infer<typeof CodeTableOverrideSchema>;

export class RiserDatabase extends Dexie {
  drafts!: EntityTable<LegacyStoredDraft, 'id'>;
  projects!: EntityTable<StoredDraft, 'id'>;
  legacyArchives!: EntityTable<LegacyStoredDraft, 'id'>;
  codeTableOverrides!: EntityTable<CodeTableOverride, 'id'>;
  librarySnapshots!: EntityTable<{ id: string; value: unknown }, 'id'>;
  constructor(name = 'illumenate-riser-scaffold') {
    super(name);
    this.version(1).stores({ drafts: 'id, updatedAt' });
    this.version(2).stores({
      drafts: 'id, updatedAt',
      projects: 'id, updatedAt',
      legacyArchives: 'id, updatedAt',
      codeTableOverrides: 'id, updatedAt',
    });
    this.version(3).stores({ librarySnapshots: 'id' });
  }
}
export const db = new RiserDatabase();

export async function migrateLegacyProjects(database = db): Promise<void> {
  await database.transaction(
    'rw',
    database.drafts,
    database.projects,
    database.legacyArchives,
    async () => {
      for (const raw of await database.drafts.toArray()) {
        const legacy = LegacyStoredSchema.parse(raw);
        if (!(await database.legacyArchives.get(legacy.id)))
          await database.legacyArchives.put(legacy);
        if (!(await database.projects.get(legacy.id)))
          await database.projects.put(
            StoredDraftSchema.parse({ ...legacy, draft: migrateDraft(legacy.draft) }),
          );
      }
    },
  );
}
export async function saveDraft(draft: Draft, database = db): Promise<void> {
  const valid = migrateDraft(draft);
  await database.projects.put(
    StoredDraftSchema.parse({ id: valid.id, draft: valid, updatedAt: new Date().toISOString() }),
  );
}
export async function recentDrafts(database = db): Promise<StoredDraft[]> {
  await migrateLegacyProjects(database);
  return (await database.projects.orderBy('updatedAt').reverse().limit(20).toArray()).map(
    (record) => StoredDraftSchema.parse(record),
  );
}
export async function loadCodeTableOverrides(database = db): Promise<CodeTable[]> {
  return (await database.codeTableOverrides.toArray()).map(
    (row) => CodeTableOverrideSchema.parse(row).table,
  );
}
export async function saveCodeTable(table: CodeTable, database = db): Promise<void> {
  const valid = CodeTableSchema.parse(table);
  await database.codeTableOverrides.put(
    CodeTableOverrideSchema.parse({
      id: valid.id,
      updatedAt: new Date().toISOString(),
      table: valid,
    }),
  );
}
export async function resetCodeTable(id: string, database = db): Promise<void> {
  await database.codeTableOverrides.delete(id);
}
