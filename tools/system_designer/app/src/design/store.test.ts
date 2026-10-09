import 'fake-indexeddb/auto';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { createDesignApi, DesignApiError, type DesignApi, type DesignMeta } from './api';
import { openDrafts, type DraftStore } from './drafts';
import { createDesignStore, loadDesign, persistDrafts, saveDesign, UNDO_LIMIT } from './store';

const fixture = DesignSchema.parse(
  JSON.parse(
    readFileSync(
      new URL('../../../packages/core-schemas/fixtures/designs/valid/runs-and-site.json', import.meta.url),
      'utf8',
    ),
  ),
) as Design;

const meta: DesignMeta = {
  name: 'SYSD-2026-00001',
  revision: 'A',
  status: 'Draft',
  modified: '2026-10-09 12:00:00.000001',
  schedule_version: fixture.schedule.version,
  is_current: true,
};

let drafts: DraftStore;
let dbIndex = 0;

beforeEach(() => {
  drafts = openDrafts(`test-drafts-${dbIndex++}`);
});

afterEach(() => drafts.close());

function apiStub(saveDesign: DesignApi['saveDesign']): DesignApi {
  return {
    openDesign: vi.fn(),
    createRevision: vi.fn(),
    saveDesign,
  } as unknown as DesignApi;
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 20));

describe('design store', () => {
  it('undoes and redoes design edits only', () => {
    const store = createDesignStore();
    store.getState().load('SCH-FIXTURE', fixture, meta);
    store.temporal.getState().clear();
    store.getState().edit((design) => {
      design.zones.push({
        id: 'z1',
        name: 'Kitchen',
        color: '#112233',
        method: 'DMX512',
      });
    });
    store.getState().setSaveStatus('saving');
    expect(store.getState().dirty).toBe(true);
    expect(store.temporal.getState().pastStates).toHaveLength(1);
    store.temporal.getState().undo();
    expect(store.getState().design?.zones).toEqual(fixture.zones);
    store.temporal.getState().redo();
    expect(store.getState().design?.zones.map((zone) => zone.id)).toEqual([
      ...fixture.zones.map((zone) => zone.id),
      'z1',
    ]);
    expect(fixture.zones.map((zone) => zone.id)).not.toContain('z1');
  });

  it('caps the undo history', () => {
    const store = createDesignStore();
    store.getState().load('SCH-FIXTURE', fixture, meta);
    for (let index = 0; index < UNDO_LIMIT + 20; index += 1) {
      store.getState().edit((design) => {
        design.engineVersion = `riser-${index}`;
      });
    }
    expect(store.temporal.getState().pastStates.length).toBe(UNDO_LIMIT);
  });
});

describe('browser drafts', () => {
  it('survive a reload of the same saved design and are ignored once the server copy moves on', async () => {
    const first = createDesignStore();
    await loadDesign(first, drafts, 'SCH-FIXTURE', { design: fixture, meta });
    const stop = persistDrafts(first, drafts);
    first.getState().edit((design) => {
      design.engineVersion = 'riser-edited';
    });
    await flush();
    stop();

    const reloaded = createDesignStore();
    const restored = await loadDesign(reloaded, drafts, 'SCH-FIXTURE', {
      design: fixture,
      meta,
    });
    expect(restored.restoredDraft).toBe(true);
    expect(reloaded.getState().design?.engineVersion).toBe('riser-edited');
    expect(reloaded.getState().dirty).toBe(true);
    expect(reloaded.temporal.getState().pastStates).toHaveLength(0);

    const newer = createDesignStore();
    const result = await loadDesign(newer, drafts, 'SCH-FIXTURE', {
      design: fixture,
      meta: { ...meta, modified: '2026-10-09 13:00:00.000000' },
    });
    expect(result.restoredDraft).toBe(false);
    expect(newer.getState().design?.engineVersion).toBe(fixture.engineVersion);
  });
});

