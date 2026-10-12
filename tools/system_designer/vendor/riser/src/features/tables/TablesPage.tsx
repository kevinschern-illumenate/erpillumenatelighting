import { lazy, Suspense, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
const MiniDrawing = lazy(() =>
  import('../drawing/DrawingPage').then((m) => ({ default: m.MiniDrawing })),
);
import * as Tabs from '@radix-ui/react-tabs';
import Papa from 'papaparse';
import type { ColDef } from 'ag-grid-community';
import { DataGrid } from '../../components/DataGrid';
import { PickerEditor } from '../../components/PickerEditor';
import { Button } from '../../components/ui/button';
import { useEngine } from '../../hooks/use-engine';
import { useProjectStore } from '../../state/project-store';
import {
  EquipmentSchema,
  LoadSchema,
  SourceSchema,
  ControlLinkSchema,
  type Project,
} from '../../schemas/project';
import { EnvironmentSchema, ProtocolSchema } from '../../schemas/common';
import { powerPortOptions, controlPortOptions, parsePort } from '../../engine/ports';
import { demoProject } from '../../data/demo';
import { downloadFile } from '../../lib/files';
import { ControlLinkForm } from './ControlLinkForm';

type TableKey = 'sources' | 'equipment' | 'loads' | 'controlLinks';
type Row = Project[TableKey][number];
const names: Record<TableKey, string> = {
  sources: 'Sources',
  equipment: 'Equipment',
  loads: 'Loads',
  controlLinks: 'Control Links',
};
const schemas = {
  sources: SourceSchema,
  equipment: EquipmentSchema,
  loads: LoadSchema,
  controlLinks: ControlLinkSchema,
};
const fields: Record<TableKey, string[]> = {
  sources: [
    'tag',
    'panel',
    'circuit',
    'voltage',
    'phase',
    'breakerA',
    'poles',
    'switching',
    'notes',
  ],
  equipment: [
    'tag',
    'catalogId',
    'qty',
    'location',
    'enclosure',
    'fedFrom',
    'feedLengthFt',
    'controlFrom',
    'controlLengthFt',
    'chainOrder',
    'universe',
    'startAddress',
    'terminatorPresent',
    'env',
    'notes',
  ],
  loads: [
    'typeTag',
    'catalogId',
    'zone',
    'enclosure',
    'qty',
    'lengthFt',
    'fedFrom',
    'homeRunLengthFt',
    'interFixtureLengthFt',
    'feedMethod',
    'feeds',
    'env',
    'notes',
  ],
  controlLinks: ['protocol', 'from', 'to', 'lengthFt', 'env', 'universe', 'notes'],
};
const numeric = new Set([
  'voltage',
  'breakerA',
  'poles',
  'qty',
  'lengthFt',
  'feedLengthFt',
  'controlLengthFt',
  'chainOrder',
  'universe',
  'homeRunLengthFt',
  'interFixtureLengthFt',
  'feeds',
]);
function read(row: Row, field: string): unknown {
  if (['universe', 'startAddress', 'terminatorPresent'].includes(field) && 'dmx' in row)
    return row.dmx?.[field as keyof NonNullable<typeof row.dmx>];
  const value = (row as unknown as Record<string, unknown>)[field];
  if (value && typeof value === 'object' && 'ref' in value)
    return `${value.ref}${'port' in value && value.port ? `::${value.port}` : ''}`;
  return value ?? '';
}
function incomingControlLinks(project: Project, row: Row) {
  return project.controlLinks.filter(
    (link) => link.to.ref === row.id || ('tag' in row && link.to.ref === row.tag),
  );
}
export function TablesPage() {
  const { project, library, result } = useEngine();
  const location = useLocation();
  const selectedId = new URLSearchParams(location.search).get('row');
  const initialTab =
    (Object.keys(names) as TableKey[]).find((key) =>
      project[key].some((row) => row.id === selectedId),
    ) ?? 'sources';
  const [tab, setTab] = useState<TableKey>(initialTab);
  const [selected, setSelected] = useState<Row[]>([]);
  const [error, setError] = useState('');
  const [paste, setPaste] = useState('');
  const [showPaste, setShowPaste] = useState(false);
  const [bulkField, setBulkField] = useState('notes');
  const [bulkValue, setBulkValue] = useState('');
  const [mini, setMini] = useState(false);
  const [linkEditor, setLinkEditor] = useState<
    Project['controlLinks'][number] | 'DMX512' | '0-10V' | null
  >(null);
  const rows = project[tab] as Row[];
  function nextTag(prefix: string) {
    let i = 1;
    const used = new Set([...project.sources, ...project.equipment].map((r) => r.tag));
    while (used.has(`${prefix}${i}`)) i++;
    return `${prefix}${i}`;
  }
  function blank(kind: TableKey): Row {
    const id = crypto.randomUUID();
    if (kind === 'sources') {
      const tag = nextTag('LP-1/');
      return SourceSchema.parse({
        id,
        tag,
        panel: 'LP-1',
        circuit: tag.split('/')[1],
        voltage: 120,
        phase: '1PH',
        breakerA: 20,
        poles: 1,
        switching: 'none',
      });
    }
    if (kind === 'equipment') {
      const item =
        library.products.find((p) => p.specs.kind === 'psu') ??
        library.products.find((p) => !['tape', 'fixture', 'incomplete'].includes(p.specs.kind));
      if (!item) throw new Error('Add an equipment product to the library first.');
      return EquipmentSchema.parse({
        id,
        tag: nextTag('PS-'),
        catalogId: item.id,
        category: item.category,
        qty: 1,
        location: 'Unassigned',
        fedFrom: { ref: project.sources[0]?.tag ?? 'SELECT SOURCE' },
        feedLengthFt: 0,
        env: 'raceway',
      });
    }
    if (kind === 'loads') {
      const item = library.products.find(
        (p) => p.specs.kind === 'tape' || p.specs.kind === 'fixture',
      );
      if (!item) throw new Error('Add a tape or fixture product first.');
      return LoadSchema.parse({
        id,
        typeTag: 'T1',
        zone: '',
        catalogId: item.id,
        ...(item.specs.kind === 'tape' ? { lengthFt: 1 } : { qty: 1 }),
        fedFrom: { ref: project.equipment[0]?.tag ?? 'SELECT SUPPLY', port: 'OUT1' },
        homeRunLengthFt: 0,
        feedMethod: 'end',
        env: 'riser',
      });
    }
    return ControlLinkSchema.parse({
      id,
      from: { ref: project.equipment[0]?.tag ?? 'SELECT SOURCE' },
      to: { ref: project.equipment[1]?.tag ?? 'SELECT RECEIVER' },
      protocol: 'DMX512',
      lengthFt: 0,
      env: 'riser',
    });
  }
  function change(row: Row, field: string, raw: unknown): Row {
    const next = structuredClone(row) as unknown as Record<string, unknown>;
    let value: unknown = raw;
    if (numeric.has(field)) value = raw === '' || raw === undefined ? undefined : Number(raw);
    if (field.endsWith('Ft') && project.settings.units === 'm' && typeof value === 'number')
      value /= 0.3048;
    if (['fedFrom', 'controlFrom', 'from', 'to'].includes(field)) {
      if (!raw && field === 'controlFrom') {
        delete next.controlFrom;
        delete next.controlLengthFt;
      } else {
        next[field] = parsePort(String(raw));
        if (field === 'controlFrom' && next.controlLengthFt === undefined) next.controlLengthFt = 0;
      }
    } else if (
      ['universe', 'startAddress', 'terminatorPresent'].includes(field) &&
      tab === 'equipment'
    ) {
      next.dmx = {
        universe: 1,
        startAddress: 'auto',
        ...((next.dmx as object) ?? {}),
        [field]:
          field === 'startAddress'
            ? raw === 'auto'
              ? 'auto'
              : Number(raw)
            : field === 'terminatorPresent'
              ? raw === true || raw === 'true'
              : value,
      };
    } else if (field === 'enclosure') {
      if (String(value ?? '').trim()) next.enclosure = String(value).trim();
      else delete next.enclosure;
    } else next[field] = value;
    if (field === 'catalogId') {
      const item = library.products.find((p) => p.id === raw || p.sku === raw);
      if (!item) throw new Error('Choose an existing catalog SKU.');
      if (item.specs.kind === 'incomplete')
        throw new Error(
          `${item.sku}: Needs specifications. Complete this product in Libraries first.`,
        );
      next.catalogId = item.id;
      if (tab === 'equipment') next.category = item.category;
      if (tab === 'equipment' && item.category === 'dmx-0-10v-converter')
        next.dmx ??= { universe: 1, startAddress: 'auto' };
      if (tab === 'loads') {
        if (item.specs.kind === 'tape') {
          delete next.qty;
          next.lengthFt ??= 1;
        } else {
          delete next.lengthFt;
          next.qty ??= 1;
        }
      }
    }
    if (field === 'feedMethod') {
      if (raw === 'multi-feed') next.feeds ??= 2;
      else delete next.feeds;
    }
    return schemas[tab].parse(next);
  }
  function apply(next: Row[]) {
    try {
      useProjectStore.getState().updateProject({ [tab]: next });
      setError('');
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid rows');
    }
  }
  const columns = useMemo<ColDef<Row>[]>(
    () => [
      {
        colId: 'status',
        headerName: 'QA',
        width: 64,
        minWidth: 64,
        maxWidth: 64,
        pinned: 'left',
        valueGetter: (p) =>
          result.messages.some((m) => m.entityRef === p.data?.id && m.severity === 'error')
            ? '🔴'
            : result.messages.some((m) => m.entityRef === p.data?.id && m.severity === 'warning')
              ? '🟠'
              : '🟢',
        tooltipValueGetter: (p) =>
          result.messages
            .filter((m) => m.entityRef === p.data?.id)
            .map((m) => `${m.code}: ${m.text}`)
            .join('\n') || 'No issues',
      },
      ...fields[tab].map((field): ColDef<Row> => {
        const col: ColDef<Row> = {
          colId: field,
          headerName:
            field.replace(/Ft$/, '').replace(/([A-Z])/g, ' $1') +
            (field.endsWith('Ft') ? ` (${project.settings.units})` : ''),
          editable: true,
          minWidth: ['notes', 'catalogId', 'fedFrom', 'controlFrom', 'from', 'to'].includes(field)
            ? 190
            : 115,
          valueGetter: (p) =>
            p.data
              ? field.endsWith('Ft') &&
                project.settings.units === 'm' &&
                typeof read(p.data, field) === 'number'
                ? Number((Number(read(p.data, field)) * 0.3048).toFixed(3))
                : read(p.data, field)
              : '',
          cellDataType: false,
        };
        if (field === 'catalogId') {
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = {
            options: library.products
              .filter((p) =>
                tab === 'loads'
                  ? ['tape', 'fixture'].includes(p.specs.kind)
                  : !['tape', 'fixture', 'incomplete'].includes(p.specs.kind),
              )
              .map((p) => ({ value: p.id, label: `${p.sku} · ${p.model} · ${p.description}` })),
          };
          col.valueFormatter = (p) =>
            library.products.find((i) => i.id === p.value)?.sku ?? p.value;
        }
        if (field === 'fedFrom') {
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = (p: { data: Row }) => ({
            options: powerPortOptions(project, library.products, p.data.id),
          });
        }
        if (['controlFrom', 'from', 'to'].includes(field)) {
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = (p: { data: Row }) => ({
            options: controlPortOptions(
              project,
              library.products,
              field === 'to' ? 'in' : 'out',
              'protocol' in p.data ? p.data.protocol : undefined,
              field === 'controlFrom'
                ? p.data.id
                : 'from' in p.data && 'to' in p.data
                  ? field === 'from'
                    ? p.data.to.ref
                    : p.data.from.ref
                  : undefined,
            ),
          });
          if (field === 'to')
            col.valueFormatter = (p) => {
              if (!p.value) return '';
              const ref = parsePort(String(p.value));
              const load = project.loads.find((l) => l.id === ref.ref);
              return load
                ? `${load.typeTag}${load.zone ? ` · ${load.zone}` : ''}${ref.port ? ` / ${ref.port}` : ''}`
                : p.value;
            };
        }
        if (tab === 'equipment' && ['controlFrom', 'controlLengthFt'].includes(field)) {
          const originalGetter = col.valueGetter as (p: { data?: Row }) => unknown;
          col.valueGetter = (p) => {
            const links = p.data ? incomingControlLinks(project, p.data) : [];
            return links.length
              ? field === 'controlFrom'
                ? links
                    .map((link) => `${link.from.ref}${link.from.port ? `::${link.from.port}` : ''}`)
                    .join(', ')
                : 'See Control Links'
              : originalGetter(p);
          };
          col.editable = (p) => !p.data || incomingControlLinks(project, p.data).length === 0;
          col.tooltipValueGetter = (p) =>
            p.data && incomingControlLinks(project, p.data).length
              ? 'Edit this incoming connection and its cable length in Control Links.'
              : '';
        }
        const options =
          field === 'env'
            ? EnvironmentSchema.options
            : field === 'protocol'
              ? ProtocolSchema.options
              : field === 'phase'
                ? ['1PH', '3PH']
                : field === 'switching'
                  ? ['none', 'relay', 'phase-forward', 'phase-reverse', '0-10V', 'lutron-module']
                  : field === 'feedMethod'
                    ? ['end', 'double-end', 'center', 'multi-feed']
                    : field === 'terminatorPresent'
                      ? ['true', 'false']
                      : null;
        if (options) {
          col.cellEditor = 'agSelectCellEditor';
          col.cellEditorParams = { values: options };
        }
        return col;
      }),
      ...(tab === 'equipment' || tab === 'loads'
        ? [
            {
              colId: 'spec',
              headerName: 'Catalog specs (read only)',
              minWidth: 240,
              valueGetter: (p: { data?: Row }) => {
                const row = p.data;
                const item =
                  row && 'catalogId' in row
                    ? library.products.find((i) => i.id === row.catalogId)
                    : undefined;
                const s = item?.specs;
                if (!s) return '';
                return s.kind === 'tape'
                  ? `${s.voltage} V · ${s.wPerFtMax} W/ft · ${s.channels} ch`
                  : 'ratedW' in s
                    ? `${s.ratedW} W · ${s.outputType} ${s.outputV ?? s.outputmA}${s.outputType === 'CC' ? ' mA' : ' V'}`
                    : s.kind === 'fixture'
                      ? `${s.watts} W · ${s.inputV} V`
                      : s.kind;
              },
            },
          ]
        : []),
    ],
    [tab, project, library.products, result.messages],
  );
  const pastePreview = useMemo(() => {
    if (!paste.trim()) return { rows: [] as Row[], errors: [] as string[] };
    const parsed = Papa.parse<string[]>(paste.trim(), {
      delimiter: '\t',
      skipEmptyLines: 'greedy',
    });
    const first = parsed.data[0] ?? [];
    const hasHeader = first.every((h) => fields[tab].includes(h.trim()));
    const headers = hasHeader ? first.map((h) => h.trim()) : fields[tab];
    const incoming = hasHeader ? parsed.data.slice(1) : parsed.data;
    const errors: string[] = [];
    const imported: Row[] = [];
    incoming.forEach((cells, i) => {
      try {
        let row = blank(tab);
        if ('tag' in row && !headers.includes('tag')) {
          const prefix = tab === 'sources' ? 'LP-1/' : 'PS-';
          const taken = new Set(
            [...project.sources, ...project.equipment, ...imported].flatMap((r) =>
              'tag' in r ? [r.tag] : [],
            ),
          );
          let n = 1;
          while (taken.has(`${prefix}${n}`)) n++;
          row.tag = `${prefix}${n}`;
          if ('circuit' in row) row.circuit = String(n);
        }
        for (let c = 0; c < cells.length; c++) {
          if (cells[c] !== '' && headers[c]) row = change(row, headers[c]!, cells[c]);
        }
        imported.push(row);
      } catch (e) {
        errors.push(`Row ${i + 1}: ${e instanceof Error ? e.message : 'Invalid value'}`);
      }
    });
    return { rows: imported, errors };
    // Explicit text buffer is the transaction boundary; current catalogs/project are inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paste, tab, library.products, project]);
  return (
    <div className="tables-workspace">
      <div className="action-bar">
        <Button
          variant="outline"
          onClick={() => useProjectStore.getState().updateProject(demoProject(project))}
        >
          Load complete example
        </Button>
        <span className="editor-help">
          Example replaces this project's system tables; Undo restores the previous system.
        </span>
      </div>
      <Tabs.Root
        value={tab}
        onValueChange={(v) => {
          setTab(v as TableKey);
          setSelected([]);
          setPaste('');
          setError('');
          setLinkEditor(null);
        }}
      >
        <Tabs.List className="library-tabs" aria-label="System tables">
          {Object.entries(names).map(([key, label]) => (
            <Tabs.Trigger key={key} value={key}>
              {label}
              <span className="tab-count">{project[key as TableKey].length}</span>
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {tab === 'controlLinks' && (
          <p className="editor-help">
            For a DMX daisy chain, connect the controller to device 1, then select device 1’s DMX
            THRU as the source for device 2, and continue along the chain. Enter each cable’s
            length. An incoming Control Link replaces Equipment’s “Control from” connection for the
            same protocol. For downlights, use a 0–10 V link from the dimmer or converter’s output
            to the fixture’s DIM IN. Each control cable has its own length and environment.
          </p>
        )}
      </Tabs.Root>
      <section className="panel library-panel">
        <div className="library-panel-top">
          <div>
            <h2>{names[tab]}</h2>
            <p>
              Double-click or press Enter to edit. Catalog and feed cells offer searchable
              compatible choices.
            </p>
          </div>
          <span className="data-badge">{rows.length} rows</span>
        </div>
        <div className="action-bar">
          <Button
            onClick={() => {
              if (tab === 'controlLinks') {
                setLinkEditor('DMX512');
                return;
              }
              try {
                apply([...rows, blank(tab)]);
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Add row
          </Button>
          {tab === 'controlLinks' && (
            <>
              <Button variant="outline" onClick={() => setLinkEditor('0-10V')}>
                Add 0–10 V link
              </Button>
              <Button
                variant="outline"
                disabled={selected.length !== 1}
                onClick={() => {
                  const link = selected[0];
                  if (link && 'protocol' in link) setLinkEditor(link);
                }}
              >
                Edit control link
              </Button>
            </>
          )}
          <Button
            variant="outline"
            disabled={!selected.length}
            onClick={() => {
              const taken = new Set(rows.flatMap((r) => ('tag' in r ? [r.tag] : [])));
              const copies = selected.map((row) => {
                const copy = structuredClone(row);
                copy.id = crypto.randomUUID();
                if ('tag' in copy) {
                  const prefix = copy.tag.replace(/\d+$/, '');
                  let n = Number(copy.tag.match(/\d+$/)?.[0] ?? 0) + 1;
                  while (taken.has(`${prefix}${n}`)) n++;
                  copy.tag = `${prefix}${n}`;
                  taken.add(copy.tag);
                  if ('circuit' in copy) copy.circuit = String(n);
                }
                return copy;
              });
              apply([...rows, ...copies]);
            }}
          >
            Duplicate rows
          </Button>
          <Button
            variant="outline"
            disabled={!selected.length}
            onClick={() => {
              apply(rows.filter((r) => !selected.some((s) => s.id === r.id)));
              setSelected([]);
            }}
          >
            Delete rows
          </Button>
          <Button variant="outline" onClick={() => setShowPaste(!showPaste)}>
            Paste from Excel
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              downloadFile(
                `${tab}.tsv`,
                Papa.unparse(
                  {
                    fields: fields[tab],
                    data: rows.map((r) =>
                      fields[tab].map((f) =>
                        f.endsWith('Ft') &&
                        project.settings.units === 'm' &&
                        typeof read(r, f) === 'number'
                          ? Number(read(r, f)) * 0.3048
                          : read(r, f),
                      ),
                    ),
                  },
                  { delimiter: '\t', escapeFormulae: true },
                ),
                'text/tab-separated-values',
              )
            }
          >
            Export table
          </Button>
        </div>
        {error && (
          <pre className="inline-error" role="alert">
            {error}
          </pre>
        )}
        {tab === 'controlLinks' && linkEditor && (
          <ControlLinkForm
            key={typeof linkEditor === 'string' ? linkEditor : linkEditor.id}
            project={project}
            products={library.products}
            initial={linkEditor}
            onCancel={() => setLinkEditor(null)}
            onSave={(link) => {
              const next = project.controlLinks.some((l) => l.id === link.id)
                ? project.controlLinks.map((l) => (l.id === link.id ? link : l))
                : [...project.controlLinks, link];
              if (apply(next)) setLinkEditor(null);
            }}
          />
        )}
        <DataGrid<Row>
          key={tab}
          rows={rows}
          columns={columns}
          onSelect={setSelected}
          onEdit={(e) => {
            try {
              if (!e.data) return;
              const changed = change(e.data, e.column.getColId(), e.newValue);
              apply(rows.map((r) => (r.id === changed.id ? changed : r)));
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Invalid value');
            }
          }}
          onReady={(api) => {
            const id = new URLSearchParams(window.location.hash.split('?')[1]).get('row');
            if (id) {
              const node = api.getRowNode(id);
              if (node) {
                node.setSelected(true);
                api.ensureNodeVisible(node);
              }
            }
          }}
        />
        <div className="action-bar">
          <label>
            Bulk field
            <select value={bulkField} onChange={(e) => setBulkField(e.target.value)}>
              {fields[tab].map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </label>
          <input
            aria-label="Bulk value"
            placeholder="Value for selected rows"
            value={bulkValue}
            onChange={(e) => setBulkValue(e.target.value)}
          />
          <Button
            variant="outline"
            disabled={!selected.length}
            onClick={() => {
              try {
                apply(
                  rows.map((r) =>
                    selected.some((s) => s.id === r.id) ? change(r, bulkField, bulkValue) : r,
                  ),
                );
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Apply to selected
          </Button>
          <Button
            variant="outline"
            disabled={selected.length < 2}
            onClick={() => {
              try {
                const first = rows.find((r) => selected.some((s) => s.id === r.id))!;
                apply(
                  rows.map((r) =>
                    selected.some((s) => s.id === r.id)
                      ? change(
                          r,
                          bulkField,
                          bulkField.endsWith('Ft') && project.settings.units === 'm'
                            ? Number(read(first, bulkField)) * 0.3048
                            : read(first, bulkField),
                        )
                      : r,
                  ),
                );
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Fill down selected
          </Button>
        </div>
        {showPaste && (
          <section className="editor-section">
            <h3>Excel / TSV paste</h3>
            <p className="editor-help">
              Include column headers, or use this order: {fields[tab].join(', ')}. Port references
              use TAG::PORT. Length values use {project.settings.units}. All rows are validated
              before adding.
            </p>
            <textarea
              className="json-editor"
              aria-label="Excel paste buffer"
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
            />
            <p>
              {pastePreview.rows.length} valid rows · {pastePreview.errors.length} invalid rows
            </p>
            {pastePreview.errors.map((e) => (
              <pre key={e} role="alert" className="inline-error">
                {e}
              </pre>
            ))}
            <Button
              disabled={!pastePreview.rows.length || pastePreview.errors.length > 0}
              onClick={() => {
                if (apply([...rows, ...pastePreview.rows])) {
                  setPaste('');
                  setShowPaste(false);
                }
              }}
            >
              Add pasted rows
            </Button>
          </section>
        )}
      </section>
      <section className="panel library-panel compact-preview">
        <Button variant="ghost" onClick={() => setMini(!mini)}>
          {mini ? 'Hide' : 'Show'} live diagram preview
        </Button>
        {mini && (
          <Suspense fallback={<p>Loading preview…</p>}>
            <MiniDrawing />
          </Suspense>
        )}
      </section>
    </div>
  );
}
