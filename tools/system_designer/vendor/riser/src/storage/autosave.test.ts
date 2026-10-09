import { afterEach, describe, expect, it, vi } from 'vitest';
import { createDraft, type Draft } from '../schemas/workspace';
import { createAutosaver } from './autosave';

afterEach(() => vi.useRealTimers());

describe('autosave queue', () => {
  it('debounces edits and stores the newest complete snapshot', async () => {
    vi.useFakeTimers();
    const write = vi.fn(async () => {});
    const status = vi.fn();
    const saver = createAutosaver(write, status);
    const first = createDraft();
    const last = { ...first, meta: { ...first.meta, name: 'Latest' } };
    saver.schedule(first);
    saver.schedule(last);
    await vi.advanceTimersByTimeAsync(400);
    expect(write).toHaveBeenCalledExactlyOnceWith(last);
    expect(status).toHaveBeenLastCalledWith('saved');
    saver.dispose();
  });

  it('serializes slow writes without marking a later unsaved edit saved', async () => {
    vi.useFakeTimers();
    const writes: Draft[] = [];
    let release: (() => void) | undefined;
    const status = vi.fn();
    const write = vi.fn(async (draft: Draft) => {
      writes.push(draft);
      if (writes.length === 1)
        await new Promise<void>((resolve) => {
          release = resolve;
        });
    });
    const saver = createAutosaver(write, status);
    const first = createDraft();
    const second = createDraft();
    saver.schedule(first);
    const firstSave = saver.flush();
    await Promise.resolve();
    saver.schedule(second);
    const secondSave = saver.flush();
    expect(writes).toEqual([first]);
    release?.();
    await Promise.all([firstSave, secondSave]);
    expect(writes).toEqual([first, second]);
    expect(status.mock.calls.filter(([s]) => s === 'saved')).toHaveLength(1);
    saver.dispose();
  });

  it('reports failed saves, retains the snapshot, and allows a retry', async () => {
    const write = vi
      .fn()
      .mockRejectedValueOnce(new Error('quota'))
      .mockResolvedValueOnce(undefined);
    const status = vi.fn();
    const saver = createAutosaver(write, status);
    saver.schedule(createDraft());
    await expect(saver.flush()).rejects.toThrow('quota');
    expect(status).toHaveBeenLastCalledWith('error');
    await expect(saver.flush()).resolves.toBeUndefined();
    expect(status).toHaveBeenLastCalledWith('saved');
    saver.dispose();
  });

  it('flushes before the debounce expires for project switches', async () => {
    const write = vi.fn(async () => {});
    const saver = createAutosaver(write, () => {});
    saver.schedule(createDraft());
    await saver.flush();
    expect(write).toHaveBeenCalledTimes(1);
    await saver.flush();
    expect(write).toHaveBeenCalledTimes(1);
    saver.dispose();
  });
});
