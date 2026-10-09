import type { LibrarySnapshot } from '@ill/core-schemas/library';
import { seedCodeTables, seedProducts, seedWires } from './seeds';

/** The riser's seed library (EXAMPLE products and wires). Test and reference use only; never dealer data. */
export const seedLibrary = (): LibrarySnapshot =>
  structuredClone({
    schemaVersion: 1,
    products: seedProducts,
    wires: seedWires,
    codeTables: seedCodeTables,
  });
