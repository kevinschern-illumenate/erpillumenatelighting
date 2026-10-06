import { beforeEach, describe, expect, it } from 'vitest';
import { createDraft } from '../schemas/workspace';
import { activateDraft, useProjectStore } from './project-store';

describe('project history', () => {
  beforeEach(() => activateDraft(createDraft()));

  it('undoes and redoes edits across form sections', () => {
    const { editMeta, editSetting, editNote } = useProjectStore.getState();
    editMeta('name', 'Gallery');
    editSetting('psuDeratePct', 75);
    editNote('Coordinate access panels');
    const history = useProjectStore.temporal.getState();
    history.undo();
    expect(useProjectStore.getState().draft.scratchNote).toBe('');
    history.undo();
    expect(useProjectStore.getState().draft.settings.psuDeratePct).toBe(80);
    history.undo();
    expect(useProjectStore.getState().draft.meta.name).toBe('Untitled project');
    history.redo(3);
    expect(useProjectStore.getState().draft.meta.name).toBe('Gallery');
    expect(useProjectStore.getState().draft.settings.psuDeratePct).toBe(75);
    expect(useProjectStore.getState().draft.scratchNote).toBe('Coordinate access panels');
  });

  it('does not create history for no-op changes', () => {
    const s = useProjectStore.getState();
    s.editMeta('name', s.draft.meta.name);
    s.editSetting('psuDeratePct', 80);
    s.editNote('');
    expect(useProjectStore.temporal.getState().pastStates).toHaveLength(0);
  });

  it('invalidates redo when branching after undo', () => {
    useProjectStore.getState().editMeta('name', 'Old branch');
    useProjectStore.temporal.getState().undo();
    useProjectStore.getState().editMeta('name', 'New branch');
    expect(useProjectStore.temporal.getState().futureStates).toHaveLength(0);
  });

  it('clears history at project boundaries and validates loads before mutation', () => {
    useProjectStore.getState().editMeta('name', 'A');
    const second = createDraft();
    activateDraft(second);
    expect(useProjectStore.temporal.getState().pastStates).toHaveLength(0);
    expect(useProjectStore.getState().draft.id).toBe(second.id);
    expect(() => activateDraft({ schemaVersion: 99 })).toThrow('Unsupported');
    expect(useProjectStore.getState().draft.id).toBe(second.id);
  });

  it('rejects invalid values without modifying state', () => {
    expect(() => useProjectStore.getState().editSetting('psuDeratePct', 101)).toThrow();
    expect(() => useProjectStore.getState().editMeta('date', 'invalid')).toThrow();
    expect(useProjectStore.getState().draft.settings.psuDeratePct).toBe(80);
  });

  it('bounds history at 100 edits', () => {
    for (let index = 0; index < 120; index++)
      useProjectStore.getState().editMeta('number', String(index));
    expect(useProjectStore.temporal.getState().pastStates).toHaveLength(100);
  });
});
