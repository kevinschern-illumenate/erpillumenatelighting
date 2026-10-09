import { useEffect, useMemo, useState, type DragEvent } from 'react';
import { useStore } from 'zustand';
import type { Cabinet, Design, Run, Zone } from '@ill/core-schemas/design';
import type { Equipment } from '@ill/core-schemas/project';
import {
  addSupply,
  addZone,
  assignmentProblem,
  assignRuns,
  capacity,
  fitSorted,
  FROM_CONFIGURATOR,
  moveSupply,
  outputLoads,
  placeConfiguratorSupplies,
  powerSpecs,
  removeSupply,
  removeZone,
  reviewHints,
  setRunZone,
  setSupplyCircuit,
  unassignRuns,
  updateZone,
  ZONE_METHODS,
  type PowerContext,
  type SupplyChoice,
} from '@ill/engine/power';
import { runRows, type RunRow } from '@ill/engine/runs';
import { addCabinet, distanceDefaults } from '@ill/engine/site';
import { DesignApiError, type DesignApi } from '../design/api';
import { loadCatalog, type DesignCatalog } from '../design/catalog';
import type { DesignStore } from '../design/store';
import { CommitInput } from './fields';
import type { OpenDesign } from './open';

const DRAG_TYPE = 'application/x-ill-runs';
const watts = (value: number) => `${Number(value.toFixed(1))} W`;
const total = (runs: readonly Run[]) => runs.reduce((sum, run) => sum + run.watts, 0);

type CatalogState =
  { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; catalog: DesignCatalog };

/**
 * The power board (plan §10.1–10.2, §10.5): unassigned runs on the left, cabinets with their supplies and
 * outputs on the right. Drag runs onto an output, or select them and use "Assign here" from the keyboard.
 * A refused assignment says why. Supplies are picked by fit from the eligible list; no prices (D6).
 */
