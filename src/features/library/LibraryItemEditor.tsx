import { useEffect, useId, useRef, useState } from 'react';
import { Button } from '../../components/ui/button';
import { LibraryField, type FieldIssue } from './LibraryFields';
import {
  categoryLabels,
  intendedKind,
  productDetails,
  sourceFields,
  specSections,
  wireSections,
  type Section,
} from './editor-fields';
import {
  changeCategory,
  at,
  fullProduct,
  incompleteProduct,
  itemSchema,
  parseEditor,
  record,
  updateField,
  type EditorRecord,
} from './editor-model';
import type { LibraryKind, LibraryRow } from './import';

function SourceValues({ value }: { value: unknown }) {
  if (Array.isArray(value))
    return (
      <ol>
        {value.map((v, i) => (
          <li key={i}>
            <SourceValues value={v} />
          </li>
        ))}
      </ol>
    );
  if (value && typeof value === 'object')
    return (
      <dl>
        {Object.entries(value).map(([key, v]) => (
          <div key={key}>
            <dt>{key.replaceAll('_', ' ')}</dt>
            <dd>
              <SourceValues value={v} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{value === '' || value === null || value === undefined ? '—' : String(value)}</span>;
}

export function LibraryItemEditor({
  initialValue,
  kind,
  editingId,
  onSave,
  onCancel,
  saveError,
}: {
  initialValue: string;
  kind: LibraryKind;
  editingId: string | null;
  onSave: (item: LibraryRow) => void;
  onCancel: () => void;
  saveError: string;
}) {
  const [draft, setDraft] = useState(() => parseEditor(initialValue));
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [json, setJson] = useState(initialValue);
  const [issues, setIssues] = useState<FieldIssue[]>([]);
  const [error, setError] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const categoryDrafts = useRef<Record<string, unknown>>({});
  const editorRef = useRef<HTMLElement>(null);
  useEffect(() => {
    editorRef.current?.scrollIntoView({ block: 'start' });
    editorRef.current?.focus({ preventScroll: true });
  }, []);
  const idPrefix = useId();
  const specs = record(draft.specs),
    pending = specs.kind === 'incomplete';
  const specKind = String(pending ? specs.intendedKind : specs.kind);
  const specPrefix = pending ? 'specs.available' : 'specs';
  const notes = pending && Array.isArray(specs.notes) ? specs.notes.map(String) : [];
  const unresolved =
    pending && Array.isArray(specs.missingFields) ? specs.missingFields.map(String) : [];
  const sections: { section: Section; prefix: string }[] =
    kind === 'products'
      ? [
          { section: { title: 'Product details', fields: productDetails }, prefix: '' },
          ...(specSections[specKind] ?? []).map((section) => ({ section, prefix: specPrefix })),
        ]
      : wireSections.map((section) => ({ section, prefix: '' }));
  sections.push({
    section: {
      title: 'Source and verification',
      hint: 'Keep the reference used to confirm these specifications.',
      fields: sourceFields,
    },
    prefix: '',
  });
  const fieldLabels = new Map<string, string>();
  for (const { section, prefix } of sections)
    for (const field of section.fields)
      fieldLabels.set(prefix ? `${prefix}.${field.key}` : field.key, field.label);
  function labelFor(path: string) {
    return (
      fieldLabels.get(path) ??
      [...fieldLabels.entries()].find(([p]) => path.startsWith(p + '.'))?.[1] ??
      path
    );
  }
  function focusField(path: string) {
    const field =
      document.getElementById(`${idPrefix}-${path}`) ??
      document.getElementById(`${idPrefix}-${path.split('.').slice(0, -1).join('.')}`);
    let ancestor = field?.parentElement;
    while (ancestor) {
      if (ancestor instanceof HTMLDetailsElement) ancestor.open = true;
      ancestor = ancestor.parentElement;
    }
    field?.scrollIntoView({ block: 'center' });
    field?.focus();
  }
  function change(path: string, value: unknown) {
    setDraft((previous) => {
      if (path === 'category' && kind === 'products') {
        const current = record(previous.specs),
          oldKind = String(current.kind === 'incomplete' ? current.intendedKind : current.kind);
        const nextKind = intendedKind(value);
        categoryDrafts.current[oldKind] = structuredClone(current);
        const next = changeCategory(previous, String(value));
        if (nextKind !== oldKind && categoryDrafts.current[nextKind])
          next.specs = structuredClone(categoryDrafts.current[nextKind]);
        return next;
      }
      return updateField(previous, path, value);
    });
    setIssues((previous) =>
      path === 'category'
        ? []
        : previous.filter((issue) => issue.path !== path && !issue.path.startsWith(path + '.')),
    );
    setError('');
  }
  function switchMode(next: 'form' | 'json') {
    if (next === mode) return;
    if (next === 'json') setJson(JSON.stringify(draft, null, 2));
    else {
      try {
        setDraft(parseEditor(json));
      } catch {
        setError(
          'The advanced JSON is invalid. Correct it before returning to the form, or discard the JSON edits.',
        );
        return;
      }
    }
    setMode(next);
    setIssues([]);
    setError('');
  }
  function save(action: 'current' | 'incomplete' | 'complete') {
    try {
      let candidate: EditorRecord = mode === 'json' ? parseEditor(json) : draft;
      const candidateSpecs = record(candidate.specs);
      if (editingId && candidate.id !== editingId)
        throw new Error('The internal ID must stay unchanged. Use Duplicate for a separate item.');
      if (kind === 'products') {
        if (action === 'complete') candidate = fullProduct(candidate);
        else if (action === 'incomplete' || candidateSpecs.kind === 'incomplete')
          candidate = incompleteProduct(candidate);
      }
      const parsed = itemSchema(kind).safeParse(candidate);
      if (!parsed.success) {
        const mapped = parsed.error.issues.map((issue) => ({
          path: issue.path
            .join('.')
            .replace(/^specs\.(?!available\.)/, pending ? 'specs.available.' : 'specs.'),
          message:
            at(candidate, issue.path.join('.')) === undefined && issue.code !== 'custom'
              ? 'This field is required before the item can be marked complete.'
              : issue.message,
        }));
        setIssues(mapped);
        setError('Please correct the highlighted fields.');
        if (mode === 'form') requestAnimationFrame(() => focusField(mapped[0]?.path ?? ''));
        return;
      }
      if (
        action === 'complete' &&
        candidateSpecs.kind === 'incomplete' &&
        Array.isArray(candidateSpecs.notes) &&
        candidateSpecs.notes.length > 0 &&
        !reviewed
      )
        throw new Error(
          'Review the imported source notes and check the confirmation before saving as complete.',
        );
      setIssues([]);
      setError('');
      onSave(parsed.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to save item.');
    }
  }
  return (
    <section
      ref={editorRef}
      tabIndex={-1}
      className="editor-section library-item-editor"
      aria-label={editingId ? 'Edit library item' : 'New library item'}
    >
      <div className="library-editor-heading">
        <div>
          <h3>{editingId ? 'Edit item' : 'New item'}</h3>
          <p className="editor-help">
            {kind === 'products'
              ? 'Enter known specifications. You can save an incomplete product and finish it later.'
              : 'Enter the cable ratings and conductor groups used for wire selection.'}
          </p>
        </div>
        <span className="data-badge">
          {kind === 'wires'
            ? 'Wire / cable'
            : pending
              ? 'Needs specifications'
              : 'Complete specifications'}
        </span>
      </div>
      <div className="library-editor-tabs" role="tablist" aria-label="Item editor mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'form'}
          onClick={() => switchMode('form')}
        >
          Form fields
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'json'}
          onClick={() => switchMode('json')}
        >
          Advanced JSON
        </button>
      </div>
      {kind === 'products' && pending && (
        <div className="library-pending-note">
          <strong>Save your progress at any time</strong>
          <p>
            This item stays out of calculations until its specifications are complete. Blank fields
            remain unknown.
          </p>
        </div>
      )}
      {(error || saveError) && (
        <div role="alert" className="inline-error library-form-errors">
          <strong>{error || saveError}</strong>
          {issues.length > 0 && (
            <ul>
              {issues.map((issue, i) => (
                <li key={i}>
                  <button type="button" onClick={() => focusField(issue.path)}>
                    {labelFor(issue.path)}: {issue.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {mode === 'form' ? (
        <div role="tabpanel" aria-label="Form fields">
          {draft.category === 'dmx-0-10v-converter' && (
            <p className="library-pending-note">
              Feed this converter from its own AC or DC supply. Add a named 0–10 V output port for
              each independent channel (DIM1, DIM2, etc.). In the project, connect DMX using Control
              from, then add 0–10 V Control Links to the separately powered drivers or fixtures.
            </p>
          )}
          {sections.map(({ section, prefix }, i) => (
            <details className="library-form-section" key={section.title} open={i < 3}>
              <summary>
                <span>{String(i + 1).padStart(2, '0')}</span>
                {section.title}
              </summary>
              {section.hint && <p className="library-section-hint">{section.hint}</p>}
              <div className="library-field-grid">
                {section.fields.map((field) => (
                  <LibraryField
                    key={field.key}
                    field={field}
                    path={prefix ? `${prefix}.${field.key}` : field.key}
                    value={draft}
                    onChange={change}
                    issues={issues}
                    idPrefix={idPrefix}
                  />
                ))}
              </div>
            </details>
          ))}
          {kind === 'products' && (
            <p className="field-hint">
              Category: {categoryLabels[String(draft.category)] ?? String(draft.category)}. Changing
              to a different specification family opens its own fields; values are retained if you
              switch back during this edit.
            </p>
          )}
        </div>
      ) : (
        <div role="tabpanel" aria-label="Advanced JSON">
          <p className="editor-help">
            Advanced editing of the full record. Form edits and JSON edits stay in sync when
            switching modes.
          </p>
          <label htmlFor={`${idPrefix}-json`}>Item JSON</label>
          <textarea
            id={`${idPrefix}-json`}
            className="json-editor"
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setJson(JSON.stringify(draft, null, 2));
              setError('');
              setIssues([]);
            }}
          >
            Discard JSON edits
          </Button>
        </div>
      )}
      {pending && notes.length > 0 && (
        <details className="library-form-section library-source-notes" open>
          <summary>Imported source notes</summary>
          <div className="library-section-content">
            <ul>
              {notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
            {unresolved.length > 0 && (
              <p className="field-hint">Import checklist: {unresolved.join(', ')}.</p>
            )}
            <label className="library-review-check">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />
              <span>
                I have checked these notes and resolved any product or modeling conflicts.
              </span>
            </label>
          </div>
        </details>
      )}
      {draft.sourceData !== undefined && (
        <details className="library-form-section">
          <summary>
            Original ERPNext data <span>read only</span>
          </summary>
          <div className="library-source-data">
            <SourceValues value={draft.sourceData} />
          </div>
        </details>
      )}
      <div className="library-editor-footer">
        <div className="field-hint">Internal ID: {String(draft.id ?? '')}</div>
        <div className="action-bar">
          <Button type="button" onClick={() => save('current')}>
            {mode === 'json'
              ? 'Validate & save JSON'
              : pending
                ? 'Save incomplete product'
                : 'Save changes'}
          </Button>
          {kind === 'products' && mode === 'form' && (
            <Button
              type="button"
              variant="outline"
              onClick={() => save(pending ? 'complete' : 'incomplete')}
            >
              {pending ? 'Save as complete' : 'Save as incomplete'}
            </Button>
          )}
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel edit
          </Button>
        </div>
      </div>
    </section>
  );
}
