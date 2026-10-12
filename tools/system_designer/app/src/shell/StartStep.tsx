import { useState } from 'react';
import { useStore } from 'zustand';
import { applyReconcile } from '@ill/engine/reconcile';
import { DesignApiError, type DesignApi } from '../design/api';
import type { DesignStore } from '../design/store';
import { expandOptions, type OpenDesign } from './open';

export const designUrl = (schedule: string) => `/portal/schedules/${encodeURIComponent(schedule)}/design`;

const REVIEW_REASONS: Record<string, string> = {
  DMX: 'The design uses DMX control.',
  PHASE_DIMMING: 'The design uses line-voltage (phase-cut) dimming.',
  LOAD_OVER_THRESHOLD: 'The connected load is over the review threshold',
};

export function reviewReasonText(reason: { code: string; detail?: string | null }) {
  const text = REVIEW_REASONS[reason.code] ?? reason.code;
  return reason.code === 'LOAD_OVER_THRESHOLD' && reason.detail ? `${text} (${reason.detail}).` : text;
}

function plural(count: number, one: string, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

export function StartStep({
  open,
  store,
  api,
  readOnly,
  navigate = (url: string) => window.location.assign(url),
}: {
  open: OpenDesign;
  store: DesignStore;
  api: DesignApi;
  readOnly: boolean;
  navigate?: (url: string) => void;
}) {
  const design = useStore(store, (s) => s.design);
  const meta = useStore(store, (s) => s.meta);
  const reconcile = useStore(store, (s) => s.reconcile);
  const [copyError, setCopyError] = useState('');
  const [copying, setCopying] = useState(false);
  const { readiness, review_requirement: review } = open;
  const spaces = design?.site.spaces.length ?? 0;
  const runs = design?.runs.length ?? 0;

  const applyChanges = () => {
    if (!design || !reconcile) return;
    const result = applyReconcile(design, open.lines, open.builds, reconcile, expandOptions(open));
    store.getState().acceptReconcile(result.design);
  };

  const copyForward = async () => {
    if (!meta || !open.newer_version) return;
    setCopying(true);
    setCopyError('');
    try {
      await api.copyDesignToVersion(meta.name, open.newer_version.name);
      navigate(designUrl(open.newer_version.name));
    } catch (error) {
      setCopyError(error instanceof DesignApiError ? error.message : 'The design could not be copied. Try again.');
    } finally {
      setCopying(false);
    }
  };

  return (
    <section aria-labelledby="ill-sd-start-title" className="ill-sd__start">
      <h2 id="ill-sd-start-title">Start</h2>
      {open.schedule.is_locked ? (
        <div className="ill-sd__callout" data-testid="locked">
          <p>To change this design, work on a newer version of the schedule.</p>
          {open.newer_version ? (
            <div className="ill-sd__actions ill-sd__actions--start">
              {meta ? (
                <button type="button" className="ill-sd__button" disabled={copying} onClick={() => void copyForward()}>
                  Design on version {open.newer_version.version}
                </button>
              ) : null}
              <a className="ill-sd__button ill-sd__button--quiet" href={designUrl(open.newer_version.name)}>
                Open version {open.newer_version.version}
              </a>
            </div>
          ) : (
            <a className="ill-sd__button" href={`/portal/schedules/${encodeURIComponent(open.schedule.name)}`}>
              Design on a new version
            </a>
          )}
          {copyError ? (
            <p role="alert" className="ill-sd__error">
              {copyError}
            </p>
          ) : null}
        </div>
      ) : null}
      {reconcile ? (
        <div className="ill-sd__callout ill-sd__callout--warn" data-testid="reconcile">
          <p>
            The schedule changed since this design was saved: {plural(reconcile.added.length, 'line')} added,{' '}
            {plural(reconcile.removed.length, 'line')} removed, {plural(reconcile.changed.length, 'line')} changed and{' '}
            {plural(reconcile.qty.length, 'quantity', 'quantities')} updated.
            {reconcile.removed.some((item) => item.assignments.length)
              ? ' Supply assignments on removed lines will be dropped.'
              : ''}
          </p>
          <button type="button" className="ill-sd__button" disabled={readOnly} onClick={applyChanges}>
            Apply schedule changes
          </button>
        </div>
      ) : null}
      {review.required ? (
        <div className="ill-sd__callout ill-sd__callout--warn" data-testid="review-banner">
          <p>
            <strong>ilLumenate must review this design before the order.</strong>
          </p>
          <ul>
            {review.reasons.map((reason) => (
              <li key={reason.code}>{reviewReasonText(reason)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p data-testid="design-size">
        This design has {plural(runs, 'run')} in {plural(spaces, 'space')} from{' '}
        {plural(readiness.ready.length, 'ready line')}.
      </p>
      <h3>Schedule readiness</h3>
      <ul className="ill-sd__readiness">
        <li>{plural(readiness.ready.length, 'line')} ready to design</li>
        {readiness.needs_data.length ? (
          <li>
            {plural(readiness.needs_data.length, 'line')} need dealer data (watts, voltage or dimming) on the schedule
          </li>
        ) : null}
        {readiness.unconfigured.length ? (
          <li>
            {plural(readiness.unconfigured.length, 'line')} not configured yet;{' '}
            <a href={`/portal/schedules/${encodeURIComponent(open.schedule.name)}`}>configure them on the schedule</a>
          </li>
        ) : null}
        {readiness.catalog_gaps.length ? (
          <li>{plural(readiness.catalog_gaps.length, 'product')} not in the design catalog yet</li>
        ) : null}
      </ul>
      <p className="ill-sd__muted">The check panel lists each line that needs attention.</p>
    </section>
  );
}
