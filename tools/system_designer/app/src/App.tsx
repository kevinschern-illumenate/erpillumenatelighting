import { useEffect, useMemo, useState } from 'react';
import { labelRuns } from '@ill/engine/labels';
import { createDesignApi, DesignApiError, type DesignApi } from './design/api';
import { openDrafts, type DraftStore } from './design/drafts';
import { createDesignStore, loadDesign, persistDrafts, type DesignStore } from './design/store';
import type { MountOptions } from './mount';
import { PRODUCT_NAME } from './product';
import { openingChecks, OpenDesignSchema, startingDesign, type Check, type OpenDesign } from './shell/open';
import { Shell } from './shell/Shell';
import { ErrorState, Skeleton } from './ui';

export { PRODUCT_NAME };

export interface AppServices {
  api?: DesignApi;
  drafts?: DraftStore;
  navigate?: (url: string) => void;
}

type Session =
  | { state: 'loading' }
  | { state: 'error'; message: string; code: string }
  | { state: 'ready'; open: OpenDesign; store: DesignStore; checks: Check[]; restoredDraft: boolean };

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="ill-sd sd-shell" data-testid="system-designer">
      <header className="sd-topbar">
        <div className="sd-topbar__where">
          <div className="sd-topbar__title-row">
            <h1 className="ill-sd__title sd-topbar__title">{PRODUCT_NAME}</h1>
          </div>
        </div>
      </header>
      <div className="sd-frame">{children}</div>
    </div>
  );
}

/** The shell's outline while the schedule opens (SD-1.5), so the page does not jump when it arrives. */
function Loading() {
  return (
    <div className="sd-loading" role="status" aria-label="Opening the schedule">
      <div className="sd-loading__rail">
        {Array.from({ length: 7 }, (_, index) => (
          <Skeleton key={index} height={32} />
        ))}
      </div>
      <div className="sd-loading__canvas">
        <Skeleton width="30%" height={28} />
        <Skeleton width="70%" />
        <Skeleton height={140} />
        <Skeleton height={140} />
      </div>
      <span className="sd-sr-only">Opening the schedule…</span>
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
  const [attempt, setAttempt] = useState(0);

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
        const { restoredDraft } = await loadDesign(store, drafts, open.schedule.name, { design, meta }, (loaded) => ({
          ...loaded,
          runs: labelRuns(loaded.runs, open.lines, open.builds),
        }));
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
        setSession({ state: 'error', message, code: error instanceof DesignApiError ? error.code : 'OPEN_FAILED' });
      }
    })();
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [api, drafts, options.schedule, attempt]);

  if (!options.schedule)
    return (
      <Frame>
        <p>Open a fixture schedule and choose “Design system” to start a design.</p>
      </Frame>
    );
  if (session.state === 'loading')
    return (
      <Frame>
        <Loading />
      </Frame>
    );
  if (session.state === 'error')
    return (
      <Frame>
        <ErrorState
          title="The design could not be opened"
          message={session.message}
          code={session.code}
          onRetry={
            session.code === 'FORBIDDEN' || session.code === 'NOT_FOUND'
              ? undefined
              : () => {
                  setSession({ state: 'loading' });
                  setAttempt((value) => value + 1);
                }
          }
        />
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