export function PowerStep({
  open,
  store,
  api,
  readOnly,
}: {
  open: OpenDesign;
  store: DesignStore;
  api: DesignApi;
  readOnly: boolean;
}) {
  const design = useStore(store, (s) => s.design);
  const [catalog, setCatalog] = useState<CatalogState>({ state: 'loading' });
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState('');
  const [picking, setPicking] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadCatalog(api, open.catalog_hash).then(
      (value) => !cancelled && setCatalog({ state: 'ready', catalog: value }),
      (problem: unknown) =>
        !cancelled &&
        setCatalog({
          state: 'error',
          message: problem instanceof DesignApiError ? problem.message : 'The ilLumenate catalog could not be loaded.',
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [api, open.catalog_hash]);

  const context = useMemo<PowerContext | null>(
    () =>
      catalog.state === 'ready' ? { catalog: catalog.catalog.byId, lines: open.lines, builds: open.builds } : null,
    [catalog, open.lines, open.builds],
  );
  if (!design) return null;

  const change = (recipe: (draft: Design) => void) => {
    try {
      store.getState().edit((draft) => recipe(draft as Design));
      setError('');
      return true;
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
      return false;
    }
  };
  const keys = [...selected].filter((key) => design.runs.some((run) => run.key === key));
  const selectedRuns = design.runs.filter((run) => selected.has(run.key));
  const assign = (runKeys: string[], equipmentId: string, port: string) => {
    if (!context || !runKeys.length) return;
    if (change((draft) => assignRuns(draft, context, runKeys, equipmentId, port))) setSelected(new Set());
  };
  const toggle = (row: RunRow, on: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      for (const run of row.runs) {
        if (on) next.add(run.key);
        else next.delete(run.key);
      }
      return next;
    });
  const dragStart = (row: RunRow) => (event: DragEvent) => {
    const rowKeys = row.runs.map((run) => run.key);
    const dragged = rowKeys.every((key) => selected.has(key)) ? keys : rowKeys;
    event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragged));
    event.dataTransfer.setData('text/plain', dragged.join(' '));
    event.dataTransfer.effectAllowed = 'move';
  };
  const dropKeys = (event: DragEvent): string[] => {
    try {
      const value: unknown = JSON.parse(event.dataTransfer.getData(DRAG_TYPE) || '[]');
      return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
    } catch {
      return [];
    }
  };

  const unassigned = design.runs.filter((run) => !run.assignment);
  const hints = reviewHints(design);
  const zones = new Map(design.zones.map((zone) => [zone.id, zone]));
  const defaults = distanceDefaults(open.settings);
  const hasAllocations = Object.values(open.builds).some((byName) =>
    Object.values(byName).some((build) => build.allocations.length),
  );

  return (
    <section aria-labelledby="ill-sd-power-title" className="ill-sd__power">
      <h2 id="ill-sd-power-title">Power</h2>
      <p className="ill-sd__muted">
        Put each run on a supply output. Drag a run onto an output, or select runs and choose “Assign here”. Supplies
        are listed by fit for the runs you selected; loads are checked against each supply’s usable rating.
      </p>
      {hints.length ? (
        <p className="ill-sd__banner" role="note" data-testid="review-hints">
          ilLumenate reviews this design before ordering: {hints.join(', ')}.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="ill-sd__error">
          {error}
        </p>
      ) : null}
      {catalog.state === 'loading' ? <p role="status">Loading the ilLumenate catalog…</p> : null}
      {catalog.state === 'error' ? (
        <p role="alert" className="ill-sd__error">
          {catalog.message}
        </p>
      ) : null}
      {context ? (
        <fieldset disabled={readOnly} className="ill-sd__fieldset">
          <div className="ill-sd__row">
            <span data-testid="assigned-count">
              {design.runs.length - unassigned.length} of {design.runs.length} runs assigned
            </span>
            {hasAllocations && !design.project.equipment.length ? (
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                onClick={() =>
                  change(
                    (draft) =>
                      void placeConfiguratorSupplies(draft, context, (spaceId) => addCabinet(draft, spaceId, defaults)),
                  )
                }
              >
                Start from configurator supplies
              </button>
            ) : null}
          </div>

          {keys.length ? (
            <div className="ill-sd__bulk" role="group" aria-label="Selected runs">
              <strong>
                {keys.length} {keys.length === 1 ? 'run' : 'runs'} selected · {watts(total(selectedRuns))}
              </strong>
              <select
                aria-label="Selected zone"
                value=""
                onChange={(event) =>
                  event.target.value &&
                  change((draft) =>
                    setRunZone(draft, context, keys, event.target.value === '-' ? undefined : event.target.value),
                  )
                }
              >
                <option value="">Put in zone…</option>
                <option value="-">No zone</option>
                {design.zones.map((zone) => (
                  <option key={zone.id} value={zone.id}>
                    {zone.name}
                  </option>
                ))}
              </select>
              {selectedRuns.some((run) => run.assignment) ? (
                <button
                  type="button"
                  className="ill-sd__button ill-sd__button--quiet"
                  onClick={() => change((draft) => unassignRuns(draft, keys)) && setSelected(new Set())}
                >
                  Unassign
                </button>
              ) : null}
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                onClick={() => setSelected(new Set())}
              >
                Clear selection
              </button>
            </div>
          ) : null}

          <div className="ill-sd__board">
            <div className="ill-sd__pool" aria-label="Unassigned runs" role="region">
              <h3>Unassigned runs</h3>
              {unassigned.length ? null : <p className="ill-sd__muted">Every run is on a supply.</p>}
              {design.site.spaces.map((space) => {
                const rows = runRows(unassigned.filter((run) => run.spaceId === space.id));
                if (!rows.length) return null;
                return (
                  <div key={space.id}>
                    <h4>{space.name}</h4>
                    <ul className="ill-sd__run-pool">
                      {rows.map((row) => (
                        <li
                          key={row.id}
                          draggable={!readOnly}
                          onDragStart={dragStart(row)}
                          data-testid={`pool-${row.id}`}
                        >
                          <label>
                            <input
                              type="checkbox"
                              checked={row.runs.every((run) => selected.has(run.key))}
                              onChange={(event) => toggle(row, event.target.checked)}
                              aria-label={`Select ${row.label}`}
                            />
                            <ZoneDot zone={row.runs[0]!.zoneId ? zones.get(row.runs[0]!.zoneId) : undefined} />
                            <strong>{row.label}</strong>
                          </label>
                          <span className="ill-sd__muted">{watts(total(row.runs))}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>

            <div className="ill-sd__cabinets">
              {design.site.cabinets.length ? null : (
                <p className="ill-sd__muted">Add a cabinet on the Spaces step to hold supplies.</p>
              )}
              {design.site.cabinets.map((cabinet) => (
                <article key={cabinet.id} className="ill-sd__card" data-testid={`board-${cabinet.tag}`}>
                  <h3>
                    {cabinet.tag} · {cabinet.name}{' '}
                    <span className="ill-sd__muted">({cabinet.locationRating} location)</span>
                  </h3>
                  <CabinetLoad design={design} cabinet={cabinet} context={context} />
                  {design.project.equipment
                    .filter((supply) => supply.enclosure === cabinet.id)
                    .map((supply) => (
                      <SupplyCard
                        key={supply.id}
                        design={design}
                        supply={supply}
                        context={context}
                        selectedKeys={keys}
                        zones={zones}
                        onAssign={assign}
                        onDropKeys={dropKeys}
                        onUnassign={(runKeys) => change((draft) => unassignRuns(draft, runKeys))}
                        onRemove={() => change((draft) => removeSupply(draft, supply.id))}
                        onCircuit={(sourceId) => change((draft) => setSupplyCircuit(draft, supply.id, sourceId))}
                        onMove={(cabinetId) => change((draft) => moveSupply(draft, supply.id, cabinetId))}
                      />
                    ))}
                  {picking === cabinet.id ? (
                    <SupplyPicker
                      key={pickerKeys(selectedRuns, unassigned, cabinet)}
                      api={api}
                      schedule={open.schedule.name}
                      cabinet={cabinet}
                      runs={pickerRuns(selectedRuns, unassigned, cabinet)}
                      context={context}
                      deratePct={design.project.settings.psuDeratePct}
                      onPick={(catalogId) =>
                        change((draft) => void addSupply(draft, context, cabinet.id, catalogId)) && setPicking(null)
                      }
                      onClose={() => setPicking(null)}
                    />
                  ) : (
                    <button
                      type="button"
                      className="ill-sd__button ill-sd__button--quiet"
                      onClick={() => setPicking(cabinet.id)}
                    >
                      Add supply
                    </button>
                  )}
                </article>
              ))}
            </div>
          </div>

          <Zones
            zones={design.zones}
            runs={design.runs}
            onAdd={(method) => change((draft) => void addZone(draft, method))}
            onUpdate={(zoneId, changes) => change((draft) => updateZone(draft, zoneId, changes))}
            onRemove={(zoneId) => change((draft) => removeZone(draft, zoneId))}
          />
        </fieldset>
      ) : null}
    </section>
  );
}

function pickerRuns(selectedRuns: Run[], unassigned: Run[], cabinet: Cabinet): Run[] {
  if (selectedRuns.length) return selectedRuns;
  const here = unassigned.filter((run) => run.spaceId === cabinet.spaceId);
  return here.length ? here : unassigned;
}
const pickerKeys = (selectedRuns: Run[], unassigned: Run[], cabinet: Cabinet) =>
  pickerRuns(selectedRuns, unassigned, cabinet)
    .map((run) => run.key)
    .join(' ');

function ZoneDot({ zone }: { zone: Zone | undefined }) {
  if (!zone) return null;
  return <span className="ill-sd__zone-dot" style={{ background: zone.color }} title={zone.name} aria-hidden="true" />;
}

/** A load bar: share of the usable rating, with the 80% guide line (plan §10.1). */
function LoadBar({ load, usable, label }: { load: number; usable: number; label: string }) {
  const percent = usable > 0 ? (load / usable) * 100 : 0;
  return (
    <span className="ill-sd__load" title={label}>
      <span
        className={`ill-sd__load-bar${percent > 100 ? ' ill-sd__load-bar--over' : ''}`}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={usable}
        aria-valuenow={Number(load.toFixed(1))}
      >
        <span style={{ width: `${Math.min(percent, 100)}%` }} />
        <span className="ill-sd__load-line" style={{ left: '80%' }} />
      </span>
      <span className="ill-sd__load-text">
        {watts(load)} of {watts(usable)}
      </span>
    </span>
  );
}

function CabinetLoad({ design, cabinet, context }: { design: Design; cabinet: Cabinet; context: PowerContext }) {
  const supplies = design.project.equipment.filter((supply) => supply.enclosure === cabinet.id);
  if (!supplies.length) return <p className="ill-sd__muted">No supplies yet.</p>;
  let load = 0;
  let heat = 0;
  for (const supply of supplies) {
    const supplyLoad = [...outputLoads(design, supply.id).values()].reduce((sum, value) => sum + value, 0);
    const specs = powerSpecs(context.catalog.get(supply.catalogId));
    load += supplyLoad;
    if (specs) heat += supplyLoad * (1 / specs.efficiency - 1);
  }
  return (
    <p className="ill-sd__muted" data-testid={`cabinet-load-${cabinet.tag}`}>
      {supplies.length} {supplies.length === 1 ? 'supply' : 'supplies'} · {watts(load)} load · about {watts(heat)} heat
    </p>
  );
}

function SupplyCard({
  design,
  supply,
  context,
  selectedKeys,
  zones,
  onAssign,
  onDropKeys,
  onUnassign,
  onRemove,
  onCircuit,
  onMove,
}: {
  design: Design;
  supply: Equipment;
  context: PowerContext;
  selectedKeys: string[];
  zones: Map<string, Zone>;
  onAssign(runKeys: string[], equipmentId: string, port: string): void;
  onDropKeys(event: DragEvent): string[];
  onUnassign(runKeys: string[]): void;
  onRemove(): void;
  onCircuit(sourceId: string | undefined): void;
  onMove(cabinetId: string): void;
}) {
  const [over, setOver] = useState<string | null>(null);
  const item = context.catalog.get(supply.catalogId);
  const specs = powerSpecs(item);
  const loads = outputLoads(design, supply.id);
  const supplyLoad = [...loads.values()].reduce((sum, value) => sum + value, 0);
  const limits = specs ? capacity(specs, design.project.settings.psuDeratePct) : null;
  const sourceRef = design.project.sources.some((source) => source.id === supply.fedFrom.ref) ? supply.fedFrom.ref : '';
  return (
    <div className="ill-sd__supply" data-testid={`supply-${supply.tag}`}>
      <div className="ill-sd__row">
        <strong>{supply.tag}</strong>
        <span>{item?.model ?? supply.catalogId}</span>
        {specs?.outputV ? <span className="ill-sd__muted">{specs.outputV} V</span> : null}
        {supply.notes === FROM_CONFIGURATOR ? <span className="ill-sd__chip">From configurator</span> : null}
        {limits ? <LoadBar load={supplyLoad} usable={limits.usableW} label={`${supply.tag} load`} /> : null}
      </div>
      {!limits ? (
        <p className="ill-sd__error">This supply has incomplete catalog data; choose another.</p>
      ) : (
        <ul className="ill-sd__outputs">
          {limits.outputs.map((output) => {
            const runs = design.runs.filter(
              (run) => run.assignment?.equipmentId === supply.id && run.assignment.port === output.name,
            );
            const problem = selectedKeys.length
              ? assignmentProblem(design, context, selectedKeys, supply.id, output.name)
              : null;
            return (
              <li
                key={output.name}
                data-testid={`output-${supply.tag}-${output.name}`}
                className={over === output.name ? 'ill-sd__output ill-sd__output--over' : 'ill-sd__output'}
                onDragOver={(event) => {
                  event.preventDefault();
                  setOver(output.name);
                }}
                onDragLeave={() => setOver(null)}
                onDrop={(event) => {
                  event.preventDefault();
                  setOver(null);
                  onAssign(onDropKeys(event), supply.id, output.name);
                }}
              >
                <div className="ill-sd__row">
                  <span>{output.name}</span>
                  {output.class2 ? <span className="ill-sd__chip ill-sd__chip--ok">Class 2</span> : null}
                  <LoadBar
                    load={loads.get(output.name) ?? 0}
                    usable={output.usableW}
                    label={`${supply.tag} ${output.name} load`}
                  />
                  <button
                    type="button"
                    className="ill-sd__pick"
                    disabled={!selectedKeys.length}
                    onClick={() => onAssign(selectedKeys, supply.id, output.name)}
                  >
                    Assign here
                  </button>
                </div>
                {problem ? <p className="ill-sd__muted ill-sd__refusal">{problem}</p> : null}
                {runs.length ? (
                  <ul className="ill-sd__assigned">
                    {runRows(runs).map((row) => (
                      <li key={row.id}>
                        <ZoneDot zone={row.runs[0]!.zoneId ? zones.get(row.runs[0]!.zoneId) : undefined} />
                        {row.label} · {watts(total(row.runs))}
                        <button
                          type="button"
                          className="ill-sd__pick"
                          aria-label={`Unassign ${row.label}`}
                          onClick={() => onUnassign(row.runs.map((run) => run.key))}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <div className="ill-sd__row">
        <select
          aria-label={`${supply.tag} circuit`}
          value={sourceRef}
          onChange={(event) => onCircuit(event.target.value || undefined)}
        >
          <option value="">Not fed yet</option>
          {design.project.sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.panel}/{source.circuit} · {source.voltage} V
            </option>
          ))}
        </select>
        {design.site.cabinets.length > 1 ? (
          <select
            aria-label={`Move ${supply.tag} to`}
            value=""
            onChange={(event) => event.target.value && onMove(event.target.value)}
          >
            <option value="">Move to…</option>
            {design.site.cabinets
              .filter((cabinet) => cabinet.id !== supply.enclosure)
              .map((cabinet) => (
                <option key={cabinet.id} value={cabinet.id}>
                  {cabinet.tag} · {cabinet.name}
                </option>
              ))}
          </select>
        ) : null}
        <button type="button" className="ill-sd__button ill-sd__button--quiet" onClick={onRemove}>
          Remove {supply.tag}
        </button>
      </div>
    </div>
  );
}

function SupplyPicker({
  api,
  schedule,
  cabinet,
  runs,
  context,
  deratePct,
  onPick,
  onClose,
}: {
  api: DesignApi;
  schedule: string;
  cabinet: Cabinet;
  runs: Run[];
  context: PowerContext;
  deratePct: number;
  onPick(catalogId: string): void;
  onClose(): void;
}) {
  const [state, setState] = useState<
    { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; choices: SupplyChoice[] }
  >({ state: 'loading' });
  const runKeys = runs.map((run) => run.key).join(' ');
  const load = total(runs);
  const largest = Math.max(0, ...runs.map((run) => run.watts));

  useEffect(() => {
    if (!runKeys) return;
    let cancelled = false;
    api.eligibleSupplies({ schedule, runKeys: runKeys.split(' '), locationRating: cabinet.locationRating }).then(
      (rows) => {
        if (cancelled) return;
        const candidates = rows.map((row) => ({
          catalogId: row.catalog_id,
          ...(row.rank !== null ? { rank: row.rank } : {}),
        }));
        setState({ state: 'ready', choices: fitSorted(candidates, context, load, largest, deratePct) });
      },
      (problem: unknown) =>
        !cancelled &&
        setState({
          state: 'error',
          message: problem instanceof DesignApiError ? problem.message : 'Eligible supplies could not be loaded.',
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [api, schedule, cabinet.locationRating, runKeys, context, load, largest, deratePct]);
  const shown = runKeys
    ? state
    : ({ state: 'error', message: 'Every run is assigned; select runs to find supplies for them.' } as const);

  return (
    <div className="ill-sd__picker" role="group" aria-label={`Add a supply to ${cabinet.tag}`}>
      <div className="ill-sd__row">
        <strong>Add a supply</strong>
        <span className="ill-sd__muted">
          For {runs.length} {runs.length === 1 ? 'run' : 'runs'} · {watts(load)} · {cabinet.locationRating} location
        </span>
        <button type="button" className="ill-sd__pick" onClick={onClose}>
          Close
        </button>
      </div>
      {shown.state === 'loading' ? <p role="status">Finding eligible supplies…</p> : null}
      {shown.state === 'error' ? <p className="ill-sd__error">{shown.message}</p> : null}
      {shown.state === 'ready' && !shown.choices.length ? (
        <p className="ill-sd__muted">No catalog supply fits these runs here. Contact your ilLumenate representative.</p>
      ) : null}
      {shown.state === 'ready' && shown.choices.length ? (
        <ul className="ill-sd__choices">
          {shown.choices.map((choice) => {
            const item = context.catalog.get(choice.catalogId)!;
            const specs = powerSpecs(item)!;
            return (
              <li key={choice.catalogId} data-testid={`choice-${choice.catalogId}`}>
                <div>
                  <strong>{item.model}</strong>
                  <span className="ill-sd__muted">
                    {' '}
                    {specs.outputV} V · {watts(choice.usableW)} usable · {specs.outputs.length}{' '}
                    {specs.outputs.length === 1 ? 'output' : 'outputs'}
                    {specs.outputs.some((output) => output.class2) ? ' · Class 2' : ''}
                    {specs.dimming.length ? ` · ${specs.dimming.join(', ')}` : ''}
                  </span>
                </div>
                <span className={`ill-sd__chip${choice.fits ? ' ill-sd__chip--ok' : ''}`}>
                  {choice.fits
                    ? 'Carries these runs'
                    : Number.isFinite(choice.count)
                      ? `Needs ${choice.count}`
                      : 'A run is larger than its outputs'}
                </span>
                <button
                  type="button"
                  className="ill-sd__button ill-sd__button--quiet"
                  disabled={!Number.isFinite(choice.count)}
                  onClick={() => onPick(choice.catalogId)}
                >
                  Add {item.model}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function Zones({
  zones,
  runs,
  onAdd,
  onUpdate,
  onRemove,
}: {
  zones: Zone[];
  runs: Run[];
  onAdd(method: Zone['method']): void;
  onUpdate(zoneId: string, changes: Partial<Pick<Zone, 'name' | 'method'>>): void;
  onRemove(zoneId: string): void;
}) {
  return (
    <article className="ill-sd__card" data-testid="zones">
      <h3>Control zones</h3>
      <p className="ill-sd__muted">
        Runs in a zone dim together. Phase-cut and 0-10V zones need supplies that accept that dimming; each output feeds
        one zone.
      </p>
      {zones.map((zone) => (
        <div key={zone.id} className="ill-sd__row" data-testid={`zone-${zone.id}`}>
          <ZoneDot zone={zone} />
          <CommitInput label={`${zone.name} name`} value={zone.name} onCommit={(name) => onUpdate(zone.id, { name })} />
          <select
            aria-label={`${zone.name} method`}
            value={zone.method}
            onChange={(event) => onUpdate(zone.id, { method: event.target.value as Zone['method'] })}
          >
            {ZONE_METHODS.map((method) => (
              <option key={method.id} value={method.id}>
                {method.label}
              </option>
            ))}
          </select>
          <span className="ill-sd__muted">{runs.filter((run) => run.zoneId === zone.id).length} runs</span>
          <button type="button" className="ill-sd__button ill-sd__button--quiet" onClick={() => onRemove(zone.id)}>
            Remove
          </button>
        </div>
      ))}
      <select
        aria-label="Add zone"
        value=""
        onChange={(event) => event.target.value && onAdd(event.target.value as Zone['method'])}
      >
        <option value="">Add a zone…</option>
        {ZONE_METHODS.map((method) => (
          <option key={method.id} value={method.id}>
            {method.label}
          </option>
        ))}
      </select>
    </article>
  );
}
