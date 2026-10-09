import { useState } from 'react';
import type { CustomCellEditorProps } from 'ag-grid-react';

export function PickerEditor({
  value,
  onValueChange,
  stopEditing,
  options = [],
}: CustomCellEditorProps & { options: { value: string; label: string }[] }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const filtered = options
    .filter((o) => `${o.label} ${o.value}`.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 60);
  function choose(next: string) {
    onValueChange(next);
    stopEditing();
  }
  return (
    <div className="ill-sd__picker">
      <input
        autoFocus
        aria-label="Search choices"
        placeholder={options.find((o) => o.value === value)?.label ?? 'Search…'}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive(Math.min(active + 1, filtered.length - 1));
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive(Math.max(0, active - 1));
          }
          if (e.key === 'Enter' && filtered[active]) {
            e.preventDefault();
            choose(filtered[active]!.value);
          }
        }}
      />
      <div role="listbox">
        {filtered.map((o, i) => (
          <button
            type="button"
            key={o.value}
            role="option"
            aria-selected={i === active}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => choose(o.value)}
          >
            {o.label}
          </button>
        ))}
        {!filtered.length && <p>No compatible choices.</p>}
      </div>
    </div>
  );
}
