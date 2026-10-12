import { Fragment, useMemo, useState, type ReactNode } from 'react';
import { useStore } from 'zustand';
import type { Design, EnvChoice, Run } from '@ill/core-schemas/design';
import type { Build } from '@ill/core-schemas/open-design';
import type { ValidationMessage } from '@ill/core-schemas/project';
import { choiceOf, ENVIRONMENTS, environmentOption } from '@ill/data/environments';
import {
  buildFor,
  feedPositions,
  groupRuns,
  moveRuns,
  runChecks,
  runLabel,
  runRows,
  runType,
  splitGroup,
  type RunRow,
} from '@ill/engine/runs';
import {
  DISTANCE_LABELS,
  distanceDefaults,
  pickLength,
  setHomeRuns,
  setRunEnvironment,
  type DistancePick,
} from '@ill/engine/site';
import type { DesignStore } from '../design/store';
import { CommitInput, parseFeet, PICKS, PROVENANCE } from './fields';
import type { OpenDesign } from './open';

const FEEDS: Record<Run['feedMethod'], string> = {
  end: 'End',
  'double-end': 'Both ends',
  center: 'Center',
  'multi-feed': 'Multi-feed',
};
const ICONS: Record<ValidationMessage['severity'], string> = { error: '✖', warning: '▲', info: 'ℹ' };
const RANK: Record<ValidationMessage['severity'], number> = { error: 0, warning: 1, info: 2 };

const feet = (value: number | undefined) => (value === undefined ? '—' : `${Number(value.toFixed(2))} ft`);
const feedText = (run: Run) =>
  run.feedMethod === 'multi-feed' && run.feeds ? `${FEEDS[run.feedMethod]} (${run.feeds})` : FEEDS[run.feedMethod];

