import { useEffect, useMemo } from 'react';
import { create } from 'zustand';
import { DrawingSchema, type Drawing } from '../drawing/model';
import { useEngine } from './use-engine';

const useLayoutState = create<{
  drawing: Drawing | null;
  busy: boolean;
  error: string;
  key: string;
}>(() => ({ drawing: null, busy: false, error: '', key: '' }));
let worker: Worker | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;
let requested = '';
let serial = 0;
function request(key: string, inputs: ReturnType<typeof useEngine>) {
  if (requested === key) return;
  requested = key;
  const id = ++serial;
  if (timer) clearTimeout(timer);
  useLayoutState.setState({ busy: true, error: '' });
  timer = setTimeout(() => {
    worker ??= new Worker(new URL('../workers/layout.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onerror = (e) => {
      useLayoutState.setState({ busy: false, error: e.message || 'Drawing worker failed' });
      worker?.terminate();
      worker = undefined;
      requested = '';
    };
    worker.onmessage = (event: MessageEvent<{ id: number; drawing?: unknown; error?: string }>) => {
      if (event.data.id !== serial) return;
      if (event.data.error) {
        useLayoutState.setState({ busy: false, error: event.data.error });
        requested = '';
        return;
      }
      const parsed = DrawingSchema.safeParse(event.data.drawing);
      if (parsed.success)
        useLayoutState.setState({ drawing: parsed.data, busy: false, key, error: '' });
      else {
        useLayoutState.setState({ busy: false, error: 'Invalid drawing geometry' });
        requested = '';
      }
    };
    worker.postMessage({ id, ...inputs });
  }, 300);
}
export function useDrawing() {
  const inputs = useEngine();
  const { project, library, result } = inputs;
  const key = useMemo(() => JSON.stringify({ project, library }), [project, library]);
  const state = useLayoutState();
  useEffect(() => {
    request(key, { project, library, result });
  }, [key, project, library, result]);
  return {
    ...inputs,
    ...state,
    current: state.key === key && !state.busy,
    retry: () => {
      requested = '';
      request(key, { project, library, result });
    },
  };
}
