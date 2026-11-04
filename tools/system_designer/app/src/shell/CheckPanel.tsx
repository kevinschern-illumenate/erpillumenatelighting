import { ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useState } from 'react';
import { Button, EmptyState, SeverityIcon } from '../ui';
import { severityCounts, type Check, type Severity } from './open';

const LABELS: Record<Severity, string> = { error: 'errors', warning: 'warnings', info: 'notes' };
const ORDER: Severity[] = ['error', 'warning', 'info'];
type Filter = Severity | 'all';

/**
 * The right-hand panel (plan H9, SD-1.3): the severity counts, then each check with "Go to" (SD-2.2).
 * Collapsed, it keeps the counts so the state of the design is never hidden.
 */
export function CheckPanel({
  checks,
  open,
  onToggle,
  onGoTo,
}: {
  checks: Check[];
  open: boolean;
  onToggle(): void;
  onGoTo?(check: Check): void;
}) {
  const counts = severityCounts(checks);
  const [filter, setFilter] = useState<Filter>('all');
  const shown = [...checks]
    .filter((check) => filter === 'all' || check.severity === filter)
    .sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));
  return (
    <aside className={`sd-panel ill-sd__checks${open ? '' : ' sd-panel--closed'}`} aria-label="Checks">
      <button
        type="button"
        className="sd-panel__toggle ill-sd__checks-toggle"
        aria-expanded={open}
        aria-controls="sd-check-list"
        onClick={onToggle}
      >
        <span className="sd-panel__title">Checks</span>
        {ORDER.map((severity) => (
          <span key={severity} className={`sd-panel__count sd-panel__count--${severity}`}>
            <SeverityIcon severity={severity} size={14} />
            {counts[severity]}
            <span className="sd-sr-only"> {LABELS[severity]}</span>
          </span>
        ))}
        <span className="sd-panel__chevron" aria-hidden>
          {open ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        </span>
      </button>
      {open ? (
        <div className="sd-panel__body" id="sd-check-list">
          {checks.length ? (
            <>
              <div className="sd-panel__filters" role="group" aria-label="Show">
                {(['all', ...ORDER] as Filter[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="sd-chip-toggle"
                    aria-pressed={filter === value}
                    onClick={() => setFilter(value)}
                  >
                    {value === 'all' ? 'All' : `${LABELS[value][0]!.toUpperCase()}${LABELS[value].slice(1)}`}
                  </button>
                ))}
              </div>
              <ul className="sd-panel__list">
                {shown.map((check) => (
                  <li key={check.id} className={`sd-check sd-check--${check.severity} ill-sd__check`}>
                    <SeverityIcon severity={check.severity} label />
                    <div className="sd-check__text">
                      <strong>{check.title}</strong>
                      <p>{check.detail}</p>
                      {onGoTo ? (
                        <Button variant="quiet" size="sm" className="sd-check__go" onClick={() => onGoTo(check)}>
                          Go to<span className="sd-sr-only"> {check.title}</span>
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
              {!shown.length ? <p className="ill-sd__muted">Nothing in this group.</p> : null}
            </>
          ) : (
            <EmptyState title="No issues found so far">The checks update as you edit.</EmptyState>
          )}
        </div>
      ) : null}
    </aside>
  );
}
