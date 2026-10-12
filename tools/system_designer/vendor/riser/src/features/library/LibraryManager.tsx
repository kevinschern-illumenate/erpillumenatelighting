import { useMemo, useState } from 'react';
import type { ColDef } from 'ag-grid-community';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { DataGrid } from '../../components/DataGrid';
import { useLibraryStore } from '../../state/library-store';
import { ProductLibrarySchema, type CatalogItem } from '../../schemas/catalog';
import { WireLibrarySchema, type WireType } from '../../schemas/wire';
import { LibrarySnapshotSchema } from '../../schemas/library';
import { seedProducts, seedWires } from '../../data/seeds';
import { downloadFile } from '../../lib/files';
import { saveLibrary } from '../../storage/library';
import { LibraryItemEditor } from './LibraryItemEditor';
import { newLibraryItem } from './editor-model';
import {
  autoMap,
  commitImport,
  exportCsv,
  fieldsFor,
  previewImport,
  readCsv,
  type LibraryKind,
  type LibraryRow,
} from './import';

export function LibraryManager({ kind }: { kind: LibraryKind }) {
  const library = useLibraryStore((s) => s.library);
  const rows = library[kind];
  const ready = useLibraryStore((s) => s.ready);
  const status = useLibraryStore((s) => s.status);
  const storageError = useLibraryStore((s) => s.error);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<LibraryRow[]>([]);
  const [editor, setEditor] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [source, setSource] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [showImport, setShowImport] = useState(false);
  const categories = [
    ...new Set((kind === 'products' ? seedProducts : seedWires).map((r) => r.category)),
  ];
  const [templateCategory, setTemplateCategory] = useState<string>(categories[0]!);
  const parsed = useMemo(() => readCsv(source), [source]);
  const preview = useMemo(
    () => previewImport(kind, parsed.rows, mapping, rows),
    [kind, parsed.rows, mapping, rows],
  );
  const fields = useMemo(() => fieldsFor(kind), [kind]);
  const filtered: LibraryRow[] = rows.filter((r) =>
    JSON.stringify(r).toLowerCase().includes(query.toLowerCase()),
  );
  const incompleteCount =
    kind === 'products' ? library.products.filter((p) => p.specs.kind === 'incomplete').length : 0;
  const columns = useMemo<ColDef<LibraryRow>[]>(
    () =>
      kind === 'products'
        ? [
            {
              headerName: 'SKU',
              valueGetter: (p) => (p.data && 'sku' in p.data ? p.data.sku : ''),
              minWidth: 180,
            },
            { field: 'model', editable: true, minWidth: 220 },
            { field: 'brand', editable: true },
            { field: 'category' },
            {
              headerName: 'Specifications',
              minWidth: 175,
              valueGetter: (p) =>
                p.data && 'specs' in p.data && p.data.specs.kind === 'incomplete'
                  ? 'Needs specifications'
                  : 'Complete',
            },
            { field: 'isExample', headerName: 'Example', cellDataType: 'boolean' },
            { field: 'description', editable: true, minWidth: 250 },
          ]
        : [
            { field: 'name', editable: true, minWidth: 240 },
            { field: 'listing', minWidth: 140 },
            { field: 'category' },
            { field: 'verify', headerName: 'Needs verification' },
            { field: 'riserLabel', editable: true, minWidth: 180 },
          ],
    [kind],
  );
  function replace(next: LibraryRow[]) {
    if (kind === 'products')
      useLibraryStore.getState().update('products', ProductLibrarySchema.parse(next));
    else useLibraryStore.getState().update('wires', WireLibrarySchema.parse(next));
  }
  function edit(row: LibraryRow | undefined) {
    if (!row) return;
    setEditingId(row.id);
    setEditor(JSON.stringify(row, null, 2));
    setError('');
  }
  function create() {
    setEditingId(null);
    setEditor(JSON.stringify(newLibraryItem(kind, `new-${crypto.randomUUID()}`), null, 2));
    setError('');
  }
  function commitEditor(item: LibraryRow) {
    try {
      if (editingId && item.id !== editingId)
        throw new Error('Keep the stable ID unchanged when editing. Duplicate to make a new item.');
      if ('localOverrides' in item && editingId) {
        const old = rows.find((r) => r.id === editingId)!;
        const changed = Object.keys(item).filter(
          (f) =>
            !['id', 'erpItemCode', 'localOverrides'].includes(f) &&
            JSON.stringify((item as unknown as Record<string, unknown>)[f]) !==
              JSON.stringify((old as unknown as Record<string, unknown>)[f]),
        );
        item.localOverrides = [...new Set([...item.localOverrides, ...changed])];
      }
      replace(editingId ? rows.map((r) => (r.id === editingId ? item : r)) : [...rows, item]);
      setEditor('');
      setMessage('Library item saved.');
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid item');
    }
  }
  function uploadCsv(text: string) {
    setSource(text);
    const parsed = readCsv(text);
    setMapping(autoMap(parsed.headers, fields));
    setShowImport(true);
    setError('');
  }
  function template() {
    const sample = (kind === 'products' ? seedProducts : seedWires).find(
      (r) => r.category === templateCategory,
    )!;
    downloadFile(`${templateCategory}-template.csv`, exportCsv([sample]), 'text/csv;charset=utf-8');
  }
  const errors = preview.filter((r) => r.action === 'error').length;
  return (
    <section className="panel library-panel">
      <div className="library-panel-top">
        <div>
          <h2>{kind === 'products' ? 'Product library' : 'Wire library'}</h2>
          <p>Validate edits, preview imports, and keep local changes in this browser.</p>
        </div>
        <span className="data-badge">
          {status === 'saved'
            ? 'Library saved'
            : status === 'saving'
              ? 'Saving library…'
              : 'Save failed'}
        </span>
      </div>
      {storageError && (
        <div role="alert" className="inline-error">
          {storageError}
          <Button
            onClick={() =>
              void saveLibrary(library)
                .then(() => useLibraryStore.setState({ status: 'saved', error: '' }))
                .catch(() => undefined)
            }
          >
            Retry library save
          </Button>
        </div>
      )}
      {incompleteCount > 0 && (
        <p className="reference-note" role="note">
          {incompleteCount} products need specifications. They are saved in the Library with their
          available data, but cannot be selected for calculations. Select a product and choose Edit
          selected to see what is missing.
        </p>
      )}
      <div className="action-bar">
        <Input
          aria-label={`Search ${kind}`}
          placeholder={`Search ${kind}…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button onClick={create} disabled={!ready}>
          New item
        </Button>
        <Button
          variant="outline"
          disabled={selected.length !== 1 || !ready}
          onClick={() => edit(rows.find((r) => r.id === selected[0]?.id))}
        >
          Edit selected
        </Button>
        <Button
          variant="outline"
          disabled={selected.length !== 1 || !ready}
          onClick={() => {
            const copy = structuredClone(selected[0]!);
            const suffix = crypto.randomUUID().slice(0, 6);
            copy.id += `-${suffix}`;
            if ('sku' in copy) copy.sku += `-COPY-${suffix}`;
            setEditingId(null);
            setEditor(JSON.stringify(copy, null, 2));
          }}
        >
          Duplicate
        </Button>
        <Button
          variant="outline"
          disabled={!selected.length || !ready}
          onClick={() => {
            replace(rows.filter((r) => !selected.some((s) => s.id === r.id)));
            setSelected([]);
            setMessage('Deleted selected items. Undo restores them.');
          }}
        >
          Delete selected
        </Button>
      </div>
      <DataGrid<LibraryRow>
        rows={filtered}
        columns={columns}
        onSelect={setSelected}
        onEdit={(e) => {
          try {
            if (!e.data || !e.colDef.field) return;
            const next = { ...e.data, [e.colDef.field]: e.newValue };
            if ('localOverrides' in next)
              next.localOverrides = [...new Set([...next.localOverrides, e.colDef.field])];
            replace(rows.map((r) => (r.id === next.id ? next : r)));
            setError('');
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Invalid edit');
          }
        }}
      />
      <div className="action-bar">
        <Button
          variant="outline"
          onClick={() => downloadFile(`${kind}.csv`, exportCsv(rows), 'text/csv;charset=utf-8')}
        >
          Export CSV
        </Button>
        <select
          aria-label={`${kind} template category`}
          value={templateCategory}
          onChange={(e) => setTemplateCategory(e.target.value)}
        >
          {categories.map((category) => (
            <option key={category}>{category}</option>
          ))}
        </select>
        <Button variant="outline" onClick={template}>
          Download template
        </Button>
        <label className="file-button">
          Import CSV
          <input
            aria-label={`Import ${kind} CSV`}
            type="file"
            accept=".csv,.tsv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void f.text().then(uploadCsv);
              e.target.value = '';
            }}
          />
        </label>
        <Button
          variant="outline"
          onClick={() => downloadFile('riser-library.json', JSON.stringify(library, null, 2))}
        >
          Backup library JSON
        </Button>
        <label className="file-button">
          Restore library JSON
          <input
            aria-label="Restore library JSON"
            type="file"
            accept=".json"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f)
                void f.text().then((s) => {
                  try {
                    useLibraryStore.getState().replace(LibrarySnapshotSchema.parse(JSON.parse(s)));
                    setMessage('Library restored. Undo restores the previous library.');
                  } catch (err) {
                    setError(String(err));
                  }
                });
              e.target.value = '';
            }}
          />
        </label>
      </div>
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      {error && !editor && (
        <pre role="alert" className="inline-error">
          {error}
        </pre>
      )}
      {editor && (
        <LibraryItemEditor
          key={editor}
          initialValue={editor}
          kind={kind}
          editingId={editingId}
          onSave={commitEditor}
          onCancel={() => {
            setEditor('');
            setError('');
          }}
          saveError={error}
        />
      )}
      {showImport && (
        <section className="editor-section">
          <h3>Map columns and preview</h3>
          <p className="editor-help">
            Rows upsert by {kind === 'products' ? 'SKU' : 'wire ID'}. Unmapped existing values are
            preserved. Incomplete product records are stored as Needs specifications and excluded
            from calculation choices. No electrical ratings are inferred. Fix every error before
            committing.
          </p>
          <div className="mapping-grid">
            {parsed.headers.map((h) => (
              <label key={h}>
                {h}
                <select
                  value={mapping[h] ?? ''}
                  onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}
                >
                  <option value="">Ignore column</option>
                  {fields.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <p className="import-summary">
            {preview.length} rows · {preview.filter((r) => r.action === 'new').length} new ·{' '}
            {preview.filter((r) => r.action === 'updated').length} updated ·{' '}
            {preview.filter((r) => r.action === 'unchanged').length} unchanged · {errors} errors
          </p>
          {parsed.errors.map((e) => (
            <p role="alert" key={e} className="inline-error">
              {e}
            </p>
          ))}
          <div className="import-preview">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Row / key</th>
                  <th>Action</th>
                  <th>Validation</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((r) => (
                  <tr key={r.row}>
                    <td>
                      {r.row} · {r.key}
                    </td>
                    <td>{r.action}</td>
                    <td>
                      {r.errors.join('; ') ||
                        (r.value && 'specs' in r.value && r.value.specs.kind === 'incomplete'
                          ? `Needs specifications: ${r.value.specs.missingFields.join(', ')}`
                          : 'Valid')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="action-bar">
            <Button
              disabled={!ready || !preview.length || errors > 0 || parsed.errors.length > 0}
              onClick={() => {
                try {
                  replace(commitImport(rows, preview));
                  setShowImport(false);
                  setMessage(`${preview.length} rows imported.`);
                } catch (err) {
                  setError(String(err));
                }
              }}
            >
              Commit import
            </Button>
            <Button variant="outline" onClick={() => setShowImport(false)}>
              Cancel import
            </Button>
          </div>
        </section>
      )}
    </section>
  );
}

export type ProductRow = CatalogItem;
export type WireRow = WireType;
