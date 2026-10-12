import { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type GridApi,
  type CellEditRequestEvent,
} from 'ag-grid-community';
ModuleRegistry.registerModules([AllCommunityModule]);

export function DataGrid<T extends { id: string }>({
  rows,
  columns,
  onEdit,
  onSelect,
  onReady,
  height = 470,
}: {
  rows: T[];
  columns: ColDef<T>[];
  onEdit?: (event: CellEditRequestEvent<T>) => void;
  onSelect?: (rows: T[]) => void;
  onReady?: (api: GridApi<T>) => void;
  height?: number;
}) {
  const theme = useMemo(
    () =>
      themeQuartz.withParams({
        fontFamily: 'Manrope, Arimo, Arial, sans-serif',
        fontSize: 13,
        headerFontSize: 11,
        rowHeight: 37,
        headerHeight: 36,
        accentColor: '#00588c',
        browserColorScheme: 'inherit',
        backgroundColor: 'var(--surface)',
        foregroundColor: 'var(--foreground)',
        borderColor: 'var(--border)',
        headerBackgroundColor: 'var(--accent)',
      }),
    [],
  );
  return (
    <div className="engineering-grid" style={{ height }}>
      <AgGridReact<T>
        theme={theme}
        rowData={rows}
        columnDefs={columns}
        defaultColDef={{ sortable: true, filter: true, resizable: true, minWidth: 100, flex: 1 }}
        getRowId={(p) => p.data.id}
        readOnlyEdit
        onCellEditRequest={onEdit}
        rowSelection={{ mode: 'multiRow' }}
        onSelectionChanged={(e) => onSelect?.(e.api.getSelectedRows())}
        onGridReady={(e) => onReady?.(e.api)}
        tooltipShowDelay={200}
        stopEditingWhenCellsLoseFocus
      />
    </div>
  );
}
