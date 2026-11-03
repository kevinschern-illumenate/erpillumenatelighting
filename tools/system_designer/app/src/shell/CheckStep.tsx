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
import { SeverityIcon } from '../ui';
import { CommitInput } from './fields';
import { FIX_STEP } from './checkTargets';
import { entityLabel, type OpenDesign } from './open';
import type { StepId } from './steps';

const SEVERITY_LABEL: Record<DesignMessage['severity'], string> = { error: 'Error', warning: 'Warning', info: 'Note' };
/** The Check step lists errors first and what is already accepted last (SD-2.6). */
const GROUPS = [
  { key: 'error', title: 'Errors' },
  { key: 'warning', title: 'Warnings' },
  { key: 'info', title: 'Notes' },
  { key: 'accepted', title: 'Accepted' },
] as const;
const groupOf = (item: DesignMessage) => (item.override ? 'accepted' : item.severity);
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

/** One line on where the design stands, so the step opens with the answer (SD-2.6). */
export function checkSummary(messages: readonly DesignMessage[]) {
  const open = messages.filter((item) => !item.override);
  const errors = open.filter((item) => item.severity === 'error').length;
  const warnings = open.filter((item) => item.severity === 'warning').length;
  if (errors)
    return {
      tone: 'error' as const,
      text: `${plural(errors, 'error')}${warnings ? ` and ${plural(warnings, 'warning')}` : ''} to fix before you export.`,
    };
  if (warnings)
    return {
      tone: 'warning' as const,
      text: `No errors. Review ${plural(warnings, 'warning')}: fix each one or accept it with a reason.`,
    };
  return { tone: 'ok' as const, text: 'No errors or warnings. The design is ready to export.' };
}

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
  /** Open a step and point at the item a check is about. */
  goTo(step: StepId, ref?: string): void;
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
  const summary = ready ? checkSummary(ready.messages) : null;

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
              <>
                <p
                  className={`sd-check-summary sd-check-summary--${summary?.tone}`}
                  data-testid="check-summary"
                >
                  {summary?.text}
                </p>
                {GROUPS.map((group) => {
                  const items = ready.messages.filter((item) => groupOf(item) === group.key);
                  if (!items.length) return null;
                  return (
                    <div key={group.key} className="sd-check-group">
                      <h4>
                        {group.title} <span className="ill-sd__muted">({items.length})</span>
                      </h4>
                      <ul className="ill-sd__check-list" data-testid={`check-list-${group.key}`}>
                        {items.map((item) => {
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
                              data-entity={item.entityRef}
                            >
                              <SeverityIcon severity={item.override ? 'info' : item.severity} />
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
                                        onClick={() => goTo(fix.step, item.entityRef)}
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
                    </div>
                  );
                })}
              </>
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
                        <tr key={key} data-testid={`result-${key}`} data-entity={result.entityRef}>
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
