import { useState } from 'react';
import type { EnvChoice, Run } from '@ill/core-schemas/design';
import { ENVIRONMENTS } from '@ill/data/environments';
import { DISTANCE_LABELS, type DistancePick } from '@ill/engine/site';

export const PICKS = Object.keys(DISTANCE_LABELS) as DistancePick[];

export const PROVENANCE: Record<Run['homeRunProvenance'], string> = {
  estimate: 'estimate',
  entered: 'entered',
  measured: 'measured',
  erp: 'from ERP',
};

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

/** A distance in feet with its provenance and the plan §8 quick picks. */
export function Distance({
  label,
  value,
  provenance,
  onType,
  onPick,
}: {
  label: string;
  value: number;
  provenance: string;
  onType(text: string): void;
  onPick(pick: DistancePick): void;
}) {
  return (
    <span className="ill-sd__distance">
      <CommitInput
        label={label}
        type="number"
        min={0}
        step="any"
        value={value}
        onCommit={onType}
        className="ill-sd__feet"
      />
      ft <span className="ill-sd__muted">({provenance})</span>
      <select
        aria-label={`${label} quick pick`}
        value=""
        onChange={(event) => event.target.value && onPick(event.target.value as DistancePick)}
      >
        <option value="">Quick pick…</option>
        {PICKS.map((pick) => (
          <option key={pick} value={pick}>
            {DISTANCE_LABELS[pick]}
          </option>
        ))}
      </select>
    </span>
  );
}
