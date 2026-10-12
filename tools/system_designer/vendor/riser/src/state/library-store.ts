import { create } from 'zustand';
import { temporal } from 'zundo';
import { seedCodeTables, seedProducts, seedWires } from '../data/seeds';
import { LibrarySnapshotSchema, type LibrarySnapshot } from '../schemas/library';

export const seedLibrary = (): LibrarySnapshot =>
  structuredClone({
    schemaVersion: 1,
    products: seedProducts,
    wires: seedWires,
    codeTables: seedCodeTables,
  });
export const useLibraryStore = create<{
  library: LibrarySnapshot;
  ready: boolean;
  status: 'saved' | 'saving' | 'error';
  error: string;
  replace: (library: unknown) => void;
  update: <K extends 'products' | 'wires' | 'codeTables'>(key: K, rows: LibrarySnapshot[K]) => void;
}>()(
  temporal(
    (set) => ({
      library: seedLibrary(),
      ready: false,
      status: 'saving',
      error: '',
      replace: (value) => set({ library: LibrarySnapshotSchema.parse(value) }),
      update: (key, rows) =>
        set((s) => {
          const library = LibrarySnapshotSchema.parse({ ...s.library, [key]: rows });
          return JSON.stringify(library) === JSON.stringify(s.library) ? s : { library };
        }),
    }),
    {
      partialize: ({ library }) => ({ library }),
      equality: (a, b) => a.library === b.library,
      limit: 100,
    },
  ),
);
