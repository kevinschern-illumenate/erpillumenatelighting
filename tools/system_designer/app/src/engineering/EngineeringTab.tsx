import { useMemo, useState } from 'react';
import { useStore } from 'zustand';
import { AgGridReact } from 'ag-grid-react';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type CellEditRequestEvent,
  type ColDef,
} from 'ag-grid-community';
import { EnvironmentSchema, ProtocolSchema } from '@ill/core-schemas/common';
import { controlPortOptions, powerPortOptions } from '@ill/engine/ports';
import type { CatalogState } from '../design/catalog';
import type { CheckState } from '../design/engine';
import type { DesignStore } from '../design/store';
import {
  addRow,
  editCell,
  editSetting,
  GRID_FIELDS,
  GRIDS,
  gridRows,
  readCell,
  readSetting,
  removeRows,
  SETTING_FIELDS,
  type GridKey,
  type GridRow,
} from './grids';
import { PickerEditor } from './PickerEditor';

ModuleRegistry.registerModules([AllCommunityModule]);

const THEME = themeQuartz.withParams({
  fontFamily: 'Poppins, Arimo, Arial, sans-serif',
  fontSize: 13,
  headerFontSize: 11,
  rowHeight: 34,
  headerHeight: 34,
  accentColor: '#00588c',
});

const SELECTS: Record<string, readonly string[]> = {
  env: EnvironmentSchema.options,
  protocol: ProtocolSchema.options,
  phase: ['1PH', '3PH'],
  switching: ['', 'none', 'relay', 'phase-forward', 'phase-reverse', '0-10V', 'lutron-module'],
  terminatorPresent: ['true', 'false'],
  voltage: ['120', '208', '240', '277', '347', '480'],
  poles: ['1', '2', '3'],
};
const heading = (field: string) =>
  field
    .replace(/Ft$/, ' (ft)')
    .replace(/Id$/, '')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (c) => c.toUpperCase());

type Tab = GridKey | 'settings';

/**
 * Engineering mode tables (plan §7, WP-3.8): circuits, equipment, loads and control links in the
 * riser's grids, and every project setting. Edits go through the design store, so undo, drafts and
 * the checks work as on the guided steps.
 */
