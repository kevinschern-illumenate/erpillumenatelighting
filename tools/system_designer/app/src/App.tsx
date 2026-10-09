import { useEffect, useMemo, useState } from 'react';
import { createDesignApi, DesignApiError, type DesignApi } from './design/api';
import { openDrafts, type DraftStore } from './design/drafts';
import { createDesignStore, loadDesign, persistDrafts, type DesignStore } from './design/store';
import type { MountOptions } from './mount';
import { PRODUCT_NAME } from './product';
import { openingChecks, OpenDesignSchema, startingDesign, type Check, type OpenDesign } from './shell/open';
import { Shell } from './shell/Shell';

export { PRODUCT_NAME };

export interface AppServices {
  api?: DesignApi;
  drafts?: DraftStore;
  navigate?: (url: string) => void;
}

type Session =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; open: OpenDesign; store: DesignStore; checks: Check[]; restoredDraft: boolean };

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="ill-sd" data-testid="system-designer">
      <header className="ill-sd__header">
        <div className="ill-sd__heading">
          <span className="ill-sd__brand">ilLumenate</span>
          <h1 className="ill-sd__title">{PRODUCT_NAME}</h1>
        </div>
      </header>
      <main className="ill-sd__body">{children}</main>
    </div>
  );
}

export function App({ options, services = {} }: { options: MountOptions; services?: AppServices }) {
  const api = useMemo(
    () => services.api ?? createDesignApi({ apiBase: options.apiBase, csrfToken: options.csrfToken }),
    [services.api, options.apiBase, options.csrfToken],
  );
  const drafts = useMemo(() => services.drafts ?? openDrafts(), [services.drafts]);
  const [session, setSession] = useState<Session>({ state: 'loading' });

  useEffect(() => {
    const schedule = options.schedule;
    if (!schedule) return;
    let cancelled = false;
    let stop: (() => void) | undefined;
    (async () => {
      try {
        const open = OpenDesignSchema.parse(await api.openDesign(schedule));
        const { design, meta, skipped } = startingDesign(open);
        const store = createDesignStore();
        const { restoredDraft } = await loadDesign(store, drafts, open.schedule.name, { design, meta });
        store.getState().setReconcile(open.reconcile);
        if (cancelled) return;
        stop = persistDrafts(store, drafts);
        setSession({ state: 'ready', open, store, checks: openingChecks(open, skipped), restoredDraft });
      } catch (error) {
        if (cancelled) return;
        if (!(error instanceof DesignApiError)) console.error('ilLumenate System Designer: open failed', error);
        const message =
          error instanceof DesignApiError
            ? error.message
            : 'The design could not be opened. Reload the page or try again later.';
        setSession({ state: 'error', message });
      }
    })();
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [api, drafts, options.schedule]);

  if (!options.schedule)
    return (
      <Frame>
        <p>Open a fixture schedule and choose “Design system” to start a design.</p>
      </Frame>
    );
  if (session.state === 'loading')
    return (
      <Frame>
        <p role="status">Opening the schedule…</p>
      </Frame>
    );
  if (session.state === 'error')
    return (
      <Frame>
        <p role="alert" className="ill-sd__error">
          {session.message}
        </p>
      </Frame>
    );
  return (
    <Shell
      open={session.open}
      store={session.store}
      api={api}
      drafts={drafts}
      checks={session.checks}
      restoredDraft={session.restoredDraft}
      navigate={services.navigate}
    />
  );
}
