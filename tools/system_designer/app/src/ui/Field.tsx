import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react';
import { cn } from './cn';
import { formatFeet, parseLength } from './length';
import { SeverityIcon } from './SeverityIcon';

/** A label, the control, a hint and an error message, wired with ids for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
  className?: string;
}) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cn('sd-field', error && 'sd-field--invalid', className)}>
      <label className="sd-field__label" htmlFor={id}>
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint ? (
        <p className="sd-field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="sd-field__error" id={`${id}-error`}>
          <SeverityIcon severity="error" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function Input({ className, invalid, ...props }, ref) {
    return (
      <input ref={ref} className={cn('sd-input', className)} aria-invalid={invalid || undefined} {...props} />
    );
  },
);

/** A styled native select: the platform picker is the most reliable on touch screens and in tests. */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(
  function Select({ className, invalid, ...props }, ref) {
    return (
      <select ref={ref} className={cn('sd-input sd-select', className)} aria-invalid={invalid || undefined} {...props} />
    );
  },
);

export const LENGTH_HINT = 'Feet: 12.5, 12\' 6" or 3.8 m';

/**
 * A length in feet that accepts 12' 6", 12.5 ft or metric, commits on blur or Enter (one undo step),
 * and says what is wrong instead of silently refusing.
 */
export function UnitInput({
  value,
  onCommit,
  label,
  min = 0,
  disabled,
  className,
  id,
  describedBy,
}: {
  value: number | null | undefined;
  onCommit(feet: number): void;
  label?: string;
  min?: number;
  disabled?: boolean;
  className?: string;
  id?: string;
  describedBy?: string;
}) {
  const shownValue = formatFeet(value);
  const [text, setText] = useState(shownValue);
  const [shown, setShown] = useState(shownValue);
  const [error, setError] = useState<string | null>(null);
  const errorId = useId();
  if (shown !== shownValue) {
    setShown(shownValue);
    setText(shownValue);
    setError(null);
  }
  const commit = () => {
    if (text === shownValue) return setError(null);
    const feet = parseLength(text);
    if (feet == null || feet < min) {
      setError(feet == null ? 'Enter a length like 12.5, 12\' 6" or 3.8 m' : `Enter at least ${min} ft`);
      return;
    }
    setError(null);
    const rounded = Number(feet.toFixed(2));
    setText(formatFeet(rounded));
    onCommit(rounded);
  };
  return (
    <span className={cn('sd-unit', error && 'sd-unit--invalid', className)}>
      <input
        id={id}
        aria-label={id ? undefined : label}
        aria-invalid={error ? true : undefined}
        aria-describedby={[describedBy, error ? errorId : ''].filter(Boolean).join(' ') || undefined}
        className="sd-input sd-unit__input"
        inputMode="decimal"
        value={text}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') commit();
          if (event.key === 'Escape') {
            setText(shownValue);
            setError(null);
          }
        }}
      />
      <span className="sd-unit__suffix" aria-hidden>
        ft
      </span>
      {error ? (
        <span className="sd-unit__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
