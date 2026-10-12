import Dexie, { type EntityTable } from 'dexie';
import type { Design } from '@ill/core-schemas/design';

/** An unsaved design kept in the browser so edits survive a reload or a lost connection. */
export interface Draft {
  schedule: string;
  /** The saved design this draft edits, or null before the first save. */
  designName: string | null;
  /** ``modified`` of the saved design when editing began; a save sends it to detect conflicts. */
  baseModified: string | null;
  design: Design;
  savedAt: string;
}

export const DRAFT_DB_NAME = 'ill-system-designer';

class DraftDatabase extends Dexie {
  drafts!: EntityTable<Draft, 'schedule'>;

  constructor(name: string) {
    super(name);
    this.version(1).stores({ drafts: 'schedule, savedAt' });
  }
}

export function openDrafts(name = DRAFT_DB_NAME) {
  const db = new DraftDatabase(name);
  return {
    get: (schedule: string) => db.drafts.get(schedule),
    put: (draft: Omit<Draft, 'savedAt'>, now = new Date()) => db.drafts.put({ ...draft, savedAt: now.toISOString() }),
    remove: (schedule: string) => db.drafts.delete(schedule),
    close: () => db.close(),
  };
}

export type DraftStore = ReturnType<typeof openDrafts>;
