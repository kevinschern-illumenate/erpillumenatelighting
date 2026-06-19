/**
 * Side-by-side comparison of the top ilLumenate recommendation against the
 * competitor sample stub. Illustrative only -- competitor values are sample data.
 *
 * @param {object} props
 * @param {object} props.primary      Top ilLumenate recommendation (or null).
 * @param {Array}  props.competitors  Competitor recommendation rows.
 */
const ROWS = [
  { key: 'brand', label: 'Brand' },
  { key: 'series', label: 'Series', from: 'family' },
  { key: 'lumens_per_foot', label: 'Lumens / ft', unit: ' lm/ft' },
  { key: 'cri_typical', label: 'CRI (typical)' },
  { key: 'watts_per_foot', label: 'Watts / ft', unit: ' W/ft' },
  { key: 'input_voltage', label: 'Input voltage' },
  { key: 'environment_rating', label: 'Environment' },
  { key: 'ip_rating', label: 'IP rating' },
  { key: 'voltage_drop_max_run_length_ft', label: 'Max single-feed run', unit: ' ft' },
  { key: 'supported_dimming_protocols', label: 'Dimming protocols', join: true },
];

function cellValue(row, rec) {
  if (!rec) return '\u2014';
  if (row.from === 'family') return rec.family || '\u2014';
  if (row.key === 'brand') return rec.brand || '\u2014';
  const v = rec.attributes ? rec.attributes[row.key] : undefined;
  if (v === undefined || v === null || v === '') return '\u2014';
  if (row.join && Array.isArray(v)) return v.join(', ');
  return `${v}${row.unit || ''}`;
}

export default function CompareTable({ primary, competitors }) {
  const columns = [primary, ...competitors].filter(Boolean);
  if (columns.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-xl border border-ill-border bg-ill-paper">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ill-border bg-ill-bg text-left">
            <th className="px-4 py-3 font-semibold text-ill-muted">Specification</th>
            {columns.map((rec, i) => (
              <th key={rec.sku} className="px-4 py-3 font-semibold text-ill-ink">
                <span className="block">{rec.sku}</span>
                {i === 0 && (
                  <span className="mt-0.5 inline-block rounded bg-ill-accentSoft px-2 py-0.5 text-[11px] font-medium text-ill-accent">
                    ilLumenate pick
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label} className="border-b border-ill-border last:border-0">
              <th scope="row" className="px-4 py-2.5 text-left font-medium text-ill-muted">
                {row.label}
              </th>
              {columns.map((rec) => (
                <td key={rec.sku + row.label} className="px-4 py-2.5 text-ill-ink">
                  {cellValue(row, rec)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-4 py-2 text-xs text-ill-subtle">
        Competitor columns use illustrative sample data for prototype comparison only.
      </p>
    </div>
  );
}
