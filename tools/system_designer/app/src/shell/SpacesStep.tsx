import { useState } from 'react';
import { useStore } from 'zustand';
import type { Design, Run } from '@ill/core-schemas/design';
import { choiceOf } from '@ill/data/environments';
import {
  addCabinet,
  addCircuit,
  DISTANCE_LABELS,
  distanceDefaults,
  mergeSpaces,
  pickLength,
  removeCabinet,
  removeCircuit,
  renameSpace,
  setCabinetEnvironment,
  setCabinetFeed,
  setHomeRuns,
  setRunEnvironment,
  setSpaceEnvironment,
  updateCabinet,
  updateCircuit,
  type DistancePick,
} from '@ill/engine/site';
import type { DesignStore } from '../design/store';
import { CommitInput, EnvironmentSelect, parseFeet } from './fields';
import type { OpenDesign } from './open';

const PICKS = Object.keys(DISTANCE_LABELS) as DistancePick[];
const VOLTAGES = [120, 208, 240, 277, 347, 480] as const;
const PROVENANCE: Record<Run['homeRunProvenance'], string> = {
  estimate: 'estimate',
  entered: 'entered',
  measured: 'measured',
  erp: 'from ERP',
};

/** "F3-1.2": line, copy and run (plan §9.1). */
export const runLabel = (run: Pick<Run, 'lineId' | 'buildIndex' | 'runIndex'>) =>
  `${run.lineId}-${run.buildIndex}.${run.runIndex}`;

