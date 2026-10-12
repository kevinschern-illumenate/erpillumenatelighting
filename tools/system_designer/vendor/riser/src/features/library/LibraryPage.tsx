import { useState } from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { BookOpen, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { seedCodeTables, seedLayers, seedNotes, seedTitleBlocks } from '@/data/seeds';
import { CodeTableSchema, type CodeTable } from '@/schemas/reference-data';
import { useLibraryStore } from '@/state/library-store';
import { LibraryManager } from './LibraryManager';
import { ErpPanel } from '../erp/ErpPanel';

function JsonView({ value }: { value: unknown }) {
  return <pre className="data-json">{JSON.stringify(value, null, 2)}</pre>;
}

function CodeEditor({
  table,
  loaded,
  onSaved,
  onReset,
}: {
  table: CodeTable;
  loaded: boolean;
  onSaved: (table: CodeTable) => void;
  onReset: (id: string) => void;
}) {
  const [text, setText] = useState(JSON.stringify(table, null, 2));
  const [previousTable, setPreviousTable] = useState(table);
  if (previousTable !== table) {
    setPreviousTable(table);
    setText(JSON.stringify(table, null, 2));
  }
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save() {
    setError('');
    setMessage('');
    let input: unknown;
    try {
      input = JSON.parse(text);
    } catch {
      setError('Invalid JSON. Fix the syntax before saving.');
      return;
    }
    const result = CodeTableSchema.safeParse(input);
    if (!result.success) {
      setError(result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('\n'));
      return;
    }
    if (result.data.id !== table.id || result.data.kind !== table.kind) {
      setError(
        'Keep the table ID and kind unchanged. Edit values and source metadata within this table.',
      );
      return;
    }
    if (
      result.data.source.edition !== table.source.edition ||
      result.data.source.table !== table.source.table
    ) {
      setError(
        'Keep this table’s code edition and table reference unchanged. A different edition requires a separate table, not relabelling these values.',
      );
      return;
    }
    setBusy(true);
    try {
      onSaved(result.data);
      setText(JSON.stringify(result.data, null, 2));
      setMessage('Code table saved locally.');
    } catch {
      setError('Could not save the table. Your edits remain in the editor; retry before leaving.');
    } finally {
      setBusy(false);
    }
  }
  async function reset() {
    setBusy(true);
    setError('');
    try {
      const seed = seedCodeTables.find((t) => t.id === table.id)!;
      setText(JSON.stringify(seed, null, 2));
      onReset(table.id);
      setMessage('Restored the shipped seed table.');
    } catch {
      setError('Could not restore the seed. Local edits remain unchanged.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="code-editor">
      <div className="reference-note">
        <BookOpen size={20} />
        <div>
          <strong>
            {table.source.standard} · {table.source.edition} · {table.source.table}
          </strong>
          <p>{table.comment}</p>
          <a href={table.source.url} target="_blank" rel="noreferrer">
            Source reference ↗
          </a>
          <span className="source-status">{table.source.verification.replaceAll('-', ' ')}</span>
        </div>
      </div>
      {'status' in table && table.status === 'unavailable' && (
        <p className="library-notice">
          Table 9 values were not supplied. Effective-Z remains unavailable; no resistance-table
          substitution is made.
        </p>
      )}
      <label htmlFor="code-table-json">Table JSON</label>
      <p className="editor-help">
        Values, units and provenance are validated together. Save before changing tables or leaving
        this editor. Changes stay in this browser; Restore seed returns the shipped JSON.
      </p>
      <textarea
        id="code-table-json"
        className="json-editor"
        spellCheck={false}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setMessage('');
        }}
        disabled={!loaded || busy}
      />
      {error && (
        <pre role="alert" className="inline-error">
          {error}
        </pre>
      )}
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      <div className="editor-actions">
        <Button onClick={() => void save()} disabled={!loaded || busy}>
          Validate & save table
        </Button>
        <Button variant="outline" onClick={() => void reset()} disabled={!loaded || busy}>
          Restore seed
        </Button>
      </div>
    </div>
  );
}

function CodeTables() {
  const library = useLibraryStore((s) => s.library);
  const loaded = useLibraryStore((s) => s.ready);
  const error = useLibraryStore((s) => s.error);
  const [selected, setSelected] = useState(seedCodeTables[0]!.id);
  const tables = library.codeTables;
  const overrides = tables.filter(
    (t) => JSON.stringify(t) !== JSON.stringify(seedCodeTables.find((s) => s.id === t.id)),
  );
  const setOverrides = (updater: (rows: typeof tables) => typeof tables) =>
    useLibraryStore.getState().update('codeTables', updater(tables));
  const table = tables.find((t) => t.id === selected)!;
  return (
    <section className="panel library-panel">
      <div className="library-panel-top">
        <div>
          <h2>Code reference tables</h2>
          <p>2023 seed values · verify against the adopted edition.</p>
        </div>
        <span className="data-badge">3 populated + Table 9 pending</span>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="table-picker">
        <label htmlFor="code-table-picker">Select code table</label>
        <Select
          id="code-table-picker"
          value={selected}
          onValueChange={setSelected}
          options={tables.map((t) => ({
            value: t.id,
            label: `${t.source.table} · ${t.units}${overrides.some((o) => o.id === t.id) ? ' · edited' : ''}`,
          }))}
        />
      </div>
      {loaded && table ? (
        <CodeEditor
          key={table.id}
          table={table}
          loaded={loaded}
          onSaved={(value) =>
            setOverrides((rows) => [...rows.filter((t) => t.id !== value.id), value])
          }
          onReset={(id) =>
            setOverrides((rows) =>
              rows.map((t) => (t.id === id ? seedCodeTables.find((s) => s.id === id)! : t)),
            )
          }
        />
      ) : (
        <p className="editor-help">
          {error ? 'Resolve the storage error before editing.' : 'Loading saved code tables…'}
        </p>
      )}
    </section>
  );
}

export function LibraryPage() {
  const { products, wires } = useLibraryStore((s) => s.library);
  return (
    <div className="library-workspace">
      <div className="library-stats">
        <div>
          <strong>{products.length}</strong>
          <span>Catalog products</span>
        </div>
        <div>
          <strong>{wires.length}</strong>
          <span>Wire templates</span>
        </div>
        <div>
          <strong>{seedLayers.layers.length}</strong>
          <span>Drawing layers</span>
        </div>
        <div>
          <strong>{seedTitleBlocks.length}</strong>
          <span>Sheet templates</span>
        </div>
        <div className="schema-status">
          <Check size={19} />
          <span>Seed schemas validated</span>
        </div>
      </div>
      <Tabs.Root defaultValue="products">
        <Tabs.List className="library-tabs" aria-label="Library workspace">
          {[
            ['products', 'Products'],
            ['wires', 'Wires'],
            ['code', 'Code tables'],
            ['drawing', 'Drawing standards'],
            ['notes', 'General notes'],
            ['erp', 'ERPNext Sync'],
          ].map(([value, label]) => (
            <Tabs.Trigger key={value} value={value!}>
              {label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="products">
          <LibraryManager kind="products" />
        </Tabs.Content>
        <Tabs.Content value="wires">
          <LibraryManager kind="wires" />
        </Tabs.Content>
        <Tabs.Content value="code">
          <CodeTables />
        </Tabs.Content>
        <Tabs.Content value="drawing">
          <div className="standards-layout">
            <section className="panel library-panel">
              <div className="library-panel-top">
                <div>
                  <h2>Sheet templates</h2>
                  <p>Paper inches · lower-left origin · right-side title block.</p>
                </div>
              </div>
              {seedTitleBlocks.map((sheet) => (
                <details className="library-detail" key={sheet.id}>
                  <summary>
                    <strong>{sheet.sheetSize.replace('_', ' ')}</strong>
                    <span>
                      {sheet.widthIn} × {sheet.heightIn} in
                    </span>
                  </summary>
                  <p>
                    Minimum text: 3/32 in. Reference square: 1 × 1 in. ilLumenate Lighting uses the
                    supplied monochrome vector logo.
                  </p>
                  <JsonView value={sheet} />
                </details>
              ))}
            </section>
            <section className="panel library-panel">
              <div className="library-panel-top">
                <div>
                  <h2>Drawing layers</h2>
                  <p>Line types and weights remain meaningful in monochrome.</p>
                </div>
              </div>
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Layer</th>
                      <th>Line type</th>
                      <th>Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seedLayers.layers.map((layer) => (
                      <tr key={layer.name}>
                        <td>
                          <strong>{layer.name}</strong>
                          <span>
                            {layer.export ? layer.description : 'Preview only · NEVER EXPORTED'}
                          </span>
                        </td>
                        <td>{layer.linetype}</td>
                        <td>{layer.lineweightMm} mm</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </Tabs.Content>
        <Tabs.Content value="notes">
          <section className="panel library-panel">
            <div className="library-panel-top">
              <div>
                <h2>Draft general notes</h2>
                <p>Review against the actual equipment and project requirements before issue.</p>
              </div>
              <span className="data-badge">{seedNotes.length} notes</span>
            </div>
            <div className="note-list">
              {seedNotes.map((note) => (
                <article key={note.id}>
                  <span>{note.id}</span>
                  <div>
                    <p>{note.text}</p>
                    <small>{note.classification.replaceAll('-', ' ')}</small>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </Tabs.Content>
        <Tabs.Content value="erp">
          <ErpPanel />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
