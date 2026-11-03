import { Button, Dialog } from '../ui';

/** Someone else saved this design first (SD-1.4): keep your version or take theirs. Escape cannot pick for you. */
export function ConflictDialog({
  open,
  busy,
  onKeepMine,
  onTakeTheirs,
}: {
  open: boolean;
  busy: boolean;
  onKeepMine(): void;
  onTakeTheirs(): void;
}) {
  return (
    <Dialog
      open={open}
      dismissable={false}
      title="This design was changed somewhere else"
      size="sm"
      data-testid="conflict-dialog"
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onTakeTheirs}>
            Open the latest version
          </Button>
          <Button variant="primary" loading={busy} onClick={onKeepMine}>
            Keep my changes
          </Button>
        </>
      }
    >
      <p>
        Someone saved this design, in another tab or on another computer, after you opened it. Keep your changes to
        save over theirs, or open the latest version and drop the changes made here.
      </p>
    </Dialog>
  );
}

/** The portal session ended (SD-1.6). Nothing is lost: the draft stays in this browser. */
export function SessionDialog({ open, onRetry, onClose }: { open: boolean; onRetry(): void; onClose(): void }) {
  const login = `/login?redirect-to=${encodeURIComponent(globalThis.location?.pathname ?? '/portal')}`;
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => (value ? null : onClose())}
      title="Sign in again to save"
      size="sm"
      data-testid="session-dialog"
      footer={
        <>
          <Button asChild variant="secondary">
            <a href={login} target="_blank" rel="noreferrer">
              Sign in (new tab)
            </a>
          </Button>
          <Button variant="primary" onClick={onRetry}>
            I've signed in, save now
          </Button>
        </>
      }
    >
      <p>
        Your portal session has ended, so this design could not be saved. Your changes are kept in this browser. Sign in
        in a new tab, then come back and save.
      </p>
    </Dialog>
  );
}
