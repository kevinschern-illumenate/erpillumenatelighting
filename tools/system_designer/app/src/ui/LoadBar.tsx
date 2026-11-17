import { cn } from './cn';
import { SeverityIcon } from './SeverityIcon';

/** How full a supply, output or circuit is. Over 100 % is an error and 80 % a warning, by icon and text. */
export function loadTone(value: number, max: number, warnAt = 0.8) {
  if (max <= 0) return value > 0 ? 'error' : 'ok';
  const ratio = value / max;
  return ratio > 1 ? 'error' : ratio >= warnAt ? 'warning' : 'ok';
}

export function LoadBar({
  value,
  max,
  label,
  unit = 'W',
  warnAt = 0.8,
  className,
}: {
  value: number;
  max: number;
  label: string;
  unit?: string;
  warnAt?: number;
  className?: string;
}) {
  const tone = loadTone(value, max, warnAt);
  const percent = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className={cn('sd-loadbar', `sd-loadbar--${tone}`, className)}>
      <div
        className="sd-loadbar__track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.min(value, max)}
        aria-valuetext={`${Math.round(value)} of ${Math.round(max)} ${unit} (${percent}%)`}
      >
        <span className="sd-loadbar__fill" style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
      <span className="sd-loadbar__text">
        {tone !== 'ok' ? <SeverityIcon severity={tone} size={14} label /> : null}
        {Math.round(value)} / {Math.round(max)} {unit} · {percent}%
      </span>
    </div>
  );
}