describe('saving', () => {
  it('sends the base timestamp, records the new one and drops the draft', async () => {
    const store = createDesignStore();
    await loadDesign(store, drafts, 'SCH-FIXTURE', { design: fixture, meta });
    const stop = persistDrafts(store, drafts);
    store.getState().edit((design) => {
      design.engineVersion = 'riser-saved';
    });
    await flush();
    const save = vi.fn<DesignApi['saveDesign']>().mockResolvedValue({
      name: meta.name,
      revision: 'A',
      modified: '2026-10-09 12:05:00.000000',
      build_hash: 'f'.repeat(64),
      summary: {},
    });
    await saveDesign(store, apiStub(save), drafts);
    stop();
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        schedule: 'SCH-FIXTURE',
        designName: meta.name,
        expectedModified: meta.modified,
      }),
    );
    expect(store.getState()).toMatchObject({
      dirty: false,
      saveStatus: 'saved',
    });
    expect(store.getState().meta?.modified).toBe('2026-10-09 12:05:00.000000');
    expect(await drafts.get('SCH-FIXTURE')).toBeUndefined();
  });

  it('keeps the draft on a conflict and reports a locked revision', async () => {
    const store = createDesignStore();
    await loadDesign(store, drafts, 'SCH-FIXTURE', { design: fixture, meta });
    const stop = persistDrafts(store, drafts);
    store.getState().edit((design) => {
      design.engineVersion = 'riser-conflict';
    });
    await flush();
    await saveDesign(
      store,
      apiStub(vi.fn().mockRejectedValue(new DesignApiError('CONFLICT', 'Someone else saved'))),
      drafts,
    );
    expect(store.getState()).toMatchObject({
      saveStatus: 'conflict',
      saveMessage: 'Someone else saved',
      dirty: true,
    });
    expect((await drafts.get('SCH-FIXTURE'))?.design.engineVersion).toBe('riser-conflict');
    await saveDesign(store, apiStub(vi.fn().mockRejectedValue(new DesignApiError('LOCKED', 'In review'))), drafts);
    expect(store.getState().saveStatus).toBe('locked');
    await saveDesign(store, apiStub(vi.fn().mockRejectedValue(new Error('offline'))), drafts);
    expect(store.getState()).toMatchObject({
      saveStatus: 'error',
      saveMessage: 'offline',
    });
    stop();
  });
});

describe('api client', () => {
  it('posts form fields with the CSRF token and unwraps the envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          message: { success: true, data: { name: 'SYSD-1', revision: 'B' } },
        }),
      ),
    );
    const api = createDesignApi({
      apiBase: '/api/method/x.api',
      csrfToken: 'tok',
      fetch: fetchMock,
    });
    expect(await api.createRevision('SYSD-1', 'note')).toEqual({
      name: 'SYSD-1',
      revision: 'B',
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/method/x.api.create_revision');
    expect((init.headers as Record<string, string>)['X-Frappe-CSRF-Token']).toBe('tok');
    expect((init.body as URLSearchParams).get('note')).toBe('note');
  });

  it('turns contract failures and broken responses into DesignApiError', async () => {
    const failing = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            message: { success: false, error: 'Nope', code: 'NOT_FOUND' },
          }),
        ),
      )
      .mockResolvedValueOnce(new Response('<html>', { status: 502 }));
    const api = createDesignApi({
      apiBase: '/m',
      csrfToken: 't',
      fetch: failing,
    });
    await expect(api.openDesign('SCH-1', 'SYSD-9')).rejects.toMatchObject({
      code: 'NOT_FOUND',
      message: 'Nope',
    });
    expect(failing.mock.calls[0]?.[0]).toBe('/m.open_design?schedule=SCH-1&design=SYSD-9');
    await expect(api.openDesign('SCH-1')).rejects.toMatchObject({
      code: 'INTERNAL',
    });
  });
});
