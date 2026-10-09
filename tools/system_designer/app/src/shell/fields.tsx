import { useState } from 'react';
import type { EnvChoice } from '@ill/core-schemas/design';
import { ENVIRONMENTS } from '@ill/data/environments';

/** A text or number input that commits on blur or Enter, so typing is not one undo step per key. */
export function CommitInput({
  value,
  onCommit,
  label,
  type = 'text',
  min,
  step,
  className,
}: {
  value: string | number;
  onCommit(value: string): void;
  label: string;
  type?: 'text' | 'number';
  min?: number;
  step?: number | 'any';
  className?: string;
}) {
  const [text, setText] = useState(String(value));
  // Follow outside changes (undo, a quick pick) without an effect: reset while rendering.
  const [shown, setShown] = useState(value);
  if (shown !== value) {
    setShown(value);
    setText(String(value));
  }
  const commit = () => {
    if (text !== String(value)) onCommit(text);
  };
  return (
    <input
      aria-label={label}
      className={className}
      type={type}
      min={min}
      step={step}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') commit();
        if (event.key === 'Escape') setText(String(value));
      }}
    />
  );
}

export function EnvironmentSelect({
  value,
  onChange,
  label,
}: {
  value: EnvChoice;
  onChange(value: EnvChoice): void;
  label: string;
}) {
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value as EnvChoice)}>
      {ENVIRONMENTS.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/** Feet from a typed value; null when it is not a length. */
export function parseFeet(text: string): number | null {
  const value = Number(text.trim());
  return text.trim() !== '' && Number.isFinite(value) && value >= 0 ? value : null;
}
