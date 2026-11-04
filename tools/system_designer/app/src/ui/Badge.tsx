import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from './cn';

export type Tone = 'neutral' | 'info' | 'ok' | 'warning' | 'error' | 'brand';

export function Badge({
  tone = 'neutral',
  icon,
  className,
  children,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone; icon?: ReactNode }) {
  return (
    <span className={cn('sd-badge', `sd-badge--${tone}`, className)} {...props}>
      {icon ? (
        <span aria-hidden className="sd-badge__icon">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}
