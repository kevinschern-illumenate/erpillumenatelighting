import { afterEach, describe, expect, it } from 'vitest';
import Dexie from 'dexie';
import { createDraft as createLegacyDraft } from '../schemas/legacy-workspace';
import { seedCodeTables } from '../data/seeds';
import { createDraft } from '../schemas/workspace';
import {
  loadCodeTableOverrides,
  migrateLegacyProjects,
  recentDrafts,
  resetCodeTable,
  RiserDatabase,
  saveCodeTable,
  saveDraft,
} from './database';

const databases: RiserDatabase[] = [];
function freshDatabase() {
  const database = new RiserDatabase(`test-${crypto.randomUUID()}`);
  databases.push(database);
  return database;
}
afterEach(async () => {
  await Promise.all(databases.splice(0).map((database) => database.delete()));
});

describe('Phase 0 migration and editable reference tables', () => {
  it('upgrades a real v1 database, archives originals, and never overwrites later edits', async () => {
    const database = freshDatabase();
    const legacyDb = new Dexie(database.name);
    legacyDb.version(1).stores({ drafts: 'id, updatedAt' });
    const legacy = createLegacyDraft();
    legacy.meta = {
      ...legacy.meta,
      name: 'Preserve all metadata',
      number: '26-042',
      client: 'Owner',
      siteAddress: '123 Main',
      designer: 'KD',
      checker: 'AB',
      brand: '206',
      sheetPrefix: 'LR-',
      stamp: 'FOR REFERENCE',
    };
    legacy.defaults = { sheetSize: 'ANSI_B', flow: 'TB', psuDeratePct: 75 };
    legacy.scratchNote = 'Original note';
    const original = { id: legacy.id, draft: legacy, updatedAt: '2026-09-01T00:00:00.000Z' };
    await legacyDb.table('drafts').put(original);
    legacyDb.close();
    const [migrated] = await recentDrafts(database);
    expect(migrated?.draft.meta).toEqual(legacy.meta);
    expect(migrated?.draft.settings.sheet).toEqual({ size: 'ANSI_B', flow: 'TB' });
    expect(migrated?.draft.settings.psuDeratePct).toBe(75);
    expect(migrated?.draft.scratchNote).toBe(legacy.scratchNote);
    expect(migrated?.draft.schemaVersion).toBe(1);
    expect(await database.drafts.get(legacy.id)).toEqual(original);
    expect(await database.legacyArchives.get(legacy.id)).toEqual(original);
    const changed = migrated!.draft;
    changed.meta.name = 'Edited after migration';
    await saveDraft(changed, database);
    await migrateLegacyProjects(database);
    expect((await database.projects.get(legacy.id))?.draft.meta.name).toBe(
      'Edited after migration',
    );
    expect(await database.legacyArchives.get(legacy.id)).toEqual(original);
    expect(await database.projects.count()).toBe(1);
  });

  it('rolls back all migration writes when any original record is invalid', async () => {
    const database = freshDatabase();
    const good = createLegacyDraft();
    const bad = createLegacyDraft();
    await database.drafts.put({ id: good.id, draft: good, updatedAt: new Date().toISOString() });
    await database.table('drafts').put({
      id: bad.id,
      draft: { ...bad, schemaVersion: 99 },
      updatedAt: new Date().toISOString(),
    });
    await expect(recentDrafts(database)).rejects.toThrow();
    expect(await database.drafts.count()).toBe(2);
    expect(await database.projects.count()).toBe(0);
    expect(await database.legacyArchives.count()).toBe(0);
  });

  it('persists validated code overrides across reopen, rejects corruption, and restores seeds', async () => {
    const database = freshDatabase();
    const table = structuredClone(seedCodeTables[0]!);
    table.comment = 'Locally reviewed reference';
    await saveCodeTable(table, database);
    database.close();
    await database.open();
    expect(await loadCodeTableOverrides(database)).toEqual([table]);
    await expect(
      saveCodeTable({ ...table, units: 'invalid' } as unknown as typeof table, database),
    ).rejects.toThrow();
    expect(await loadCodeTableOverrides(database)).toEqual([table]);
    expect(seedCodeTables[0]!.comment).not.toBe(table.comment);
    await database.table('codeTableOverrides').update(table.id, { 'table.units': 'invalid' });
    await expect(loadCodeTableOverrides(database)).rejects.toThrow();
    await resetCodeTable(table.id, database);
    expect(await loadCodeTableOverrides(database)).toEqual([]);
  });
});

describe('IndexedDB drafts', () => {
  it('persists and restores exact editable state across a database reopen', async () => {
    const database = freshDatabase();
    const draft = createDraft();
    draft.meta.name = 'Lobby';
    draft.scratchNote = 'Access through ceiling';
    await saveDraft(draft, database);
    database.close();
    await database.open();
    expect((await recentDrafts(database))[0]?.draft).toEqual(draft);
  });

  it('upserts the same project and preserves separate projects', async () => {
    const database = freshDatabase();
    const first = createDraft();
    const second = createDraft();
    await saveDraft(first, database);
    await saveDraft(second, database);
    first.meta.name = 'Revised';
    await saveDraft(first, database);
    expect(await database.projects.count()).toBe(2);
    expect((await database.projects.get(first.id))?.draft.meta.name).toBe('Revised');
    expect((await database.projects.get(second.id))?.draft).toEqual(second);
  });

  it('surfaces corrupt storage instead of treating it as a new empty workspace', async () => {
    const database = freshDatabase();
    const draft = createDraft();
    await saveDraft(draft, database);
    // Model an external/older app writing a record outside our validation boundary.
    await database.table<{ draft: { schemaVersion: number } }>('projects').update(draft.id, {
      'draft.schemaVersion': 999,
    });
    await expect(recentDrafts(database)).rejects.toThrow();
    expect(await database.projects.count()).toBe(1);
  });
});
