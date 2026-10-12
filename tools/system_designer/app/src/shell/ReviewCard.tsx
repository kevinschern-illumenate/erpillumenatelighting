import { useState } from 'react';
import { useStore } from 'zustand';
import type { Design } from '@ill/core-schemas/design';
import type { DesignApi, ReviewDecision, ReviewRequirement } from '../design/api';
import type { CheckState } from '../design/engine';
import type { DesignStore } from '../design/store';
import type { OpenDesign } from './open';
import { designUrl } from './StartStep';

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

/** The errors still open on the design, which an Applications Engineer approves past only with an override. */
export function openErrors(engine: CheckState) {
  if (engine.state !== 'ready') return [];
  return engine.check.messages.filter((item) => item.severity === 'error' && !item.override);
}

/** Request an ilLumenate review of the saved revision (plan §14.2, WP-4.2); reviewers decide on it here (WP-4.3). */
export function ReviewCard({
  open,
  store,
  engine,
  api,
  navigate = (url: string) => window.location.assign(url),
}: {
  open: OpenDesign;
  store: DesignStore;
  engine: CheckState;
  api: DesignApi;
  navigate?: (url: string) => void;
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
  const [requirement, setRequirement] = useState<ReviewRequirement>(open.review_requirement);
  const status = meta?.status;
  const reviewing = open.permissions.can_review && status === 'In Review' && Boolean(meta?.is_current);
  const canRevise = open.permissions.can_edit && !open.schedule.is_locked && status === 'Approved' && meta?.is_current;
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

  async function startRevision() {
    if (!meta) return;
    setBusy(true);
    setError('');
    try {
      await api.createRevision(meta.name, `Started after revision ${meta.revision} was approved`);
      navigate(designUrl(open.schedule.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The next revision could not be started');
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
      {requirement.required && requirement.satisfied ? (
        <p className="ill-sd__muted" data-testid="review-gate">
          {requirement.override
            ? `Ordering is allowed without a review: ${requirement.override.by} overrode it ("${requirement.override.reason}"). A change to the schedule's lines needs a new review or override.`
            : 'Ordering is allowed: the approved design matches the schedule.'}
        </p>
      ) : requirement.required && meta?.status === 'Approved' ? (
        <p className="ill-sd__callout ill-sd__callout--warn" data-testid="review-gate">
          The schedule changed after this revision was approved, so it needs a new review before it can be ordered.
        </p>
      ) : null}
      {requirement.required && !requirement.satisfied && open.permissions.can_review ? (
        <GateOverride
          schedule={open.schedule.name}
          api={api}
          onDone={(next) => {
            setRequirement(next);
            setNotice('This schedule can now be ordered without a review.');
          }}
        />
      ) : null}
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
      {reviewing && meta ? (
        <ReviewerPanel store={store} engine={engine} api={api} design={meta.name} onDecided={setNotice} />
      ) : null}
      {canRevise ? (
        <button
          type="button"
          className="ill-sd__button ill-sd__button--quiet"
          disabled={busy}
          onClick={() => void startRevision()}
        >
          Start the next revision
        </button>
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

/** Reviewer mode (plan §11.5, WP-4.3): override errors with a reason, then approve or ask for changes. */
function ReviewerPanel({
  store,
  engine,
  api,
  design,
  onDecided,
}: {
  store: DesignStore;
  engine: CheckState;
  api: DesignApi;
  design: string;
  /** The panel closes once the revision leaves review, so the card shows the outcome. */
  onDecided(message: string): void;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const errors = openErrors(engine);
  const key = (item: { code: string; entityRef: string }) => `${item.code}:${item.entityRef}`;

  async function override(code: string, entityRef: string) {
    const reason = (reasons[`${code}:${entityRef}`] ?? '').trim();
    setBusy(true);
    setError('');
    try {
      const result = await api.overrideCheck({ design, code, entityRef, reason });
      const current = store.getState().design;
      // The server stored the override and a new build hash; the open design takes both without becoming dirty.
      if (current) store.setState({ design: { ...current, overrides: result.overrides } as Design });
      store.setState({ meta: result.design_meta, dirty: false });
      setNotice(`Overrode ${code} on ${entityRef}. Draw and keep the riser again before you decide.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The check could not be overridden');
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: ReviewDecision) {
    setBusy(true);
    setError('');
    try {
      const result = await api.reviewDecide(design, decision, note.trim());
      onDecided(
        decision === 'Approved'
          ? `Revision ${result.design_meta.revision} is approved.`
          : 'Changes requested. The dealer can edit the design again.',
      );
      setNote('');
      store.setState({ meta: result.design_meta });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The decision could not be recorded');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="reviewer-panel">
      <h4>Your review</h4>
      <p className="ill-sd__muted">
        Approving publishes the riser PDF kept on this revision to the review request, so draw it on the Views step and
        download the PDF first.
      </p>
      {errors.length ? (
        <ul className="ill-sd__check-list" data-testid="reviewer-errors">
          {errors.map((item) => (
            <li key={key(item)} className="ill-sd__check ill-sd__check--error">
              <div>
                <p>
                  <strong>{item.entityRef}</strong>: {item.text}
                </p>
                <div className="ill-sd__row">
                  <input
                    aria-label={`Override reason for ${item.code} on ${item.entityRef}`}
                    placeholder="Why this is acceptable"
                    value={reasons[key(item)] ?? ''}
                    onChange={(event) => setReasons((current) => ({ ...current, [key(item)]: event.target.value }))}
                  />
                  <button
                    type="button"
                    className="ill-sd__button ill-sd__button--quiet"
                    disabled={busy || (reasons[key(item)] ?? '').trim().length < 3}
                    onClick={() => void override(item.code, item.entityRef)}
                  >
                    Override
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <label className="ill-sd__pick">
        <span>Note to the dealer (needed when you ask for changes)</span>
        <textarea
          aria-label="Review note"
          value={note}
          maxLength={2000}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      {errors.length ? (
        <p className="ill-sd__muted" role="status">
          Override or send back {errors.length === 1 ? 'the open error' : `the ${errors.length} open errors`} before you
          approve.
        </p>
      ) : null}
      <div className="ill-sd__row">
        <button
          type="button"
          className="ill-sd__button"
          disabled={busy || errors.length > 0 || engine.state !== 'ready'}
          onClick={() => void decide('Approved')}
        >
          Approve
        </button>
        <button
          type="button"
          className="ill-sd__button ill-sd__button--quiet"
          disabled={busy || !note.trim()}
          onClick={() => void decide('Changes Requested')}
        >
          Request changes
        </button>
      </div>
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="ill-sd__muted" role="status" data-testid="reviewer-notice">
          {notice}
        </p>
      ) : null}
    </div>
  );
}

/** Staff let a schedule's current lines be ordered without an approved design (H8.5, WP-4.4). */
function GateOverride({
  schedule,
  api,
  onDone,
}: {
  schedule: string;
  api: DesignApi;
  onDone(requirement: ReviewRequirement): void;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function send() {
    setBusy(true);
    setError('');
    try {
      onDone((await api.overrideReviewGate(schedule, reason.trim())).review_requirement);
      setReason('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The review could not be overridden');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ill-sd__row" data-testid="gate-override">
      <input
        aria-label="Reason to allow ordering without review"
        placeholder="Why this schedule can be ordered without review"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
      />
      <button
        type="button"
        className="ill-sd__button ill-sd__button--quiet"
        disabled={busy || reason.trim().length < 3}
        onClick={() => void send()}
      >
        Allow ordering without review
      </button>
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
