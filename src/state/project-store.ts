import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { temporal } from 'zundo';
import { createDraft, DraftSchema, migrateDraft, type Draft } from '../schemas/workspace';

type DraftState = { draft: Draft };
type Actions = {
  editMeta: <K extends keyof Draft['meta']>(key: K, value: Draft['meta'][K]) => void;
  editSetting: <K extends keyof Draft['settings']>(key: K, value: Draft['settings'][K]) => void;
  editNote: (value: string) => void;
  loadDraft: (draft: unknown) => void;
  updateProject: (patch: Partial<Draft>) => void;
};

export const useProjectStore = create<DraftState & Actions>()(
  temporal(
    immer((set) => ({
      draft: createDraft(),
      editMeta: (key, value) =>
        set((state) => {
          const next = DraftSchema.parse({
            ...state.draft,
            meta: { ...state.draft.meta, [key]: value },
          });
          if (state.draft.meta[key] !== next.meta[key]) state.draft = next;
        }),
      editSetting: (key, value) =>
        set((state) => {
          const next = DraftSchema.parse({
            ...state.draft,
            settings: { ...state.draft.settings, [key]: value },
          });
          if (JSON.stringify(state.draft.settings[key]) !== JSON.stringify(next.settings[key]))
            state.draft = next;
        }),
      editNote: (value) =>
        set((state) => {
          if (state.draft.scratchNote !== value)
            state.draft = DraftSchema.parse({ ...state.draft, scratchNote: value });
        }),
      loadDraft: (draft) => set({ draft: migrateDraft(draft) }),
      updateProject: (patch) =>
        set((state) => {
          const next = DraftSchema.parse({ ...state.draft, ...patch });
          if (JSON.stringify(next) !== JSON.stringify(state.draft)) state.draft = next;
        }),
    })),
    { partialize: ({ draft }) => ({ draft }), equality: (a, b) => a.draft === b.draft, limit: 100 },
  ),
);

export function activateDraft(draft: unknown) {
  useProjectStore.getState().loadDraft(draft);
  useProjectStore.temporal.getState().clear();
}
