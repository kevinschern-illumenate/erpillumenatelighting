import { useEffect } from 'react';
import { loadLibrary, saveLibrary } from '../storage/library';
import { useLibraryStore } from '../state/library-store';

export function useLibraryWorkspace() {
  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;
    let queue = Promise.resolve();
    let revision = 0;
    void loadLibrary()
      .then((library) => {
        if (!active) return;
        useLibraryStore.setState({ library, ready: true, status: 'saved', error: '' });
        useLibraryStore.temporal.getState().clear();
        unsubscribe = useLibraryStore.subscribe((next, previous) => {
          if (next.library === previous.library) return;
          const current = ++revision;
          useLibraryStore.setState({ status: 'saving', error: '' });
          queue = queue
            .catch(() => undefined)
            .then(() => saveLibrary(next.library))
            .then(() => {
              if (active && current === revision) useLibraryStore.setState({ status: 'saved' });
            })
            .catch(() => {
              if (active)
                useLibraryStore.setState({
                  status: 'error',
                  error:
                    'Library save failed. Keep this page open and retry saving or export a library backup.',
                });
            });
        });
      })
      .catch(() => {
        if (active)
          useLibraryStore.setState({
            ready: false,
            status: 'error',
            error: 'The saved library could not be loaded. Existing records have been preserved.',
          });
      });
    const warn = (event: BeforeUnloadEvent) => {
      if (useLibraryStore.getState().status !== 'saved') {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', warn);
    return () => {
      active = false;
      unsubscribe?.();
      window.removeEventListener('beforeunload', warn);
    };
  }, []);
}
