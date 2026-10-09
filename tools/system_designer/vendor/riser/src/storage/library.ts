import { db, loadCodeTableOverrides, type RiserDatabase } from './database';
import { LibrarySnapshotSchema, type LibrarySnapshot } from '../schemas/library';
import { seedLibrary } from '../state/library-store';

export async function loadLibrary(database: RiserDatabase = db): Promise<LibrarySnapshot> {
  const saved = await database.librarySnapshots.get('local');
  if (saved) return LibrarySnapshotSchema.parse(saved.value);
  const library = seedLibrary();
  const overrides = await loadCodeTableOverrides(database);
  library.codeTables = library.codeTables.map((t) => overrides.find((o) => o.id === t.id) ?? t);
  return LibrarySnapshotSchema.parse(library);
}
export async function saveLibrary(value: unknown, database: RiserDatabase = db): Promise<void> {
  const library = LibrarySnapshotSchema.parse(value);
  await database.librarySnapshots.put({ id: 'local', value: library });
}
