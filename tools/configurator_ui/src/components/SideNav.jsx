import { AlertTriangle } from 'lucide-react';

/**
 * Vertical sticky sidebar navigation — desktop counterpart to the horizontal
 * ProgressBar used on mobile.
 *
 * Bubbles are coloured by state:
 *   broken   → red with warning icon, always clickable
 *   current  → outlined accent border, not clickable (you're already here)
 *   answered → filled accent, clickable (scroll back)
 *   revealed but optional/unanswered → soft accent tint, clickable
 *   unrevealed → very soft/muted, disabled
 *
 * @param {object}   props
 * @param {Array}    props.steps          { id, shortLabel }[] for every visible question.
 * @param {number}   props.currentIndex   Index of the last revealed (active) step.
 * @param {number}   props.revealedCount  How many steps have been revealed so far.
 * @param {Set}      props.brokenSet      Indices whose stored answer is no longer valid.
 * @param {Function} props.onJump         (id: string) => void  — scroll-to callback.
 */
export default function SideNav({ steps, currentIndex, revealedCount, brokenSet, onJump }) {
  return (
    <nav aria-label="Configuration progress">
      <ol className="flex flex-col gap-3 py-1">
        {steps.map((step, i) => {
          const isRevealed = i < revealedCount;
          const isCurrent = i === currentIndex;
          const isBroken = brokenSet.has(i);
          const isAnsweredPast = isRevealed && i < currentIndex;
          const isClickable = (isRevealed || isBroken) && !isCurrent;

          let bubbleClass;
          if (isBroken) {
            bubbleClass =
              'bg-red-500 text-white ring-2 ring-red-300 ring-offset-1 hover:bg-red-600 cursor-pointer';
          } else if (isCurrent) {
            bubbleClass =
              'bg-white border-2 border-ill-accent text-ill-accent cursor-default';
          } else if (isAnsweredPast) {
            bubbleClass =
              'bg-ill-accent text-white hover:opacity-80 cursor-pointer';
          } else if (isRevealed) {
            // Revealed optional/unanswered step
            bubbleClass =
              'bg-ill-accentSoft text-ill-subtle hover:opacity-80 cursor-pointer';
          } else {
            bubbleClass =
              'bg-ill-accentSoft text-ill-subtle opacity-40 cursor-not-allowed';
          }

          return (
            <li key={step.id} className="group relative flex-none">
              <button
                type="button"
                aria-label={`Step ${i + 1}: ${step.shortLabel}${isBroken ? ' — needs attention' : ''}${isCurrent ? ' (current)' : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
                disabled={!isClickable}
                onClick={() => isClickable && onJump(step.id)}
                className={[
                  'flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-semibold',
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

              {/* Tooltip to the right */}
              <div
                role="tooltip"
                className="pointer-events-none absolute left-full top-1/2 z-20 ml-2 -translate-y-1/2 opacity-0 transition-opacity duration-150 group-hover:opacity-100"
              >
                <div className="flex items-center gap-0">
                  {/* Left-pointing arrow */}
                  <div className="h-0 w-0 border-b-[5px] border-r-[5px] border-t-[5px] border-b-transparent border-t-transparent border-r-gray-900" />
                  <div className="whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white shadow-lg">
                    {step.shortLabel}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