/** The run list (plan §9.3): every run with its checks, bulk edits, group and split, and a strip preview. */
export function RunsStep({ open, store, readOnly }: { open: OpenDesign; store: DesignStore; readOnly: boolean }) {
  const design = useStore(store, (s) => s.design);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [focus, setFocus] = useState<string | null>(null);
  const [spaceFilter, setSpaceFilter] = useState('');
  const [error, setError] = useState('');
  const checks = useMemo(() => (design ? runChecks(design, open.builds) : []), [design, open.builds]);
  if (!design) return null;

  const defaults = distanceDefaults(open.settings);
  const byRun = new Map<string, ValidationMessage[]>();
  for (const check of checks) byRun.set(check.entityRef, [...(byRun.get(check.entityRef) ?? []), check]);
  const spaceName = new Map(design.site.spaces.map((space) => [space.id, space.name]));
  const equipment = new Map(design.project.equipment.map((item) => [item.id, item.tag]));
  const visible = design.runs.filter((run) => !spaceFilter || run.spaceId === spaceFilter);
  const rows = runRows(visible);
  const keys = [...selected].filter((key) => design.runs.some((run) => run.key === key));
  const focused = design.runs.find((run) => run.key === focus) ?? null;

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
  const toggle = (row: RunRow, on: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      for (const run of row.runs) {
        if (on) next.add(run.key);
        else next.delete(run.key);
      }
      return next;
    });
  const allVisible = rows.length > 0 && rows.every((row) => row.runs.every((run) => selected.has(run.key)));

  return (
    <section aria-labelledby="ill-sd-runs-title" className="ill-sd__runs-step">
      <h2 id="ill-sd-runs-title">Runs</h2>
      <p className="ill-sd__muted">
        Every run from the schedule. Lengths, watts and feeds come from the configured products; change them in the
        configurator. Select runs to move them, set their environment or home-run length together, or group identical
        copies so they are assigned once.
      </p>
      {error ? (
        <p role="alert" className="ill-sd__error">
          {error}
        </p>
      ) : null}
      <fieldset disabled={readOnly} className="ill-sd__fieldset">
        <div className="ill-sd__row">
          <select aria-label="Show space" value={spaceFilter} onChange={(event) => setSpaceFilter(event.target.value)}>
            <option value="">All spaces</option>
            {design.site.spaces.map((space) => (
              <option key={space.id} value={space.id}>
                {space.name}
              </option>
            ))}
          </select>
          <span className="ill-sd__muted" data-testid="run-count">
            {visible.length} {visible.length === 1 ? 'run' : 'runs'} ·{' '}
            {Number(visible.reduce((sum, run) => sum + run.watts, 0).toFixed(1))} W
          </span>
        </div>

        {keys.length ? (
          <BulkBar
            count={keys.length}
            spaces={design.site.spaces}
            defaults={defaults}
            onMove={(spaceId) => change((draft) => moveRuns(draft, keys, spaceId))}
            onEnvironment={(choice) => change((draft) => setRunEnvironment(draft, keys, choice))}
            onPick={(length) => change((draft) => setHomeRuns(draft, keys, length, true))}
            onType={(text) => {
              const value = parseFeet(text);
              if (value === null) setError('Enter a length in feet, 0 or more');
              else change((draft) => setHomeRuns(draft, keys, value, false));
            }}
            onGroup={() => change((draft) => void groupRuns(draft, keys)) && setSelected(new Set())}
            onClear={() => setSelected(new Set())}
          />
        ) : null}

        <div className="ill-sd__table-wrap">
          <table className="ill-sd__table">
            <thead>
              <tr>
                <th scope="col">
                  <input
                    type="checkbox"
                    aria-label="Select all runs"
                    checked={allVisible}
                    onChange={(event) => rows.forEach((row) => toggle(row, event.target.checked))}
                  />
                </th>
                <th scope="col">Run</th>
                <th scope="col">Type</th>
                <th scope="col">Space</th>
                <th scope="col">Length</th>
                <th scope="col">Watts</th>
                <th scope="col">Feed</th>
                <th scope="col">Environment</th>
                <th scope="col">Home run</th>
                <th scope="col">Supply</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isOpen = row.groupId ? expanded.has(row.groupId) : false;
                const members = row.groupId && row.runs.length > 1 ? row.runs : [];
                return (
                  <Fragment key={row.id}>
                    <RunLine
                      row={row}
                      label={row.label}
                      selected={row.runs.every((run) => selected.has(run.key))}
                      onSelect={(on) => toggle(row, on)}
                      onFocus={() => setFocus(row.runs[0]!.key)}
                      focused={row.runs.some((run) => run.key === focus)}
                      spaceName={spaceName}
                      equipment={equipment}
                      checks={row.runs.flatMap((run) => byRun.get(run.key) ?? [])}
                      type={runType(row.runs[0]!, open.builds)}
                      group={
                        members.length ? (
                          <span className="ill-sd__group-actions">
                            <button
                              type="button"
                              className="ill-sd__pick"
                              aria-expanded={isOpen}
                              onClick={() =>
                                setExpanded((current) => {
                                  const next = new Set(current);
                                  if (next.has(row.groupId!)) next.delete(row.groupId!);
                                  else next.add(row.groupId!);
                                  return next;
                                })
                              }
                            >
                              {isOpen ? 'Hide runs' : 'Show runs'}
                            </button>
                            <button
                              type="button"
                              className="ill-sd__pick"
                              onClick={() => change((draft) => splitGroup(draft, row.groupId!))}
                            >
                              Split
                            </button>
                          </span>
                        ) : null
                      }
                    />
                    {isOpen
                      ? members.map((run) => (
                          <RunLine
                            key={run.key}
                            nested
                            row={{ id: run.key, label: runLabel(run), runs: [run] }}
                            label={runLabel(run)}
                            selected={selected.has(run.key)}
                            onSelect={(on) => toggle({ id: run.key, label: '', runs: [run] }, on)}
                            onFocus={() => setFocus(run.key)}
                            focused={run.key === focus}
                            spaceName={spaceName}
                            equipment={equipment}
                            checks={byRun.get(run.key) ?? []}
                            type={runType(run, open.builds)}
                          />
                        ))
                      : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        {rows.length ? null : <p className="ill-sd__muted">No runs in this space.</p>}
      </fieldset>

      {focused ? (
        <StripPreview
          run={focused}
          build={buildFor(focused, open.builds)}
          checks={byRun.get(focused.key) ?? []}
          onClose={() => setFocus(null)}
        />
      ) : (
        <p className="ill-sd__muted">Choose a run to preview its strip and feeds.</p>
      )}
    </section>
  );
}

function RunLine({
  row,
  label,
  selected,
  onSelect,
  onFocus,
  focused,
  spaceName,
  equipment,
  checks,
  type,
  group,
  nested = false,
}: {
  row: RunRow;
  label: string;
  selected: boolean;
  onSelect(on: boolean): void;
  onFocus(): void;
  focused: boolean;
  spaceName: Map<string, string>;
  equipment: Map<string, string>;
  checks: ValidationMessage[];
  type: string;
  group?: ReactNode;
  nested?: boolean;
}) {
  const run = row.runs[0]!;
  const count = row.runs.length;
  const worst = [...checks].sort((a, b) => RANK[a.severity] - RANK[b.severity])[0];
  const assigned = row.runs.filter((item) => item.assignment).length;
  const supply = run.assignment
    ? `${equipment.get(run.assignment.equipmentId) ?? run.assignment.equipmentId} · output ${run.assignment.port}`
    : null;
  return (
    <tr
      className={`${nested ? 'ill-sd__nested' : ''}${focused ? ' ill-sd__focused' : ''}`.trim() || undefined}
      data-testid={`row-${row.id}`}
    >
      <td>
        <input
          type="checkbox"
          aria-label={`Select ${label}`}
          checked={selected}
          onChange={(event) => onSelect(event.target.checked)}
        />
      </td>
      <th scope="row">
        <button type="button" className="ill-sd__link" onClick={onFocus}>
          {label}
        </button>
        {group}
      </th>
      <td>
        {type}
        {run.source.kind === 'third-party' ? (
          <span className="ill-sd__chip ill-sd__chip--warn" title="Third-party data entered by the dealer">
            Data by dealer
          </span>
        ) : null}
      </td>
      <td>{spaceName.get(run.spaceId) ?? run.spaceId}</td>
      <td>{feet(run.lengthFt)}</td>
      <td>{count > 1 ? `${run.watts} W each` : `${run.watts} W`}</td>
      <td>{feedText(run)}</td>
      <td>{environmentOption(choiceOf(run)).label}</td>
      <td>
        {feet(run.homeRunLengthFt)} <span className="ill-sd__muted">({PROVENANCE[run.homeRunProvenance]})</span>
      </td>
      <td>{count > 1 ? `${assigned} of ${count} assigned` : (supply ?? 'Not assigned')}</td>
      <td>
        {worst ? (
          <span className={`ill-sd__status ill-sd__status--${worst.severity}`} title={worst.text}>
            <span aria-hidden="true">{ICONS[worst.severity]}</span>{' '}
            {checks.length === 1 ? worst.text : `${checks.length} checks`}
          </span>
        ) : (
          <span className="ill-sd__status ill-sd__status--ok">OK</span>
        )}
      </td>
    </tr>
  );
}

function BulkBar({
  count,
  spaces,
  defaults,
  onMove,
  onEnvironment,
  onPick,
  onType,
  onGroup,
  onClear,
}: {
  count: number;
  spaces: Design['site']['spaces'];
  defaults: ReturnType<typeof distanceDefaults>;
  onMove(spaceId: string): void;
  onEnvironment(choice: EnvChoice): void;
  onPick(length: number): void;
  onType(text: string): void;
  onGroup(): void;
  onClear(): void;
}) {
  return (
    <div className="ill-sd__bulk" role="group" aria-label="Selected runs">
      <strong>
        {count} {count === 1 ? 'run' : 'runs'} selected
      </strong>
      <select
        aria-label="Move selected to space"
        value=""
        onChange={(event) => event.target.value && onMove(event.target.value)}
      >
        <option value="">Move to space…</option>
        {spaces.map((space) => (
          <option key={space.id} value={space.id}>
            {space.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Selected environment"
        value=""
        onChange={(event) => event.target.value && onEnvironment(event.target.value as EnvChoice)}
      >
        <option value="">Set environment…</option>
        {ENVIRONMENTS.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      <span className="ill-sd__distance">
        Home run
        <CommitInput
          label="Selected home run"
          type="number"
          min={0}
          step="any"
          value=""
          onCommit={onType}
          className="ill-sd__feet"
        />
        ft
        <select
          aria-label="Selected home run quick pick"
          value=""
          onChange={(event) => event.target.value && onPick(pickLength(event.target.value as DistancePick, defaults))}
        >
          <option value="">Quick pick…</option>
          {PICKS.map((pick) => (
            <option key={pick} value={pick}>
              {DISTANCE_LABELS[pick]} ({pickLength(pick, defaults)} ft)
            </option>
          ))}
        </select>
      </span>
      <button type="button" className="ill-sd__button ill-sd__button--quiet" disabled={count < 2} onClick={onGroup}>
        Group
      </button>
      <button type="button" className="ill-sd__button ill-sd__button--quiet" onClick={onClear}>
        Clear selection
      </button>
    </div>
  );
}

const STRIP = { width: 560, left: 20, top: 34, height: 14 };

/** The run drawn to scale against the build's maximum length, with its feed points (plan §9.3). */
export function StripPreview({
  run,
  build,
  checks,
  onClose,
}: {
  run: Run;
  build: Build | undefined;
  checks: ValidationMessage[];
  onClose(): void;
}) {
  const max = build?.maxRunFtEffective ?? null;
  const length = run.lengthFt;
  const span = Math.max(length ?? 0, max ?? 0) || 1;
  const scale = (STRIP.width - STRIP.left * 2) / span;
  const drawn = length === undefined ? STRIP.width - STRIP.left * 2 : length * scale;
  const over = length !== undefined && max !== null && length > max;
  const x = (share: number) => STRIP.left + share * drawn;
  const title = `${runLabel(run)} strip preview`;
  return (
    <figure className="ill-sd__card ill-sd__strip" data-testid="strip-preview">
      <figcaption className="ill-sd__row">
        <strong>{runLabel(run)}</strong>
        <span className="ill-sd__muted">
          {length === undefined ? 'No length (sheet feed)' : feet(length)} · {run.watts} W · {feedText(run)} feed
          {max !== null ? ` · max ${feet(max)}` : ''}
        </span>
        <button type="button" className="ill-sd__pick" onClick={onClose}>
          Close
        </button>
      </figcaption>
      <svg viewBox={`0 0 ${STRIP.width} 70`} role="img" aria-label={title}>
        <rect
          x={STRIP.left}
          y={STRIP.top}
          width={drawn}
          height={STRIP.height}
          rx={4}
          className={over ? 'ill-sd__strip-bar ill-sd__strip-bar--over' : 'ill-sd__strip-bar'}
          strokeDasharray={length === undefined ? '6 4' : undefined}
        />
        {max !== null && length !== undefined ? (
          <g data-testid="strip-max">
            <line
              x1={STRIP.left + max * scale}
              x2={STRIP.left + max * scale}
              y1={STRIP.top - 10}
              y2={STRIP.top + STRIP.height + 10}
              className="ill-sd__strip-max"
            />
            <text x={STRIP.left + max * scale} y={STRIP.top + STRIP.height + 22} textAnchor="middle">
              max {Number(max.toFixed(1))} ft
            </text>
          </g>
        ) : null}
        {feedPositions(run).map((share) => (
          <g key={share} data-testid="strip-feed">
            <polygon
              points={`${x(share) - 6},${STRIP.top - 14} ${x(share) + 6},${STRIP.top - 14} ${x(share)},${STRIP.top - 2}`}
              className="ill-sd__strip-feed"
            />
            <text x={x(share)} y={STRIP.top - 18} textAnchor="middle">
              feed
            </text>
          </g>
        ))}
      </svg>
      {checks.length ? (
        <ul className="ill-sd__check-list">
          {checks.map((check) => (
            <li key={check.code + check.text} className={`ill-sd__check ill-sd__check--${check.severity}`}>
              <span aria-hidden="true">{ICONS[check.severity]}</span>
              <p>{check.text}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </figure>
  );
}
