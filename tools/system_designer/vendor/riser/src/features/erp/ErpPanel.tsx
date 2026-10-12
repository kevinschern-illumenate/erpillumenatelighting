import { useState } from 'react';
import { z } from 'zod';
import { Button } from '../../components/ui/button';
import { useLibraryStore } from '../../state/library-store';
import {
  defaultMapping,
  MappingSchema,
  previewSync,
  commitSync,
  demoRecords,
  type SyncRow,
} from './sync';
import { downloadFile } from '../../lib/files';

export function ErpPanel() {
  const library = useLibraryStore((s) => s.library),
    update = useLibraryStore((s) => s.update);
  const [mode, setMode] = useState('demo'),
    [groups, setGroups] = useState('Lighting Demo'),
    [mapping, setMapping] = useState(JSON.stringify(defaultMapping, null, 2));
  const [rows, setRows] = useState<SyncRow[]>([]),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false),
    [snapshot, setSnapshot] = useState('');
  async function pull() {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const parsed = MappingSchema.parse(JSON.parse(mapping));
      let records: unknown[];
      if (mode === 'demo') records = demoRecords();
      else {
        const response = await fetch('/api/erp/items', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            groups: groups
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
            fields: ['item_code', ...Object.keys(parsed.fields)],
          }),
        });
        if (!response.ok)
          throw new Error(
            'Local proxy pull failed. Start npm run proxy and check its local configuration.',
          );
        records = z.object({ data: z.array(z.unknown()) }).parse(await response.json()).data;
      }
      setRows(previewSync(records, parsed, library.products));
      setSnapshot(JSON.stringify(library.products));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not preview sync');
      setRows([]);
    } finally {
      setBusy(false);
    }
  }
  const stale = snapshot !== JSON.stringify(library.products);
  return (
    <section className="panel library-panel">
      <h2>ERPNext pull</h2>
      <p className="editor-help">
        Demo mode supplies three clearly marked example items. A real pull uses the optional local
        proxy and your field mapping. Local overrides are preserved and reported before committing.
      </p>
      <div className="action-bar">
        <label>
          Source
          <select
            value={mode}
            onChange={(e) => {
              setMode(e.target.value);
              setRows([]);
            }}
          >
            <option value="demo">Temporary demo data</option>
            <option value="proxy">Configured local ERPNext proxy</option>
          </select>
        </label>
        <label>
          Item groups (comma-separated)
          <input value={groups} onChange={(e) => setGroups(e.target.value)} />
        </label>
        <Button disabled={busy} onClick={() => void pull()}>
          {busy ? 'Pulling…' : 'Preview pull'}
        </Button>
      </div>
      <details>
        <summary>Edit field mapping</summary>
        <p className="editor-help">
          The temporary custom_riser_specs field contains a complete validated specs JSON object.
          Replace the sample fields with your ERPNext custom fields when ready. No electrical
          ratings are inferred.
        </p>
        <textarea
          className="json-editor"
          aria-label="ERP field mapping"
          value={mapping}
          onChange={(e) => {
            setMapping(e.target.value);
            setRows([]);
          }}
        />
        <Button variant="outline" onClick={() => downloadFile('erp-mapping.json', mapping)}>
          Download mapping
        </Button>
      </details>
      {!!rows.length && (
        <>
          <p>
            {['added', 'updated', 'unchanged', 'conflict', 'invalid']
              .map((s) => `${rows.filter((r) => r.status === s).length} ${s}`)
              .join(' · ')}
          </p>
          <div className="wide-table">
            <table>
              <thead>
                <tr>
                  <th>Item code</th>
                  <th>Result</th>
                  <th>Preserved local fields / validation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.code}-${i}`}>
                    <td>{r.code}</td>
                    <td>{r.status}</td>
                    <td>{[...r.conflicts, ...r.errors].join('; ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button
            disabled={stale || rows.some((r) => r.status === 'invalid')}
            onClick={() => {
              try {
                update('products', commitSync(library.products, rows));
                setMessage(
                  'Pull committed. Local overrides were preserved. Undo restores the previous library.',
                );
                setRows([]);
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Commit valid pull
          </Button>
          {stale && (
            <p className="editor-help">
              The library changed after this preview. Preview the pull again.
            </p>
          )}
        </>
      )}
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
    </section>
  );
}
