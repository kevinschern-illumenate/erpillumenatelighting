import { severityCounts, type Check, type Severity } from './open';

const LABELS: Record<Severity, string> = { error: 'Errors', warning: 'Warnings', info: 'Notes' };
const ICONS: Record<Severity, string> = { error: '✖', warning: '▲', info: 'ℹ' };

/** Right-hand check panel (plan H9): severity counts, then each check; collapses to the counts. */
export function CheckPanel({ checks, open, onToggle }: { checks: Check[]; open: boolean; onToggle(): void }) {
  const counts = severityCounts(checks);
  return (
    <aside className={`ill-sd__checks${open ? '' : ' ill-sd__checks--closed'}`} aria-label="Checks">
      <button type="button" className="ill-sd__checks-toggle" aria-expanded={open} onClick={onToggle}>
        Checks
        {(Object.keys(LABELS) as Severity[]).map((severity) => (
          <span key={severity} className={`ill-sd__count ill-sd__count--${severity}`} title={LABELS[severity]}>
            <span aria-hidden="true">{ICONS[severity]}</span> {counts[severity]}
            <span className="ill-sd__sr"> {LABELS[severity].toLowerCase()}</span>
          </span>
        ))}
      </button>
      {open ? (
        checks.length ? (
          <ul className="ill-sd__check-list">
            {checks.map((check) => (
              <li key={check.id} className={`ill-sd__check ill-sd__check--${check.severity}`}>
                <span aria-hidden="true">{ICONS[check.severity]}</span>
                <div>
                  <strong>{check.title}</strong>
                  <p>{check.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ill-sd__muted">No issues found so far.</p>
        )
      ) : null}
    </aside>
  );
}
