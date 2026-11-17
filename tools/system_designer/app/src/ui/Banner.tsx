import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from './cn';
import { SeverityIcon, type Severity } from './SeverityIcon';

/** A full-width message above the canvas. Errors are alerts; everything else is a polite note. */
export function Banner({
  tone = 'info',
  title,
  children,
  actions,
  onDismiss,
  className,
  ...props
}: {
  tone?: Severity;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  onDismiss?: () => void;
  className?: string;
  'data-testid'?: string;
}) {
  return (
    <div className={cn('sd-banner', `sd-banner--${tone}`, className)} role={tone === 'error' ? 'alert' : 'note'} {...props}>
      <SeverityIcon severity={tone} size={18} />
      <div className="sd-banner__body">
        {title ? <p className="sd-banner__title">{title}</p> : null}
        {children ? <div className="sd-banner__text">{children}</div> : null}
      </div>
      {actions ? <div className="sd-banner__actions">{actions}</div> : null}
      {onDismiss ? (
        <button type="button" className="sd-banner__close" onClick={onDismiss}>
          <X aria-hidden size={16} />
          <span className="sd-sr-only">Dismiss</span>
        </button>
      ) : null}
    </div>
  );
}
