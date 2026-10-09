import { useEffect, useRef } from 'react';
import { PRODUCT_NAME } from '../product';

/** First-open terms (plan H9, §22.3). Accepting is recorded on the revision with its first save. */
export function TermsDialog({ text, scheduleUrl, onAccept }: { text: string; scheduleUrl: string; onAccept(): void }) {
  const accept = useRef<HTMLButtonElement>(null);
  useEffect(() => accept.current?.focus(), []);
  return (
    <div className="ill-sd__overlay">
      <div className="ill-sd__dialog" role="dialog" aria-modal="true" aria-labelledby="ill-sd-terms-title">
        <h2 id="ill-sd-terms-title">Before you start</h2>
        <p className="ill-sd__terms">{text}</p>
        <p className="ill-sd__muted">
          By continuing you accept these terms for this design. {PRODUCT_NAME} records who accepted them and when.
        </p>
        <div className="ill-sd__actions">
          <a className="ill-sd__button ill-sd__button--quiet" href={scheduleUrl}>
            Back to schedule
          </a>
          <button ref={accept} type="button" className="ill-sd__button" onClick={onAccept}>
            Accept and continue
          </button>
        </div>
      </div>
    </div>
  );
}
