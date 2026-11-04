import { CircleCheck, CircleX, Info, TriangleAlert } from 'lucide-react';
import { cn } from './cn';

export type Severity = 'error' | 'warning' | 'info' | 'ok';

const ICONS = { error: CircleX, warning: TriangleAlert, info: Info, ok: CircleCheck } as const;
export const SEVERITY_LABEL: Record<Severity, string> = {
  error: 'Error',
  warning: 'Warning',
  info: 'Note',
  ok: 'OK',
};

/** Severity is shown by shape and text, never colour alone (WCAG 1.4.1). */
export function SeverityIcon({
  severity,
  size = 16,
  label = false,
  className,
}: {
  severity: Severity;
  size?: number;
  /** Add the severity as visually hidden text for screen readers. */
  label?: boolean;
  className?: string;
}) {
  const Icon = ICONS[severity];
  return (
    <span className={cn('sd-severity', `sd-severity--${severity}`, className)}>
      <Icon aria-hidden size={size} />
      {label ? <span className="sd-sr-only">{SEVERITY_LABEL[severity]}: </span> : null}
    </span>
  );
}
