import { CircleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from './Button';
import { cn } from './cn';

/** A grey placeholder in the shape of content that is still loading. */
export function Skeleton({ width, height = 16, className }: { width?: number | string; height?: number | string; className?: string }) {
  return <span className={cn('sd-skeleton', className)} style={{ width, height }} aria-hidden />;
}

/** What goes here, and the one action that fills it. */
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="sd-empty">
      {icon ? (
        <span className="sd-empty__icon" aria-hidden>
          {icon}
        </span>
      ) : null}
      <p className="sd-empty__title">{title}</p>
      {children ? <div className="sd-empty__text">{children}</div> : null}
      {action ? <div className="sd-empty__action">{action}</div> : null}
    </div>
  );
}

export const SUPPORT_URL = '/portal/support';

/** Something failed: say what, offer Retry, give the code for support, and a way to reach a person. */
export function ErrorState({
  title = 'Something went wrong',
  message,
  code,
  onRetry,
  contactUrl = SUPPORT_URL,
  children,
}: {
  title?: ReactNode;
  message: string;
  code?: string;
  onRetry?: () => void;
  contactUrl?: string | null;
  children?: ReactNode;
}) {
  return (
    <div className="sd-error-state" data-testid="error-state">
      <CircleAlert aria-hidden size={32} className="sd-error-state__icon" />
      <h2 className="sd-error-state__title">{title}</h2>
      <p role="alert" className="sd-error-state__message">
        {message}
      </p>
      {code ? <p className="sd-error-state__code">Error code: {code}</p> : null}
      {children}
      <div className="sd-error-state__actions">
        {onRetry ? (
          <Button variant="primary" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
        {contactUrl ? (
          <Button asChild variant="quiet">
            <a href={contactUrl}>Contact ilLumenate</a>
          </Button>
        ) : null}
      </div>
    </div>
  );
}