export function SpacesStep({ open, store, readOnly }: { open: OpenDesign; store: DesignStore; readOnly: boolean }) {
  const design = useStore(store, (s) => s.design);
  const [error, setError] = useState('');
  const defaults = distanceDefaults(open.settings);
  if (!design) return null;

  const change = (recipe: (draft: Design) => void) => {
    try {
      store.getState().edit((draft) => recipe(draft as Design));
      setError('');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    }
  };
  const feet = (text: string, apply: (value: number) => void) => {
    const value = parseFeet(text);
    if (value === null) setError('Enter a length in feet, 0 or more');
    else apply(value);
  };
  const { spaces, cabinets } = design.site;
  const sources = design.project.sources;

  return (
    <section aria-labelledby="ill-sd-spaces-title" className="ill-sd__spaces">
      <h2 id="ill-sd-spaces-title">Spaces</h2>
      <p className="ill-sd__muted">
        Spaces come from the schedule locations. Rename or merge them, add the cabinets that hold supplies, and set the
        distance from each run to its supply. A space’s environment applies to its cabinets and runs unless you set
        theirs separately.
      </p>
      {error ? (
        <p role="alert" className="ill-sd__error">
          {error}
        </p>
      ) : null}
      <fieldset disabled={readOnly} className="ill-sd__fieldset">
        {spaces.map((space) => {
          const runs = design.runs.filter((run) => run.spaceId === space.id);
          const spaceCabinets = cabinets.filter((cabinet) => cabinet.spaceId === space.id);
          return (
            <article key={space.id} className="ill-sd__card" data-testid={`space-${space.id}`}>
              <div className="ill-sd__row">
                <CommitInput
                  label="Space name"
                  className="ill-sd__name"
                  value={space.name}
                  onCommit={(name) => change((draft) => renameSpace(draft, space.id, name))}
                />
                <CommitInput
                  label="Level"
                  value={space.level}
                  onCommit={(level) => change((draft) => renameSpace(draft, space.id, space.name, level))}
                />
                <EnvironmentSelect
                  label={`${space.name} environment`}
                  value={choiceOf(space)}
                  onChange={(choice) => change((draft) => setSpaceEnvironment(draft, space.id, choice))}
                />
                {spaces.length > 1 ? (
                  <select
                    aria-label={`Merge ${space.name} into`}
                    value=""
                    onChange={(event) =>
                      event.target.value && change((draft) => mergeSpaces(draft, space.id, event.target.value))
                    }
                  >
                    <option value="">Merge into…</option>
                    {spaces
                      .filter((other) => other.id !== space.id)
                      .map((other) => (
                        <option key={other.id} value={other.id}>
                          {other.name}
                        </option>
                      ))}
                  </select>
                ) : null}
              </div>

              <h3>Cabinets</h3>
              {spaceCabinets.map((cabinet) => (
                <div key={cabinet.id} className="ill-sd__cabinet" data-testid={`cabinet-${cabinet.tag}`}>
                  <div className="ill-sd__row">
                    <CommitInput
                      label="Cabinet tag"
                      className="ill-sd__tag"
                      value={cabinet.tag}
                      onCommit={(tag) => change((draft) => updateCabinet(draft, cabinet.id, { tag }))}
                    />
                    <CommitInput
                      label="Cabinet name"
                      value={cabinet.name}
                      onCommit={(name) => change((draft) => updateCabinet(draft, cabinet.id, { name }))}
                    />
                    <EnvironmentSelect
                      label={`${cabinet.tag} environment`}
                      value={choiceOf(cabinet)}
                      onChange={(choice) => change((draft) => setCabinetEnvironment(draft, cabinet.id, choice))}
                    />
                    <select
                      aria-label={`${cabinet.tag} location rating`}
                      value={cabinet.locationRating}
                      onChange={(event) =>
                        change((draft) =>
                          updateCabinet(draft, cabinet.id, {
                            locationRating: event.target.value as 'Dry' | 'Damp' | 'Wet',
                          }),
                        )
                      }
                    >
                      {['Dry', 'Damp', 'Wet'].map((rating) => (
                        <option key={rating}>{rating}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="ill-sd__button ill-sd__button--quiet"
                      onClick={() => change((draft) => removeCabinet(draft, cabinet.id))}
                    >
                      Remove
                    </button>
                  </div>
                  <div className="ill-sd__row">
                    <CommitInput
                      label={`${cabinet.tag} access note`}
                      value={cabinet.accessNote}
                      onCommit={(accessNote) => change((draft) => updateCabinet(draft, cabinet.id, { accessNote }))}
                    />
                    <select
                      aria-label={`${cabinet.tag} circuit`}
                      value={cabinet.sourceId ?? ''}
                      onChange={(event) =>
                        change((draft) =>
                          updateCabinet(draft, cabinet.id, { sourceId: event.target.value || undefined }),
                        )
                      }
                    >
                      <option value="">No circuit yet</option>
                      {sources.map((source) => (
                        <option key={source.id} value={source.id}>
                          {source.panel}/{source.circuit} · {source.voltage} V
                        </option>
                      ))}
                    </select>
                    <Distance
                      label={`${cabinet.tag} feed length`}
                      value={cabinet.feedLengthFt}
                      provenance={PROVENANCE[cabinet.feedLengthProvenance]}
                      onType={(text) =>
                        feet(text, (value) => change((draft) => setCabinetFeed(draft, cabinet.id, value, false)))
                      }
                      onPick={(pick) =>
                        change((draft) => setCabinetFeed(draft, cabinet.id, pickLength(pick, defaults), true))
                      }
                    />
                  </div>
                </div>
              ))}
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                onClick={() => change((draft) => void addCabinet(draft, space.id, defaults))}
              >
                Add cabinet
              </button>

              <h3>Runs</h3>
              {runs.length ? (
                <>
                  <div className="ill-sd__row ill-sd__muted">
                    Set all home runs in {space.name}:
                    {PICKS.map((pick) => (
                      <button
                        key={pick}
                        type="button"
                        className="ill-sd__pick"
                        onClick={() =>
                          change((draft) =>
                            setHomeRuns(
                              draft,
                              runs.map((run) => run.key),
                              pickLength(pick, defaults),
                              true,
                            ),
                          )
                        }
                      >
                        {DISTANCE_LABELS[pick]} ({pickLength(pick, defaults)} ft)
                      </button>
                    ))}
                  </div>
                  <ul className="ill-sd__runs">
                    {runs.map((run) => (
                      <li key={run.key} data-testid={`run-${run.key}`}>
                        <span className="ill-sd__run-label">{runLabel(run)}</span>
                        <span>
                          {run.watts} W{run.lengthFt ? ` · ${run.lengthFt} ft` : ''}
                        </span>
                        {run.source.kind === 'third-party' ? (
                          <span
                            className="ill-sd__chip ill-sd__chip--warn"
                            title="Third-party data entered by the dealer"
                          >
                            Data by dealer
                          </span>
                        ) : null}
                        <EnvironmentSelect
                          label={`${runLabel(run)} environment`}
                          value={choiceOf(run)}
                          onChange={(choice) => change((draft) => setRunEnvironment(draft, [run.key], choice))}
                        />
                        <Distance
                          label={`${runLabel(run)} home run`}
                          value={run.homeRunLengthFt}
                          provenance={PROVENANCE[run.homeRunProvenance]}
                          onType={(text) =>
                            feet(text, (value) => change((draft) => setHomeRuns(draft, [run.key], value, false)))
                          }
                          onPick={(pick) =>
                            change((draft) => setHomeRuns(draft, [run.key], pickLength(pick, defaults), true))
                          }
                        />
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="ill-sd__muted">No runs in this space.</p>
              )}
            </article>
          );
        })}

        <article className="ill-sd__card" data-testid="panel">
          <h3>Panel circuits</h3>
          {sources.length ? null : <p className="ill-sd__muted">Add the circuits that feed your cabinets.</p>}
          {sources.map((source) => (
            <div key={source.id} className="ill-sd__row" data-testid={`circuit-${source.tag}`}>
              <span className="ill-sd__tag">{source.tag}</span>
              <CommitInput
                label={`${source.tag} panel`}
                value={source.panel}
                onCommit={(panel) =>
                  change((draft) => updateCircuit(draft, source.id, { panel: panel.trim() || source.panel }))
                }
              />
              <CommitInput
                label={`${source.tag} circuit number`}
                value={source.circuit}
                onCommit={(circuit) =>
                  change((draft) => updateCircuit(draft, source.id, { circuit: circuit.trim() || source.circuit }))
                }
              />
              <select
                aria-label={`${source.tag} voltage`}
                value={source.voltage}
                onChange={(event) =>
                  change((draft) =>
                    updateCircuit(draft, source.id, {
                      voltage: Number(event.target.value) as (typeof VOLTAGES)[number],
                    }),
                  )
                }
              >
                {VOLTAGES.map((voltage) => (
                  <option key={voltage} value={voltage}>
                    {voltage} V
                  </option>
                ))}
              </select>
              <CommitInput
                label={`${source.tag} breaker amps`}
                type="number"
                min={1}
                value={source.breakerA}
                onCommit={(text) => {
                  const amps = Number(text);
                  if (Number.isFinite(amps) && amps > 0)
                    change((draft) => updateCircuit(draft, source.id, { breakerA: amps }));
                  else setError('Enter the breaker size in amps');
                }}
              />
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                onClick={() => change((draft) => removeCircuit(draft, source.id))}
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className="ill-sd__button ill-sd__button--quiet"
            onClick={() => change((draft) => void addCircuit(draft))}
          >
            Add circuit
          </button>
        </article>
      </fieldset>
    </section>
  );
}

function Distance({
  label,
  value,
  provenance,
  onType,
  onPick,
}: {
  label: string;
  value: number;
  provenance: string;
  onType(text: string): void;
  onPick(pick: DistancePick): void;
}) {
  return (
    <span className="ill-sd__distance">
      <CommitInput
        label={label}
        type="number"
        min={0}
        step="any"
        value={value}
        onCommit={onType}
        className="ill-sd__feet"
      />
      ft <span className="ill-sd__muted">({provenance})</span>
      <select
        aria-label={`${label} quick pick`}
        value=""
        onChange={(event) => event.target.value && onPick(event.target.value as DistancePick)}
      >
        <option value="">Quick pick…</option>
        {PICKS.map((pick) => (
          <option key={pick} value={pick}>
            {DISTANCE_LABELS[pick]}
          </option>
        ))}
      </select>
    </span>
  );
}
