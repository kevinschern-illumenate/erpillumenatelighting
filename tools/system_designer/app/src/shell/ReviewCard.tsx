import { useState } from 'react';
import { useStore } from 'zustand';
import type { DesignApi } from '../design/api';
import type { CheckState } from '../design/engine';
import type { DesignStore } from '../design/store';
import type { OpenDesign } from './open';

const PRIORITIES = ['Normal', 'High', 'Rush'] as const;

/** Open errors and warnings: checks an Applications Engineer overrode or the dealer accepted don't count. */
export function openIssues(engine: CheckState) {
  if (engine.state !== 'ready') return null;
  const open = engine.check.messages.filter((item) => !item.override);
  return {
    errors: open.filter((item) => item.severity === 'error').length,
    warnings: open.filter((item) => item.severity === 'warning').length,
  };
}

/** Request an ilLumenate review of the saved revision (plan §14.2, WP-4.2). */
export function ReviewCard({
  open,
  store,
  engine,
  api,
}: {
  open: OpenDesign;
  store: DesignStore;
  engine: CheckState;
  api: DesignApi;
}) {
  const design = useStore(store, (s) => s.design);
  const meta = useStore(store, (s) => s.meta);
  const dirty = useStore(store, (s) => s.dirty);
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]>('Normal');
  const [dueDate, setDueDate] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const issues = engine.state === 'ready' && engine.design === design ? openIssues(engine) : null;
  const requirement = open.review_requirement;
  const status = meta?.status;
  const canRequest =
    open.permissions.can_edit && !open.schedule.is_locked && (status === 'Draft' || status === 'Changes Requested');
  const blocker = !meta
    ? 'Save the design first.'
    : dirty
      ? 'Save your changes first.'
      : !issues
        ? 'Running the checks…'
        : issues.errors
          ? `Fix ${issues.errors === 1 ? 'the error' : `the ${issues.errors} errors`} on the Check step first.`
          : null;

  async function send() {
    if (!meta || !issues) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.requestReview({
        design: meta.name,
        priority,
        dueDate,
        note,
        errorCount: issues.errors,
        warningCount: issues.warnings,
      });
      store.setState({ meta: result.design_meta });
      setNotice(
        result.reviewer
          ? `Review requested. ${result.reviewer} will review revision ${result.design_meta.revision}.`
          : `Review requested. ilLumenate will assign an Applications Engineer to revision ${result.design_meta.revision}.`,
      );
      setNote('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The review could not be requested');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ill-sd__card" data-testid="review-card">
      <h3>ilLumenate review</h3>
      <p data-testid="review-requirement">
        {requirement.required
          ? `Review is required before this schedule can be ordered: ${requirement.reasons.map((reason) => reason.detail ?? reason.code).join(', ')}.`
          : 'Review is optional for this schedule. An Applications Engineer can still check the design.'}
      </p>
      {status === 'In Review' ? (
        <p className="ill-sd__callout" data-testid="review-status">
          Revision {meta?.revision} is with ilLumenate for review. It is read-only until the review is done.
        </p>
      ) : status === 'Approved' ? (
        <p className="ill-sd__callout" data-testid="review-status">
          Revision {meta?.revision} was approved{meta?.approved_by ? ` by ${meta.approved_by}` : ''}. Drawings can carry
          the REVIEWED BY ILLUMENATE stamp.
        </p>
      ) : status === 'Changes Requested' ? (
        <p className="ill-sd__callout ill-sd__callout--warn" data-testid="review-status">
          ilLumenate asked for changes. Make them, save, and send the design back for review.
        </p>
      ) : null}
      {canRequest ? (
        <>
          <div className="ill-sd__row">
            <label className="ill-sd__pick">
              <span>Priority</span>
              <select value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
                {PRIORITIES.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="ill-sd__pick">
              <span>Needed by (optional)</span>
              <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
            </label>
          </div>
          <label className="ill-sd__pick">
            <span>Note for the reviewer (optional)</span>
            <textarea value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} />
          </label>
          {blocker ? (
            <p className="ill-sd__muted" role="status">
              {blocker}
            </p>
          ) : null}
          <button
            type="button"
            className="ill-sd__button"
            disabled={Boolean(blocker) || busy}
            onClick={() => void send()}
          >
            {status === 'Changes Requested' ? 'Send back for review' : 'Request review'}
          </button>
        </>
      ) : null}
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="ill-sd__muted" role="status" data-testid="review-notice">
          {notice}
        </p>
      ) : null}
    </div>
  );
}
