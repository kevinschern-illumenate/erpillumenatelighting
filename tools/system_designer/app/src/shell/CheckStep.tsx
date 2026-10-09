import { useState } from 'react';
import { useStore } from 'zustand';
import type { Design } from '@ill/core-schemas/design';
import {
  acknowledge,
  heavierWire,
  percentText,
  setRunWire,
  setVdTarget,
  VD_TARGETS,
  withdrawAcknowledgement,
  type Actor,
  type DesignMessage,
  type VdLimits,
} from '@ill/engine/designCheck';
import type { RunResult } from '@ill/engine/model';
import { runLabel } from '@ill/engine/runs';
import type { CatalogState } from '../design/catalog';
import type { CheckState } from '../design/engine';
import type { DesignStore } from '../design/store';
import { CommitInput } from './fields';
import { entityLabel, type OpenDesign } from './open';
import type { StepId } from './steps';

const ICONS: Record<DesignMessage['severity'], string> = { error: '✖', warning: '▲', info: 'ℹ' };
const SEVERITY_LABEL: Record<DesignMessage['severity'], string> = { error: 'Error', warning: 'Warning', info: 'Note' };

/** Where each check is fixed when the Check step cannot fix it in place. */
const POWER = { step: 'power', label: 'Open Power' } as const;
const SPACES = { step: 'spaces', label: 'Open Spaces' } as const;
const RUNS = { step: 'runs', label: 'Open Runs' } as const;
const FIX_STEP: Record<string, { step: StepId; label: string }> = {
  PSU_OVERLOAD: POWER,
  PSU_ABOVE_DERATE: POWER,
  CHANNEL_OVERCURRENT: POWER,
  BREAKER_OVERLOAD: POWER,
  CLASS2_OVER_100VA: POWER,
  VOLTAGE_MISMATCH: POWER,
  DRIVE_MISMATCH: POWER,
  PROTOCOL_MISMATCH: POWER,
  RUN_UNASSIGNED: POWER,
  UNRESOLVED_REF: POWER,
  SUPPLY_NO_ACCESS: SPACES,
  NO_VALID_WIRE: SPACES,
  VD_OVER_TARGET: SPACES,
  TAPE_UNDERVOLTAGE: SPACES,
  TAPE_RUN_TOO_LONG: RUNS,
  INVALID_SPEC: RUNS,
  SCHEDULE_OUT_OF_SYNC: { step: 'start', label: 'Open Start' },
};

const feet = (value: number) => `${Number(value.toFixed(1))} ft`;
const keyOf = (item: DesignMessage) => `${item.code}:${item.entityRef}:${item.text}`;

