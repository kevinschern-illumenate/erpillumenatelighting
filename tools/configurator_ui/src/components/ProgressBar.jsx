import { useId } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Wizard progress navigator.
 *
 * Renders a row of numbered step bubbles above a thin fill bar.
 * Answered past steps are clickable (jump navigation).
 * Broken steps (answered but no longer valid) are highlighted red and clickable.
 *
 * @param {object}   props
 * @param {Array}    props.steps          Ordered array of { id, shortLabel } for each visible question.
 * @param {number}   props.currentIndex   0-based index of the currently active step.
 * @param {number}   props.maxReached     0-based highest step index the user has navigated to.
 * @param {number}   props.percent        Overall completion percentage (0–100).
 * @param {Set}      props.brokenSet      Set of step indices whose stored answer is no longer valid.
 * @param {Function} props.onJump         Callback: (index: number) => void.
 */
export default function ProgressBar({ steps, currentIndex, maxReached, percent, brokenSet, onJump }) {
  const navId = useId();

  return (
    <nav aria-label="Configuration progress" aria-describedby={navId} className="mb-6">
      {/* ── Bubble row ─────────────────────────────────────────────────── */}
      <ol
        id={navId}
        className="flex flex-wrap items-center justify-center gap-1.5 pb-1"
      >
        {steps.map((step, i) => {
          const isCurrent = i === currentIndex;
          const isPast = i < currentIndex || (i > currentIndex && i <= maxReached);
          const isBroken = brokenSet.has(i);
          const isClickable = (isPast || isBroken) && !isCurrent;

          let bubbleClass = '';

          if (isBroken) {
            bubbleClass =
              'bg-red-500 text-white ring-2 ring-red-300 ring-offset-1 hover:bg-red-600 cursor-pointer';
          } else if (isCurrent) {
            bubbleClass =
              'bg-white border-2 border-ill-accent text-ill-accent cursor-default';
          } else if (isPast) {
            bubbleClass =
              'bg-ill-accent text-white hover:opacity-80 cursor-pointer';
          } else {
            bubbleClass =
              'bg-ill-accentSoft text-ill-subtle cursor-not-allowed';
          }

          return (
            <li key={step.id} className="relative flex-none group">
              <button
                type="button"
                aria-label={`Step ${i + 1}: ${step.shortLabel}${isBroken ? ' — needs attention' : ''}${isCurrent ? ' (current)' : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
                disabled={!isClickable}
                onClick={() => isClickable && onJump(i)}
                className={[
                  'flex h-7 min-w-[1.75rem] px-1.5 flex-none items-center justify-center rounded-full text-xs font-semibold',
                  'outline-none transition focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-1',
                  bubbleClass,
                ].join(' ')}
              >
                {isBroken ? (
                  <AlertTriangle size={13} aria-hidden="true" />
                ) : (
                  i + 1
                )}
              </button>
              {/* Hover tooltip */}
              <div
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
              >
                <div className="whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white shadow-lg">
                  {step.shortLabel}
                </div>
                <div className="mx-auto mt-0.5 h-0 w-0 border-l-[5px] border-r-[5px] border-t-[5px] border-l-transparent border-r-transparent border-t-gray-900" />
              </div>
            </li>
          );
        })}
      </ol>

      {/* ── Fill bar ───────────────────────────────────────────────────── */}
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Configuration progress"
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ill-accentSoft"
      >
        <div
          className="h-full rounded-full bg-ill-accent transition-all duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* ── Step label (visible text) ────────────────────────────────── */}
      <div className="mt-1.5 flex items-center justify-between text-xs font-medium text-ill-muted">
        <span>{steps[currentIndex]?.shortLabel ?? ''}</span>
        <span>{percent}% complete</span>
      </div>

      {/* ── Broken-step callout ─────────────────────────────────────── */}
      {brokenSet.size > 0 && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          <AlertTriangle size={14} className="mt-0.5 flex-none text-red-500" aria-hidden="true" />
          <span>
            {brokenSet.size === 1
              ? 'One earlier answer is no longer valid after your change. Click the red step to fix it.'
              : `${brokenSet.size} earlier answers are no longer valid after your change. Click the red steps to fix them.`}
          </span>
        </div>
      )}
    </nav>
  );
}
