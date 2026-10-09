import { produce, type Draft as Mutable } from 'immer';
import { temporal } from 'zundo';
import { createStore } from 'zustand/vanilla';
import type { Design } from '@ill/core-schemas/design';
import { DesignApiError, type DesignApi, type DesignMeta } from './api';
import type { DraftStore } from './drafts';

export const UNDO_LIMIT = 100;

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'conflict' | 'locked' | 'error';

export interface DesignState {
  schedule: string | null;
  design: Design | null;
  meta: DesignMeta | null;
  dirty: boolean;
  saveStatus: SaveStatus;
  saveMessage: string | null;
  load(schedule: string, design: Design, meta: DesignMeta | null): void;
  edit(recipe: (design: Mutable<Design>) => void): void;
  markSaved(meta: Pick<DesignMeta, 'name' | 'revision' | 'modified'>): void;
  setSaveStatus(status: SaveStatus, message?: string | null): void;
}

/**
 * The design being edited. Only ``design`` is tracked for undo (zundo), so saving, loading and
 * status changes never land on the undo stack.
 */
export function createDesignStore() {
  return createStore<DesignState>()(
    temporal(
      (set) => ({
        schedule: null,
        design: null,
        meta: null,
        dirty: false,
        saveStatus: 'idle',
        saveMessage: null,
        load: (schedule, design, meta) =>
          set({
            schedule,
            design,
            meta,
            dirty: false,
            saveStatus: 'idle',
            saveMessage: null,
          }),
        edit: (recipe) =>
          set((state) => {
            if (!state.design) return state;
            return { design: produce(state.design, recipe), dirty: true };
          }),
        markSaved: (saved) =>
          set((state) => ({
            dirty: false,
            saveStatus: 'saved',
            saveMessage: null,
            meta: {
              status: 'Draft',
              schedule_version: state.design?.schedule.version ?? 0,
              is_current: true,
              ...state.meta,
              ...saved,
            },
          })),
        setSaveStatus: (saveStatus, saveMessage = null) => set({ saveStatus, saveMessage }),
      }),
      {
        limit: UNDO_LIMIT,
        partialize: (state) => ({ design: state.design }),
        equality: (past, current) => past.design === current.design,
      },
    ),
  );
}

export type DesignStore = ReturnType<typeof createDesignStore>;

/** Start editing: a newer browser draft for the same saved design wins over the server copy. */
export async function loadDesign(
  store: DesignStore,
  drafts: DraftStore,
  schedule: string,
  saved: { design: Design; meta: DesignMeta | null },
) {
  const draft = await drafts.get(schedule);
  const sameBase =
    draft && draft.designName === (saved.meta?.name ?? null) && draft.baseModified === (saved.meta?.modified ?? null);
  store.getState().load(schedule, sameBase ? draft.design : saved.design, saved.meta);
  if (sameBase) store.setState({ dirty: true });
  store.temporal.getState().clear();
  return { restoredDraft: Boolean(sameBase) };
}

/** Keep the browser draft in step with every edit. */
export function persistDrafts(store: DesignStore, drafts: DraftStore) {
  return store.subscribe((state, previous) => {
    if (!state.schedule || !state.design || !state.dirty || state.design === previous.design) return;
    void drafts.put({
      schedule: state.schedule,
      designName: state.meta?.name ?? null,
      baseModified: state.meta?.modified ?? null,
      design: state.design,
    });
  });
}

/** Save to the server; on success the browser draft is dropped, on conflict it is kept. */
export async function saveDesign(store: DesignStore, api: DesignApi, drafts: DraftStore) {
  const { schedule, design, meta } = store.getState();
  if (!schedule || !design) return null;
  store.getState().setSaveStatus('saving');
  try {
    const result = await api.saveDesign({
      schedule,
      design,
      designName: meta?.name,
      expectedModified: meta?.modified,
    });
    // Edits made while the request was in flight stay unsaved.
    const changedMeanwhile = store.getState().design !== design;
    store.getState().markSaved(result);
    if (changedMeanwhile) {
      const current = store.getState();
      store.setState({ dirty: true });
      await drafts.put({
        schedule,
        designName: result.name,
        baseModified: result.modified,
        design: current.design as Design,
      });
    } else {
      await drafts.remove(schedule);
    }
    return result;
  } catch (error) {
    if (error instanceof DesignApiError && (error.code === 'CONFLICT' || error.code === 'LOCKED')) {
      store.getState().setSaveStatus(error.code === 'CONFLICT' ? 'conflict' : 'locked', error.message);
    } else {
      store.getState().setSaveStatus('error', error instanceof Error ? error.message : String(error));
    }
    return null;
  }
}