export default function EngineeringTab({
  store,
  engine,
  catalog,
  readOnly,
  staff,
}: {
  store: DesignStore;
  engine: CheckState;
  catalog: CatalogState;
  readOnly: boolean;
  staff: boolean;
}) {
  const design = useStore(store, (s) => s.design);
  const [tab, setTab] = useState<Tab>('sources');
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState('');
  const products = useMemo(() => (catalog.state === 'ready' ? catalog.catalog.items : []), [catalog]);
  const check = engine.state === 'ready' ? engine.check : null;
  const grid = GRIDS.find((item) => item.key === tab);
  const editable = Boolean(grid?.editable) && !readOnly;

  function run(action: () => void) {
    try {
      action();
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That change could not be made');
    }
  }

  const columns = useMemo<ColDef<GridRow>[]>(() => {
    if (tab === 'settings') return [];
    const messages = check?.result.messages ?? [];
    const project = check?.project;
    const library = check?.library.products ?? products;
    const cabinets = design?.site.cabinets ?? [];
    return [
      {
        colId: 'qa',
        headerName: 'QA',
        width: 64,
        pinned: 'left',
        editable: false,
        valueGetter: (p) =>
          messages.some((m) => m.entityRef === p.data?.id && m.severity === 'error')
            ? '✖'
            : messages.some((m) => m.entityRef === p.data?.id && m.severity === 'warning')
              ? '▲'
              : '✓',
        tooltipValueGetter: (p) =>
          messages
            .filter((m) => m.entityRef === p.data?.id)
            .map((m) => m.text)
            .join('\n') || 'No issues',
      },
      ...GRID_FIELDS[tab].map((field): ColDef<GridRow> => {
        const col: ColDef<GridRow> = {
          colId: field,
          headerName: heading(field),
          editable,
          minWidth: ['notes', 'catalogId', 'fedFrom', 'controlFrom', 'from', 'to'].includes(field) ? 180 : 110,
          valueGetter: (p) => (p.data ? readCell(p.data, field) : ''),
          cellDataType: false,
        };
        if (field === 'catalogId') {
          col.valueFormatter = (p) => library.find((item) => item.id === p.value)?.sku ?? String(p.value ?? '');
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = {
            options: products
              .filter((item) => !['tape', 'fixture', 'incomplete'].includes(item.specs.kind))
              .map((item) => ({ value: item.id, label: `${item.sku} · ${item.model}` })),
          };
        } else if (field === 'enclosure') {
          col.valueFormatter = (p) => cabinets.find((item) => item.id === p.value)?.tag ?? String(p.value ?? '');
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = {
            options: [
              { value: '', label: 'No cabinet' },
              ...cabinets.map((item) => ({ value: item.id, label: `${item.tag} · ${item.name}` })),
            ],
          };
        } else if (field === 'fedFrom' && project) {
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = (p: { data: GridRow }) => ({
            options: [{ value: 'unassigned', label: 'Not fed yet' }, ...powerPortOptions(project, library, p.data.id)],
          });
        } else if (['controlFrom', 'from', 'to'].includes(field) && project) {
          col.cellEditor = PickerEditor;
          col.cellEditorPopup = true;
          col.cellEditorParams = (p: { data: GridRow }) => ({
            options: controlPortOptions(
              project,
              library,
              field === 'to' ? 'in' : 'out',
              'protocol' in p.data ? p.data.protocol : undefined,
              field === 'controlFrom' ? p.data.id : undefined,
            ),
          });
        } else if (SELECTS[field]) {
          col.cellEditor = 'agSelectCellEditor';
          col.cellEditorParams = { values: SELECTS[field] };
        }
        return col;
      }),
    ];
  }, [tab, check, products, design, editable]);

  if (!design) return null;
  const rows = tab === 'settings' ? [] : gridRows(design, tab);

  function onEdit(event: CellEditRequestEvent<GridRow>) {
    if (tab === 'settings' || !event.data) return;
    const field = event.colDef.colId!;
    run(() => store.getState().edit((draft) => editCell(draft, tab, event.data!.id, field, event.newValue, products)));
  }

  return (
    <section aria-labelledby="ill-sd-step-title" className="ill-sd__engineering">
      <h2 id="ill-sd-step-title">Grids</h2>
      <p className="ill-sd__muted">
        The design as the riser sees it. Loads come from the runs; change them on the Runs step.
        {staff ? '' : ' Settings that can make a design less conservative are set by ilLumenate.'}
      </p>
      <div className="ill-sd__toggle" role="tablist" aria-label="Tables">
        {[
          ...GRIDS.map((item) => ({ key: item.key as Tab, label: item.label })),
          { key: 'settings' as Tab, label: 'Settings' },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => {
              setTab(item.key);
              setSelected([]);
              setError('');
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}
      {tab === 'settings' ? (
        <div className="ill-sd__card ill-sd__settings" data-testid="project-settings">
          {SETTING_FIELDS.map((field) => {
            const value = readSetting(design.project.settings, field.key);
            const disabled = readOnly || (field.staffOnly && !staff);
            const change = (raw: unknown) =>
              run(() => store.getState().edit((draft) => editSetting(draft, field.key, raw, staff)));
            return (
              <label key={field.key} className="ill-sd__pick">
                <span>{field.label}</span>
                {field.kind === 'boolean' ? (
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    disabled={disabled}
                    onChange={(event) => change(event.target.checked)}
                  />
                ) : field.options ? (
                  <select value={String(value)} disabled={disabled} onChange={(event) => change(event.target.value)}>
                    {field.options.map((option) => (
                      <option key={option} value={String(option)}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    defaultValue={String(value)}
                    key={String(value)}
                    disabled={disabled}
                    onBlur={(event) => event.target.value !== String(value) && change(event.target.value)}
                  />
                )}
              </label>
            );
          })}
        </div>
      ) : (
        <>
          {editable ? (
            <div className="ill-sd__row">
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                onClick={() => run(() => store.getState().edit((draft) => void addRow(draft, tab, products)))}
              >
                Add{' '}
                {grid!.label === 'Circuits' ? 'circuit' : grid!.label === 'Equipment' ? 'equipment' : 'control link'}
              </button>
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                disabled={!selected.length}
                onClick={() =>
                  run(() => {
                    store.getState().edit((draft) => removeRows(draft, tab, selected));
                    setSelected([]);
                  })
                }
              >
                Remove selected
              </button>
            </div>
          ) : null}
          <div className="ill-sd__grid" style={{ height: 420 }} data-testid={`grid-${tab}`}>
            <AgGridReact<GridRow>
              theme={THEME}
              rowData={rows}
              columnDefs={columns}
              defaultColDef={{ sortable: true, filter: true, resizable: true, minWidth: 90, flex: 1 }}
              getRowId={(p) => p.data.id}
              readOnlyEdit
              onCellEditRequest={onEdit}
              rowSelection={editable ? { mode: 'multiRow' } : undefined}
              onSelectionChanged={(event) => setSelected(event.api.getSelectedRows().map((row) => row.id))}
              tooltipShowDelay={200}
              stopEditingWhenCellsLoseFocus
            />
          </div>
        </>
      )}
    </section>
  );
}
