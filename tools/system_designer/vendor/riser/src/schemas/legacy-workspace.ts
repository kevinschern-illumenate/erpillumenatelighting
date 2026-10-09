import { z } from 'zod';

// Phase 0 metadata draft. This is deliberately NOT the complete Phase 1 Project schema.
// Storage keeps its own version so bootstrap records cannot masquerade as engineering projects.
export const DraftSchema = z
  .object({
    schemaVersion: z.literal(0),
    id: z.string().uuid(),
    meta: z
      .object({
        name: z.string().max(160),
        number: z.string().max(80),
        client: z.string().max(160),
        siteAddress: z.string().max(300),
        designer: z.string().max(100),
        checker: z.string().max(100),
        date: z.iso.date(),
        brand: z.enum(['illumenate', '206']),
        sheetPrefix: z.string().min(1).max(12),
        stamp: z.enum(['NONE', 'FOR REFERENCE', 'NOT FOR CONSTRUCTION', 'PRELIMINARY']),
      })
      .strict(),
    defaults: z
      .object({
        sheetSize: z.enum(['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D']),
        flow: z.enum(['LR', 'TB']),
        psuDeratePct: z.number().min(1).max(100),
      })
      .strict(),
    scratchNote: z.string().max(4000),
  })
  .strict();

export type Draft = z.infer<typeof DraftSchema>;
export const StoredDraftSchema = z
  .object({
    id: z.string().uuid(),
    updatedAt: z.string().datetime(),
    draft: DraftSchema,
  })
  .strict()
  .refine((record) => record.id === record.draft.id, 'Draft ID does not match storage key');
export type StoredDraft = z.infer<typeof StoredDraftSchema>;

export function createDraft(): Draft {
  const now = new Date();
  const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  return DraftSchema.parse({
    schemaVersion: 0,
    id: crypto.randomUUID(),
    meta: {
      name: 'Untitled project',
      number: '',
      client: '',
      siteAddress: '',
      designer: '',
      checker: '',
      date,
      brand: 'illumenate',
      sheetPrefix: 'L-',
      stamp: 'PRELIMINARY',
    },
    defaults: { sheetSize: 'ARCH_D', flow: 'LR', psuDeratePct: 80 },
    scratchNote: '',
  });
}

// Explicit migration boundary from day one; unknown versions fail closed.
export function migrateDraft(input: unknown): Draft {
  const version = z.object({ schemaVersion: z.number().int() }).parse(input).schemaVersion;
  switch (version) {
    case 0:
      return DraftSchema.parse(input);
    default:
      throw new Error(`Unsupported draft version ${version}. This app supports version 0.`);
  }
}
