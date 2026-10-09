import type { Draft } from '../schemas/workspace';

export type SaveState = 'saving' | 'saved' | 'error';

// Serialized writes prevent a slower prior edit from overwriting a newer one.
// flush() is awaited before project switches. The debounce only groups disk writes.
export function createAutosaver(
  write: (draft: Draft) => Promise<void>,
  onState: (state: SaveState) => void,
  delayMs = 400,
) {
  let pending: Draft | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let queue = Promise.resolve();
  let revision = 0;
  let lastError: unknown;

  function flush(): Promise<void> {
    clearTimeout(timer);
    timer = undefined;
    const snapshot = pending;
    if (snapshot) {
      pending = undefined;
      const writingRevision = revision;
      queue = queue.then(async () => {
        try {
          await write(snapshot);
          lastError = undefined;
          if (writingRevision === revision) onState('saved');
        } catch (error) {
          lastError = error;
          if (!pending && writingRevision === revision) pending = snapshot;
          onState('error');
        }
      });
    }
    return queue.then(() => {
      if (lastError) throw lastError;
    });
  }

  return {
    schedule(draft: Draft) {
      pending = draft;
      revision += 1;
      onState('saving');
      clearTimeout(timer);
      timer = setTimeout(() => {
        void flush().catch(() => undefined);
      }, delayMs);
    },
    flush,
    dispose() {
      clearTimeout(timer);
    },
  };
}
