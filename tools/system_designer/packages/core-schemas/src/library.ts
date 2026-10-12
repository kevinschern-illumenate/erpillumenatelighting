import { z } from 'zod';
import { ProductLibrarySchema } from './catalog';
import { WireLibrarySchema } from './wire';
import { CodeTableLibrarySchema } from './reference-data';

export const LibrarySnapshotSchema = z
  .object({
    schemaVersion: z.literal(1),
    products: ProductLibrarySchema,
    wires: WireLibrarySchema,
    codeTables: CodeTableLibrarySchema,
  })
  .strict();
export type LibrarySnapshot = z.infer<typeof LibrarySnapshotSchema>;
