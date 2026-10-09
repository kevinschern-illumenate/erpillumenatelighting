import { useState } from 'react';
import { useStore } from 'zustand';
import type { BomItem } from '@ill/engine/model';
import type { DesignApi, WritebackPreview } from '../design/api';
import type { CheckState } from '../design/engine';
import type { DesignStore } from '../design/store';
import type { OpenDesign } from './open';

/** Engine wire footage (waste included) by catalog wire id: what the server turns into wire lines (D7). */
export function wireFeet(bom: readonly BomItem[]): Record<string, number> {
  const feet: Record<string, number> = {};
  for (const row of bom) if (row.key.startsWith('wire:') && row.quantity > 0) feet[row.sku] = row.quantity;
  return feet;
}

/** Every change in a preview as one row: what it does, to which Item, how many and where. */
export function changeRows(preview: WritebackPreview) {
  return [
    ...preview.add.map((row) => ({
      key: row.key,
      action: 'Add',
      item: row.item_name ?? row.item_code,
      qty: `${row.qty}${row.unit === 'spool' ? ' spools' : row.unit === 'ft' ? ' ft' : ''}`,
      location: row.location ?? '',
    })),
    ...preview.update.map((row) => ({
      key: row.key,
      action: 'Change',
      item: row.item_name ?? row.item_code,
      qty: `${row.from_qty} → ${row.qty}`,
      location: row.location ?? '',
    })),
    ...preview.remove.map((row) => ({
      key: row.key,
      action: 'Remove',
      item: row.item_name ?? row.item_code,
      qty: String(row.qty),
      location: row.line_id ?? '',
    })),
    ...preview.replaces_configurator_lines.map((group) => ({
      key: group.key,
      action: 'Replace',
      item: group.lines.map((line) => line.item_name ?? line.item_code).join(', '),
      qty: group.lines.map((line) => line.qty).join(', '),
      location: group.line_id ? `Supplies of line ${group.line_id}` : 'Configurator supplies',
    })),
  ];
}

