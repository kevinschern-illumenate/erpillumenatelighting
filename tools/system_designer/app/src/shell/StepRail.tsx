import { Check as CheckMark } from 'lucide-react';
import { SeverityIcon } from '../ui';
import { stepStateLabel, type StepState } from './stepState';
import { GRIDS_TAB, STEPS, type Mode, type StepId } from './steps';

/** The steps down the left (SD-1.3): number, name, and whether each has errors, warnings or is done (SD-2.1). */
export function StepRail({
  mode,
  step,
  states,
  onStep,
}: {
  mode: Mode;
  step: StepId;
  states: Record<StepId, StepState>;
  onStep(step: StepId): void;
}) {
  const items = mode === 'engineering' ? [...STEPS, GRIDS_TAB] : STEPS;
  return (
    <nav className="sd-rail" aria-label={mode === 'guided' ? 'Design steps' : 'Design tabs'}>
      <ol>
        {items.map((item, position) => {
          const state = states[item.id];
          const current = item.id === step;
          return (
            <li key={item.id}>
              <button
                type="button"
                className={`sd-rail__step sd-rail__step--${state.status}`}
                aria-current={current ? 'step' : undefined}
                aria-describedby={`sd-rail-state-${item.id}`}
                onClick={() => onStep(item.id)}
              >
                {mode === 'guided' ? (
                  <span className="ill-sd__step-number sd-rail__number">
                    {state.status === 'done' && !current ? <CheckMark size={14} aria-hidden /> : position + 1}
                  </span>
                ) : null}
                <span className="sd-rail__name">{item.label}</span>
                {state.errors || state.warnings ? (
                  <span className="sd-rail__state" aria-hidden>
                    <SeverityIcon severity={state.errors ? 'error' : 'warning'} size={14} />
                    {state.errors || state.warnings}
                  </span>
                ) : null}
              </button>
              <span id={`sd-rail-state-${item.id}`} className="sd-sr-only">
                {stepStateLabel(state)}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