/** The Check step (plan §11, WP-3.5): voltage-drop targets, sized runs and every check with its fix. */
export function CheckStep({
  open,
  store,
  engine,
  catalog,
  limits,
  readOnly,
  goTo,
}: {
  open: OpenDesign;
  store: DesignStore;
  engine: CheckState;
  catalog: CatalogState;
  limits: VdLimits;
  readOnly: boolean;
  goTo(step: StepId): void;
}) {
  const design = useStore(store, (s) => s.design);
  const [error, setError] = useState('');
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [accepting, setAccepting] = useState<string | null>(null);
  const [looserReason, setLooserReason] = useState('');
  if (!design) return null;

  const staff = open.permissions.can_review;
  const actor = (): Actor => ({ by: open.user ?? 'unknown', at: new Date().toISOString(), staff });
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
  const wireLabel = (id: string | null) => {
    if (!id) return 'No wire passes';
    const wire = catalog.state === 'ready' ? catalog.catalog.wires.find((item) => item.id === id) : undefined;
    return wire?.riserLabel ?? id;
  };
  const ready = engine.state === 'ready' ? engine.check : null;
  const runFor = (ref: string): RunResult | undefined => ready?.runs[ref.replace(/^load:/, '')];
  const runName = (result: RunResult) => {
    const key = result.entityRef.replace(/^load:/, '');
    const run = design.runs.find((item) => item.key === key);
    return run ? runLabel(run) : result.tag;
  };
  const pinned = Object.keys(design.project.wireOverrides);

  return (
    <section aria-labelledby="ill-sd-step-title" className="ill-sd__check-step">
      <h2 id="ill-sd-step-title">Check</h2>
      <p className="ill-sd__muted">
        Fix voltage drop, loading and control issues before you export. Checks update as you edit.
      </p>
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="ill-sd__card" data-testid="vd-targets">
        <h3>Voltage-drop targets</h3>
        <p className="ill-sd__muted">
          {staff
            ? 'Tighten freely. A looser target than Settings needs a reason and is recorded as your override.'
            : 'You can set a tighter target. ilLumenate reviews any looser target.'}
        </p>
        <div className="ill-sd__row">
          {VD_TARGETS.map((target) => (
            <label key={target.key} className="ill-sd__pick">
              {target.label} (%)
              {readOnly ? (
                <span>{design.project.settings[target.key]}%</span>
              ) : (
                <CommitInput
                  label={`${target.label} target`}
                  type="number"
                  min={0}
                  step="any"
                  value={design.project.settings[target.key]}
                  onCommit={(text) =>
                    change((draft) =>
                      setVdTarget(draft, target.key, Number(text), limits, actor(), looserReason || undefined),
                    )
                  }
                />
              )}
              <span className="ill-sd__muted">Settings: {limits[target.key]}%</span>
            </label>
          ))}
        </div>
        {staff && !readOnly ? (
          <label className="ill-sd__pick">
            Reason for a looser target
            <input
              aria-label="Reason for a looser target"
              value={looserReason}
              onChange={(event) => setLooserReason(event.target.value)}
            />
          </label>
        ) : null}
      </div>

      {engine.state === 'waiting' ? (
        <p className="ill-sd__muted" role="status">
          {catalog.state === 'error' ? catalog.message : 'Running the checks…'}
        </p>
      ) : engine.state === 'error' ? (
        <p className="ill-sd__error" role="alert">
          The checks could not run: {engine.message}
        </p>
      ) : null}

      {ready ? (
        <>
          <div className="ill-sd__card">
            <h3>Checks</h3>
            {ready.messages.length === 0 ? (
              <p data-testid="checks-clear">No issues. The design passes every check.</p>
            ) : (
              <ul className="ill-sd__check-list" data-testid="check-list">
                {ready.messages.map((item) => {
                  const id = keyOf(item);
                  const run = runFor(item.entityRef);
                  const heavier =
                    run && (item.code === 'VD_OVER_TARGET' || item.code === 'TAPE_UNDERVOLTAGE')
                      ? heavierWire(run)
                      : null;
                  const fix = FIX_STEP[item.code];
                  const canAccept =
                    !readOnly &&
                    !item.override &&
                    (item.severity === 'warning' || (item.severity === 'error' && staff));
                  return (
                    <li
                      key={id}
                      className={`ill-sd__check ill-sd__check--${item.override ? 'info' : item.severity}`}
                      data-testid={`check-${item.code}-${item.entityRef}`}
                    >
                      <span aria-hidden="true">{ICONS[item.override ? 'info' : item.severity]}</span>
                      <div>
                        <p>
                          <strong>{entityLabel(design, item.entityRef)}</strong>
                          <span className="ill-sd__sr"> {SEVERITY_LABEL[item.severity]}</span>
                        </p>
                        <p>{item.text}</p>
                        {item.override ? (
                          <p className="ill-sd__muted">
                            {item.override.kind === 'staff-override' ? 'Overridden by ilLumenate' : 'Accepted'}:{' '}
                            {item.override.reason}
                          </p>
                        ) : null}
                        {readOnly ? null : (
                          <div className="ill-sd__row">
                            {heavier && run ? (
                              <button
                                type="button"
                                className="ill-sd__button ill-sd__button--quiet"
                                onClick={() => change((draft) => setRunWire(draft, run.runId, heavier))}
                              >
                                Use {wireLabel(heavier)}
                              </button>
                            ) : null}
                            {fix ? (
                              <button
                                type="button"
                                className="ill-sd__button ill-sd__button--quiet"
                                onClick={() => goTo(fix.step)}
                              >
                                {fix.label}
                              </button>
                            ) : null}
                            {canAccept && accepting !== id ? (
                              <button
                                type="button"
                                className="ill-sd__button ill-sd__button--quiet"
                                onClick={() => setAccepting(id)}
                              >
                                {item.severity === 'error' ? 'Override' : 'Accept'}
                              </button>
                            ) : null}
                            {item.override ? (
                              <button
                                type="button"
                                className="ill-sd__button ill-sd__button--quiet"
                                onClick={() =>
                                  change((draft) => withdrawAcknowledgement(draft, item.code, item.entityRef))
                                }
                              >
                                Withdraw
                              </button>
                            ) : null}
                          </div>
                        )}
                        {canAccept && accepting === id ? (
                          <form
                            className="ill-sd__row"
                            onSubmit={(event) => {
                              event.preventDefault();
                              if (change((draft) => acknowledge(draft, item, reasons[id] ?? '', actor())))
                                setAccepting(null);
                            }}
                          >
                            <input
                              aria-label={`Reason for ${entityLabel(design, item.entityRef)}`}
                              value={reasons[id] ?? ''}
                              onChange={(event) => setReasons({ ...reasons, [id]: event.target.value })}
                            />
                            <button type="submit" className="ill-sd__button">
                              Save reason
                            </button>
                            <button
                              type="button"
                              className="ill-sd__button ill-sd__button--quiet"
                              onClick={() => setAccepting(null)}
                            >
                              Cancel
                            </button>
                          </form>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="ill-sd__card">
            <h3>Home runs</h3>
            {Object.keys(ready.runs).length === 0 ? (
              <p className="ill-sd__muted">Assign runs on the Power step to size their wire.</p>
            ) : (
              <div className="ill-sd__table-wrap">
                <table className="ill-sd__table" data-testid="run-results">
                  <thead>
                    <tr>
                      <th scope="col">Run</th>
                      <th scope="col">Wire</th>
                      <th scope="col">Length</th>
                      <th scope="col">Current</th>
                      <th scope="col">Voltage drop</th>
                      <th scope="col">End voltage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ready.runs).map(([key, result]) => {
                      const target = result.voltageV <= 60 ? ready.targets.vdTargetLowVoltagePct : null;
                      const over = result.checks.voltageDrop === false;
                      return (
                        <tr key={key} data-testid={`result-${key}`}>
                          <th scope="row">{runName(result)}</th>
                          <td>
                            {wireLabel(result.wireTypeId)}
                            {result.overridden ? ' (pinned)' : ''}
                          </td>
                          <td>{feet(result.lengthFt)}</td>
                          <td>{Number(result.currentA.toFixed(2))} A</td>
                          <td className={over ? 'ill-sd__error' : undefined}>
                            {percentText(result.vdPct)}
                            {target !== null ? ` of ${target}%` : ''}
                          </td>
                          <td>{result.endV === null ? '—' : `${Number(result.endV.toFixed(2))} V`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}

      {pinned.length ? (
        <div className="ill-sd__card" data-testid="pinned-wires">
          <h3>Pinned wires</h3>
          <ul>
            {pinned.map((runId) => {
              const result = ready?.result.runs.find((item) => item.runId === runId);
              return (
                <li key={runId}>
                  {result ? runName(result) : runId}: {wireLabel(design.project.wireOverrides[runId]!.wireTypeId)}{' '}
                  {readOnly ? null : (
                    <button
                      type="button"
                      className="ill-sd__button ill-sd__button--quiet"
                      onClick={() => change((draft) => setRunWire(draft, runId, undefined))}
                    >
                      Back to automatic
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
