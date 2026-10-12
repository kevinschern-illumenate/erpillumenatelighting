import { useEffect, useRef, useState } from 'react';
import { activateDraft, useProjectStore } from '../state/project-store';
import { recentDrafts, saveDraft } from '../storage/database';
import { createAutosaver, type SaveState } from '../storage/autosave';
import { createDraft, type Draft, type StoredDraft } from '../schemas/workspace';

export function useWorkspace() {
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<SaveState>('saving');
  const [error, setError] = useState('');
  const [recent, setRecent] = useState<StoredDraft[]>([]);
  const saver = useRef<ReturnType<typeof createAutosaver> | null>(null);
  const switching = useRef(false);

  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;
    const autosaver = createAutosaver(
      async (draft) => {
        await saveDraft(draft);
        const records = await recentDrafts();
        if (active) setRecent(records);
      },
      (next) => {
        if (active) {
          setStatus(next);
          setError(
            next === 'error'
              ? 'Autosave failed. Your edits are still in memory. Use Save now to retry before closing this tab.'
              : '',
          );
        }
      },
    );
    saver.current = autosaver;
    void recentDrafts()
      .then((records) => {
        if (!active) return;
        if (records[0]) activateDraft(records[0].draft);
        setRecent(records);
        unsubscribe = useProjectStore.subscribe((state, previous) => {
          if (state.draft !== previous.draft) autosaver.schedule(state.draft);
        });
        setReady(true);
        autosaver.schedule(useProjectStore.getState().draft);
      })
      .catch(() => {
        if (active) {
          setStatus('error');
          setError(
            'Local storage could not be opened or contains an unsupported draft. Existing records have been preserved. Retry in this browser with storage enabled.',
          );
        }
      });
    const flush = () => {
      void autosaver.flush().catch(() => undefined);
    };
    const onHidden = () => {
      if (document.visibilityState === 'hidden') flush();
    };
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', onHidden);
    return () => {
      active = false;
      unsubscribe?.();
      flush();
      autosaver.dispose();
      window.removeEventListener('pagehide', flush);
      document.removeEventListener('visibilitychange', onHidden);
    };
  }, []);

  useEffect(() => {
    if (status === 'saved') return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [status]);

  async function persist() {
    if (!ready || !saver.current) return;
    saver.current.schedule(useProjectStore.getState().draft);
    await saver.current.flush();
  }

  async function open(draft: Draft) {
    if (!ready || !saver.current || switching.current) return;
    switching.current = true;
    try {
      // A user can make another edit while IndexedDB is busy. Drain that edit too.
      let snapshot: Draft;
      do {
        snapshot = useProjectStore.getState().draft;
        await saver.current.flush();
      } while (snapshot !== useProjectStore.getState().draft);
      activateDraft(draft);
    } catch {
      setError(
        'Could not save the current project. Project switching is paused until Save now succeeds.',
      );
    } finally {
      switching.current = false;
    }
  }

  return { ready, status, error, recent, persist, open, create: () => open(createDraft()) };
}
