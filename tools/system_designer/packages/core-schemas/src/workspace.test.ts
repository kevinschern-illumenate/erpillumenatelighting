import { describe, expect, it } from 'vitest';
import { createDraft, DraftSchema, migrateDraft, StoredDraftSchema } from './workspace';

describe('scaffold schema boundary', () => {
  it('preserves the supplied numbering, sheet, and PSU defaults', () => {
    const draft = createDraft();
    expect(draft.meta.sheetPrefix).toBe('L-');
    expect(draft.settings.sheet).toEqual({ size: 'ARCH_D', flow: 'LR' });
    expect(draft.settings.psuDeratePct).toBe(80);
    expect(DraftSchema.safeParse(draft).success).toBe(true);
    expect(createDraft().id).not.toBe(draft.id);
  });
  it('round-trips version one without silently stripping fields', () => {
    const draft = createDraft();
    expect(migrateDraft(JSON.parse(JSON.stringify(draft)))).toEqual(draft);
    expect(() => migrateDraft({ ...draft, unknownField: true })).toThrow();
  });
  it('rejects future versions and malformed inputs', () => {
    expect(() => migrateDraft({ schemaVersion: 2 })).toThrow('Unsupported draft version 2');
    expect(() => migrateDraft(null)).toThrow();
  });
  it('rejects mismatched record IDs', () => {
    const draft = createDraft();
    expect(
      StoredDraftSchema.safeParse({
        id: crypto.randomUUID(),
        draft,
        updatedAt: new Date().toISOString(),
      }).success,
    ).toBe(false);
  });
});