const money = (amount: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', signDisplay: 'exceptZero' }).format(amount);

/** The Finish step (WP-4.1): add the design's supplies, controls and wire to the schedule. */
export function FinishStep({
  open,
  store,
  engine,
  api,
}: {
  open: OpenDesign;
  store: DesignStore;
  engine: CheckState;
  api: DesignApi;
}) {
  const design = useStore(store, (s) => s.design);
  const meta = useStore(store, (s) => s.meta);
  const dirty = useStore(store, (s) => s.dirty);
  const [preview, setPreview] = useState<{ result: WritebackPreview; feet: Record<string, number> } | null>(null);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  if (!design) return null;
  const ready = engine.state === 'ready' && engine.design === design;
  const canWrite = open.permissions.can_edit && !open.schedule.is_locked;
  const blocker = !meta
    ? 'Save the design first.'
    : dirty
      ? 'Save your changes first.'
      : !ready
        ? engine.state === 'error'
          ? engine.message
          : 'Running the checks…'
        : null;

  async function load() {
    if (!meta || engine.state !== 'ready') return;
    setBusy('Comparing the design with the schedule…');
    setError('');
    setNotice('');
    try {
      const feet = wireFeet(engine.check.result.bom);
      setPreview({ result: await api.writebackPreview(meta.name, feet), feet });
      setSkipped(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The changes could not be listed');
    } finally {
      setBusy('');
    }
  }

  async function applyChanges() {
    if (!meta || !preview) return;
    const keys = changeRows(preview.result)
      .map((row) => row.key)
      .filter((key) => !skipped.has(key));
    setBusy('Updating the schedule…');
    setError('');
    try {
      const result = await api.writebackApply(meta.name, keys, preview.feet);
      const parts = [
        result.added && `${result.added} added`,
        result.updated && `${result.updated} changed`,
        result.removed && `${result.removed} removed`,
        result.replaced && `${result.replaced} configurator supply group${result.replaced === 1 ? '' : 's'} replaced`,
      ].filter(Boolean);
      setNotice(`The schedule is updated: ${parts.join(', ') || 'nothing to change'}.`);
      setPreview({ result: await api.writebackPreview(meta.name, preview.feet), feet: preview.feet });
      setSkipped(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The schedule could not be updated');
    } finally {
      setBusy('');
    }
  }

  const rows = preview ? changeRows(preview.result) : [];
  const chosen = rows.filter((row) => !skipped.has(row.key)).length;
  const delta = preview?.result.price_delta;

  return (
    <section aria-labelledby="ill-sd-step-title">
      <h2 id="ill-sd-step-title">Finish</h2>
      <div className="ill-sd__card" data-testid="writeback">
        <h3>Add to the schedule</h3>
        <p className="ill-sd__muted">
          The supplies, controls and wire in this design become lines on the schedule, so they are quoted and ordered
          with the fixtures. Lines you added yourself are never changed.
        </p>
        {blocker ? (
          <p className="ill-sd__muted" role="status">
            {blocker}
          </p>
        ) : (
          <div className="ill-sd__row">
            <button
              type="button"
              className="ill-sd__button ill-sd__button--quiet"
              disabled={Boolean(busy)}
              onClick={() => void load()}
            >
              {preview ? 'Compare again' : 'Show the changes'}
            </button>
          </div>
        )}
        {preview ? (
          rows.length ? (
            <>
              <div className="ill-sd__table-wrap">
                <table className="ill-sd__table" data-testid="writeback-changes">
                  <thead>
                    <tr>
                      <th scope="col">Include</th>
                      <th scope="col">Change</th>
                      <th scope="col">Item</th>
                      <th scope="col">Qty</th>
                      <th scope="col">Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.key}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Include ${row.action.toLowerCase()} ${row.item}`}
                            checked={!skipped.has(row.key)}
                            disabled={!canWrite}
                            onChange={(event) =>
                              setSkipped((current) => {
                                const next = new Set(current);
                                if (event.target.checked) next.delete(row.key);
                                else next.add(row.key);
                                return next;
                              })
                            }
                          />
                        </td>
                        <td>{row.action}</td>
                        <td>{row.item}</td>
                        <td>{row.qty}</td>
                        <td>{row.location}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {delta ? (
                <p data-testid="price-delta">
                  Price change: <strong>{money(delta.amount)}</strong> at {delta.price_list} prices
                  {delta.unpriced.length ? ` (no price yet for ${delta.unpriced.join(', ')})` : ''}.
                </p>
              ) : null}
              {preview.result.error_count ? (
                <p className="ill-sd__callout ill-sd__callout--warn">
                  This revision still has {preview.result.error_count} error
                  {preview.result.error_count === 1 ? '' : 's'}. You can add it to the schedule, but fix them before you
                  request a review.
                </p>
              ) : null}
              {canWrite && preview.result.can_apply ? (
                <button
                  type="button"
                  className="ill-sd__button"
                  disabled={!chosen || Boolean(busy)}
                  onClick={() => void applyChanges()}
                >
                  Add {chosen} change{chosen === 1 ? '' : 's'} to the schedule
                </button>
              ) : (
                <p className="ill-sd__muted">
                  {canWrite
                    ? 'The schedule is not in Draft or Ready, so its lines cannot change.'
                    : 'Only people who can edit the schedule can add these lines.'}
                </p>
              )}
            </>
          ) : (
            <p className="ill-sd__muted" data-testid="writeback-in-sync">
              The schedule already has every line this design needs.
            </p>
          )
        ) : null}
        {preview?.result.blocked.length ? (
          <ul className="ill-sd__muted" data-testid="writeback-blocked">
            {preview.result.blocked.map((item) => (
              <li key={item.ref}>{item.reason}</li>
            ))}
          </ul>
        ) : null}
        {busy ? (
          <p className="ill-sd__muted" role="status">
            {busy}
          </p>
        ) : null}
        {error ? (
          <p className="ill-sd__error" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="ill-sd__muted" role="status" data-testid="writeback-notice">
            {notice}
          </p>
        ) : null}
      </div>
    </section>
  );
}
