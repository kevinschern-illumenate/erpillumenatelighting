import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import type { Field } from './editor-fields';
import { at, type EditorRecord } from './editor-model';

export type FieldIssue = { path: string; message: string };
export type FieldProps = {
  field: Field;
  path: string;
  value: EditorRecord;
  onChange: (path: string, value: unknown) => void;
  issues: FieldIssue[];
  idPrefix: string;
};
export function LibraryField({ field, path, value, onChange, issues, idPrefix }: FieldProps) {
  const current = at(value, path),
    id = `${idPrefix}-${path}`;
  const errors = issues.filter((issue) => issue.path === path);
  if (
    field.when &&
    current === undefined &&
    at(value, path.split('.').slice(0, -1).concat(field.when.key).join('.')) !== field.when.value
  )
    return null;
  const change = (v: unknown) => onChange(path, v);
  const helpId = `${id}-help`,
    errorId = `${id}-error`;
  const a11y = {
    id,
    'aria-invalid': errors.length > 0 || undefined,
    'aria-describedby':
      [field.hint ? helpId : '', errors.length ? errorId : ''].filter(Boolean).join(' ') ||
      undefined,
  };
  const options = field.options ?? [];
  const freeCutting =
    field.key === 'cutIntervalIn' &&
    at(value, path.replace(/cutIntervalIn$/, 'freeCutting')) === true;
  if (
    field.key === 'outputDimming' &&
    at(value, path.replace(/outputDimming$/, 'powerType')) !== 'AC'
  )
    return (
      <div className="library-form-field" id={id} tabIndex={-1}>
        <div className="library-field-label">AC output dimming method</div>
        <p className="field-hint">
          Select AC power input and output to set the phase dimming method.
        </p>
        {current !== undefined && (
          <Button type="button" variant="outline" size="sm" onClick={() => change(undefined)}>
            Remove stored AC dimming method
          </Button>
        )}
        {errors.length > 0 && (
          <p className="library-field-error">{errors.map((e) => e.message).join(' ')}</p>
        )}
      </div>
    );
  if (freeCutting)
    return (
      <div className="library-form-field" id={id} tabIndex={-1}>
        <div className="library-field-label">Cut interval</div>
        <p className="field-hint">Not applicable — this tape is free-cutting.</p>
        {current !== undefined && (
          <>
            <p className="library-field-error">
              A fixed interval is still stored. Remove it for free-cutting tape.
            </p>
            <Button type="button" variant="outline" size="sm" onClick={() => change(undefined)}>
              Remove stored cut interval
            </Button>
          </>
        )}
        {errors.length > 0 && (
          <p className="library-field-error">{errors.map((e) => e.message).join(' ')}</p>
        )}
      </div>
    );
  const isCollection = ['list', 'rows', 'choices', 'voltage'].includes(field.type ?? '');
  let control;
  if (field.type === 'rows' || field.type === 'list') {
    const items = Array.isArray(current) ? current : [];
    const label = field.itemLabel ?? 'value';
    control = (
      <div className="library-repeater" id={id} tabIndex={-1}>
        {items.length === 0 && (
          <p className="field-hint">
            {current === undefined ? 'Not specified yet.' : 'No entries.'}
          </p>
        )}
        {items.map((_, i) => (
          <fieldset className="library-repeat-row" key={i}>
            <legend>
              {field.itemLabel
                ? `${label.charAt(0).toUpperCase()}${label.slice(1)} ${i + 1}`
                : `${field.label} ${i + 1}`}
            </legend>
            <div className={field.type === 'rows' ? 'library-field-grid' : 'library-list-row'}>
              {field.type === 'rows' ? (
                field.fields?.map((child) => (
                  <LibraryField
                    key={child.key}
                    field={child}
                    path={`${path}.${i}.${child.key}`}
                    value={value}
                    onChange={onChange}
                    issues={issues}
                    idPrefix={idPrefix}
                  />
                ))
              ) : (
                <LibraryField
                  field={{
                    key: String(i),
                    label: `${field.label} ${i + 1}`,
                    type: field.numeric ? 'number' : 'text',
                  }}
                  path={`${path}.${i}`}
                  value={value}
                  onChange={(p, v) => onChange(p, v === undefined ? null : v)}
                  issues={issues}
                  idPrefix={idPrefix}
                />
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove ${field.itemLabel ?? field.label} ${i + 1}`}
                onClick={() => change(items.filter((_, n) => n !== i))}
              >
                Remove
              </Button>
            </div>
          </fieldset>
        ))}
        <div className="action-bar">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              change([...items, field.type === 'rows' ? {} : field.numeric ? null : ''])
            }
          >
            Add {field.itemLabel ?? field.label.toLowerCase().replace(/ \(.*\)$/, '')}
          </Button>
          {current === undefined && (
            <Button type="button" variant="ghost" size="sm" onClick={() => change([])}>
              No entries
            </Button>
          )}
          {field.optional && current !== undefined && (
            <Button type="button" variant="ghost" size="sm" onClick={() => change(undefined)}>
              Clear {field.label.toLowerCase()}
            </Button>
          )}
        </div>
      </div>
    );
  } else if (field.type === 'choices') {
    const selected: string[] = Array.isArray(current) ? current.map(String) : [];
    control = (
      <div className="library-choice-grid" id={id} tabIndex={-1}>
        {[...new Set([...options, ...selected])].map((option) => (
          <label key={option}>
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={(e) =>
                change(
                  e.target.checked ? [...selected, option] : selected.filter((s) => s !== option),
                )
              }
            />
            <span>
              {field.labels?.[option] ?? option}
              {!options.includes(option) ? ' (unrecognized)' : ''}
            </span>
          </label>
        ))}
        {current === undefined && (
          <Button type="button" variant="ghost" size="sm" onClick={() => change([])}>
            No {field.label.toLowerCase()}
          </Button>
        )}
      </div>
    );
  } else if (field.type === 'voltage') {
    const range = Array.isArray(current);
    control = (
      <div className="library-voltage" id={id} tabIndex={-1}>
        <label>
          Voltage entry
          <select
            aria-label="Voltage entry"
            value={range ? 'range' : 'single'}
            onChange={(e) =>
              change(
                e.target.value === 'range'
                  ? [typeof current === 'number' ? current : null, null]
                  : range
                    ? (current[0] ?? undefined)
                    : current,
              )
            }
          >
            <option value="single">Single voltage</option>
            <option value="range">Voltage range</option>
          </select>
        </label>
        {(range
          ? ['Minimum input voltage (V)', 'Maximum input voltage (V)']
          : ['Input voltage (V)']
        ).map((name, i) => (
          <label key={name}>
            {name}
            <Input
              aria-label={name}
              type="number"
              step="any"
              value={String((range ? current[i] : current) ?? '')}
              onChange={(e) => {
                const v = e.target.value === '' ? undefined : Number(e.target.value);
                if (range) {
                  const next = [...current];
                  next[i] = v ?? null;
                  change(next);
                } else change(v);
              }}
            />
          </label>
        ))}
      </div>
    );
  } else if (field.type === 'select' || field.type === 'boolean') {
    const values = field.type === 'boolean' ? ['true', 'false'] : [...options];
    if (current !== undefined && !values.includes(String(current))) values.push(String(current));
    control = (
      <select
        {...a11y}
        value={current === undefined ? '' : String(current)}
        onChange={(e) =>
          change(
            e.target.value === ''
              ? undefined
              : field.type === 'boolean'
                ? e.target.value === 'true'
                : field.numeric
                  ? Number(e.target.value)
                  : e.target.value,
          )
        }
      >
        <option value="">{field.optional ? 'Not specified' : 'Select…'}</option>
        {values.map((option) => (
          <option key={option} value={option}>
            {field.type === 'boolean'
              ? option === 'true'
                ? 'Yes'
                : 'No'
              : (field.labels?.[option] ?? option)}
          </option>
        ))}
      </select>
    );
  } else if (field.type === 'textarea') {
    control = (
      <textarea
        {...a11y}
        rows={3}
        value={String(current ?? '')}
        onChange={(e) => change(field.optional && !e.target.value ? undefined : e.target.value)}
      />
    );
  } else if (field.type === 'number') {
    control = (
      <Input
        {...a11y}
        type="number"
        step="any"
        value={
          typeof current === 'number' ? Number((current * (field.scale ?? 1)).toPrecision(12)) : ''
        }
        onChange={(e) =>
          change(e.target.value === '' ? undefined : Number(e.target.value) / (field.scale ?? 1))
        }
      />
    );
  } else {
    control = (
      <Input
        {...a11y}
        value={String(current ?? '')}
        onChange={(e) => change(field.optional && !e.target.value ? undefined : e.target.value)}
      />
    );
  }
  return (
    <div
      className={`library-form-field ${isCollection || field.type === 'textarea' ? 'library-field-wide' : ''}`}
    >
      {isCollection ? (
        <div className="library-field-label" id={`${id}-label`}>
          {field.label} {field.optional && <span>optional</span>}
        </div>
      ) : (
        <label htmlFor={id}>
          {field.label} {field.optional && <span>optional</span>}
        </label>
      )}
      <div
        role={isCollection ? 'group' : undefined}
        aria-labelledby={isCollection ? `${id}-label` : undefined}
      >
        {control}
      </div>
      {field.hint && (
        <p className="field-hint" id={helpId}>
          {field.hint}
        </p>
      )}
      {errors.length > 0 && (
        <p className="library-field-error" id={errorId}>
          {errors.map((e) => e.message).join(' ')}
        </p>
      )}
    </div>
  );
}
