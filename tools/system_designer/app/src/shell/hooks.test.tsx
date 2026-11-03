// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createDesignStore, type DesignStore } from '../design/store';
import { AUTOSAVE_IDLE_MS, AUTOSAVE_MIN_INTERVAL_MS, useAutosave } from './hooks';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let store: DesignStore;
let save: ReturnType<typeof vi.fn>;

function Harness({ enabled = true, step = 'start', online = true }: { enabled?: boolean; step?: string; online?: boolean }) {
  useAutosave({ store, enabled, save, step, online });
  return null;
}

const edit = (value: number) =>
  act(() => {
    store.setState({ dirty: true, design: { edit: value } as never });
  });

beforeEach(() => {
  vi.useFakeTimers();
  store = createDesignStore();
  save = vi.fn(() => {
    store.setState({ saveStatus: 'saving' });
    store.setState({ saveStatus: 'saved', dirty: false });
  });
  root = createRoot(document.createElement('div'));
  act(() => root.render(<Harness />));
});

afterEach(() => {
  act(() => root.unmount());
  vi.useRealTimers();
});

describe('autosave (SD-1.4)', () => {
  it('saves after a pause in editing, at most once a minute', () => {
    edit(1);
    act(() => vi.advanceTimersByTime(AUTOSAVE_IDLE_MS - 1_000));
    edit(2);
    act(() => vi.advanceTimersByTime(AUTOSAVE_IDLE_MS - 1));
    expect(save).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(save).toHaveBeenCalledTimes(1);
    edit(3);
    act(() => vi.advanceTimersByTime(AUTOSAVE_IDLE_MS));
    expect(save).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(AUTOSAVE_MIN_INTERVAL_MS - AUTOSAVE_IDLE_MS));
    expect(save).toHaveBeenCalledTimes(2);
  });

  it('saves when the step changes or the tab is hidden, not when it cannot succeed', () => {
    edit(1);
    act(() => root.render(<Harness step="spaces" />));
    expect(save).toHaveBeenCalledTimes(1);
    edit(2);
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(save).toHaveBeenCalledTimes(2);
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });

    act(() => root.render(<Harness enabled={false} />));
    edit(3);
    act(() => vi.advanceTimersByTime(AUTOSAVE_MIN_INTERVAL_MS * 2));
    expect(save).toHaveBeenCalledTimes(2);
    act(() => root.render(<Harness />));
    act(() => store.setState({ saveStatus: 'conflict' }));
    edit(4);
    act(() => vi.advanceTimersByTime(AUTOSAVE_MIN_INTERVAL_MS * 2));
    expect(save).toHaveBeenCalledTimes(2);
  });

  it('waits for the connection, then saves', () => {
    act(() => root.render(<Harness online={false} />));
    edit(1);
    act(() => vi.advanceTimersByTime(AUTOSAVE_MIN_INTERVAL_MS * 2));
    expect(save).not.toHaveBeenCalled();
    act(() => store.setState({ saveStatus: 'offline' }));
    act(() => root.render(<Harness online />));
    expect(save).toHaveBeenCalledTimes(1);
  });
});
