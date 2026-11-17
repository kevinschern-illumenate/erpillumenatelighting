import { useEffect, useRef, useState } from 'react';
import type { DesignApi } from '../design/api';
import type { DesignStore, SaveStatus } from '../design/store';
import { OpenDesignSchema } from './open';

/** Autosave timing (SD-1.4): after 20 s without an edit, at most once a minute. */
export const AUTOSAVE_IDLE_MS = 20_000;
export const AUTOSAVE_MIN_INTERVAL_MS = 60_000;
/** Statuses that need the designer to act before another save can succeed. */
const BLOCKED: ReadonlySet<SaveStatus> = new Set(['saving', 'conflict', 'locked', 'session']);

/**
 * Save without being asked (SD-1.4): when edits pause, when the designer changes step and when the
 * tab is hidden. `enabled` is false while the design is read-only, the terms are not accepted or
 * schedule changes wait to be applied, since a save would only fail.
 */
export function useAutosave({
  store,
  enabled,
  save,
  step,
  online,
}: {
  store: DesignStore;
  enabled: boolean;
  save(): Promise<unknown> | void;
  step: string;
  online: boolean;
}) {
  const latest = useRef({ enabled, save, online });
  useEffect(() => {
    latest.current = { enabled, save, online };
  }, [enabled, save, online]);
  const lastSave = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const runRef = useRef(() => {});
  useEffect(() => {
    runRef.current = () => {
      clearTimeout(timer.current);
      const { dirty, saveStatus } = store.getState();
      const { enabled: on, online: connected, save: write } = latest.current;
      if (!on || !connected || !dirty || BLOCKED.has(saveStatus)) return;
      lastSave.current = Date.now();
      void write();
    };
  }, [store]);

  // Edits (re)start the idle timer; a save in the last minute pushes it back.
  useEffect(() => {
    const schedule = () => {
      clearTimeout(timer.current);
      if (!store.getState().dirty) return;
      const at = Math.max(Date.now() + AUTOSAVE_IDLE_MS, lastSave.current + AUTOSAVE_MIN_INTERVAL_MS);
      timer.current = setTimeout(() => runRef.current(), at - Date.now());
    };
    const unsubscribe = store.subscribe((state, previous) => {
      if (state.saveStatus === 'saving' && previous.saveStatus !== 'saving') lastSave.current = Date.now();
      if (state.design !== previous.design || state.dirty !== previous.dirty) schedule();
    });
    schedule();
    return () => {
      unsubscribe();
      clearTimeout(timer.current);
    };
  }, [store]);

  // Changing step is a natural pause.
  const firstStep = useRef(true);
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    if (Date.now() - lastSave.current > 5_000) runRef.current();
  }, [step]);

  // Leaving the tab, and coming back online, save straight away.
  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === 'hidden') runRef.current();
    };
    document.addEventListener('visibilitychange', onHidden);
    return () => document.removeEventListener('visibilitychange', onHidden);
  }, []);
  useEffect(() => {
    if (online && store.getState().saveStatus === 'offline') runRef.current();
  }, [online, store]);
}

/** Whether the browser thinks it is online (SD-1.6). */
export function useOnline() {
  const [online, setOnline] = useState(() => globalThis.navigator?.onLine ?? true);
  useEffect(() => {
    const update = () => setOnline(globalThis.navigator?.onLine ?? true);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  return online;
}

/** Ask before leaving with changes the server does not have yet (SD-1.6). */
export function useBeforeUnload(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older browsers show the prompt only when returnValue is set.
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [active]);
}

/**
 * Whether the same schedule's design is open in another tab of this browser (SD-1.6). Each tab
 * announces itself on a BroadcastChannel and answers the others.
 */
export function useOtherTabs(schedule: string) {
  const [others, setOthers] = useState(false);
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(`ill-sd:${schedule}`);
    const id = Math.random().toString(36).slice(2);
    const peers = new Set<string>();
    channel.onmessage = (event: MessageEvent<{ type: 'hello' | 'here' | 'bye'; id: string }>) => {
      const message = event.data;
      if (!message || message.id === id) return;
      if (message.type === 'bye') peers.delete(message.id);
      else peers.add(message.id);
      if (message.type === 'hello') channel.postMessage({ type: 'here', id });
      setOthers(peers.size > 0);
    };
    channel.postMessage({ type: 'hello', id });
    const bye = () => channel.postMessage({ type: 'bye', id });
    window.addEventListener('pagehide', bye);
    return () => {
      window.removeEventListener('pagehide', bye);
      bye();
      channel.close();
    };
  }, [schedule]);
  return others;
}

export const FRESHNESS_INTERVAL_MS = 10 * 60_000;

/**
 * When the designer comes back to the tab after a while, ask the server whether the product data or
 * the saved design changed meanwhile (SD-1.6), so they hear before a save fails.
 */
export function useFreshness(api: DesignApi, schedule: string, catalogHash: string, store: DesignStore) {
  const [changes, setChanges] = useState({ catalog: false, design: false });
  const checkedAt = useRef(0);
  useEffect(() => {
    let cancelled = false;
    checkedAt.current = Date.now();
    const check = async () => {
      if (document.visibilityState !== 'visible' || Date.now() - checkedAt.current < FRESHNESS_INTERVAL_MS) return;
      checkedAt.current = Date.now();
      try {
        const latest = OpenDesignSchema.parse(await api.openDesign(schedule));
        const { meta, saveStatus } = store.getState();
        if (cancelled) return;
        setChanges({
          catalog: latest.catalog_hash !== catalogHash,
          design: Boolean(
            meta &&
              saveStatus !== 'saving' &&
              latest.design_meta?.name === meta.name &&
              latest.design_meta.modified !== meta.modified,
          ),
        });
      } catch {
        // Offline or signed out: the save path explains those.
      }
    };
    document.addEventListener('visibilitychange', check);
    window.addEventListener('focus', check);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', check);
      window.removeEventListener('focus', check);
    };
  }, [api, schedule, catalogHash, store]);
  return changes;
}
