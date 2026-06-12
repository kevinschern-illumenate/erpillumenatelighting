/**
 * Wizard progress bar.
 *
 * @param {object} props
 * @param {number} props.current  1-based index of the current visible step.
 * @param {number} props.total    Total visible steps.
 * @param {number} props.percent  Percent answered (0..100).
 */
export default function ProgressBar({ current, total, percent }) {
  return (
    <div className="mb-6">
      <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-ill-muted">
        <span>
          Step {current} of {total}
        </span>
        <span>{percent}% complete</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-ill-accentSoft"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Configuration progress"
      >
        <div
          className="h-full rounded-full bg-ill-accent transition-all duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
