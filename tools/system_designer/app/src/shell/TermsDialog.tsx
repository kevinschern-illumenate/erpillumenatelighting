import { useRef } from 'react';
import { PRODUCT_NAME } from '../product';
import { Button, Dialog } from '../ui';

/** First-open terms (plan H9, §22.3). Accepting is recorded on the revision with its first save. */
export function TermsDialog({ text, scheduleUrl, onAccept }: { text: string; scheduleUrl: string; onAccept(): void }) {
  const accept = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open
      dismissable={false}
      initialFocus={accept}
      title="Before you start"
      size="md"
      data-testid="terms-dialog"
      footer={
        <>
          <Button asChild variant="quiet">
            <a href={scheduleUrl}>Back to schedule</a>
          </Button>
          <Button ref={accept} variant="primary" onClick={onAccept}>
            Accept and continue
          </Button>
        </>
      }
    >
      <p className="sd-terms">{text}</p>
      <p className="ill-sd__muted">
        By continuing you accept these terms for this design. {PRODUCT_NAME} records who accepted them and when.
      </p>
    </Dialog>
  );
}
