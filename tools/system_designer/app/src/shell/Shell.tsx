import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'zustand';
import { PRODUCT_NAME } from '../product';
import type { DesignApi, VerifyResult } from '../design/api';
import type { DraftStore } from '../design/drafts';
import { saveDesign, type DesignStore, type SaveStatus } from '../design/store';
import { CheckPanel } from './CheckPanel';
import { PowerStep } from './PowerStep';
import { RunsStep } from './RunsStep';
import { SpacesStep } from './SpacesStep';
import { StartStep } from './StartStep';
import { TermsDialog } from './TermsDialog';
import { engineCheckItems, runCheckItems, type Check, type OpenDesign } from './open';
import { CheckStep } from './CheckStep';
import { ViewsStep } from './ViewsStep';
import { useCatalog } from '../design/catalog';
import { useDesignCheck } from '../design/engine';
import { vdLimits } from '@ill/engine/designCheck';
import { verifySubset } from '@ill/engine/verify';
import { GRIDS_TAB, readOptIn, STEPS, writeOptIn, type Mode, type StepId } from './steps';

// The grids load AG Grid; only engineering mode pays for it.
const EngineeringTab = lazy(() => import('../engineering/EngineeringTab'));

const EDITABLE_STATUSES = new Set(['Draft', 'Changes Requested']);

export interface ShellProps {
  open: OpenDesign;
  store: DesignStore;
  api: DesignApi;
  drafts: DraftStore;
  checks: Check[];
  restoredDraft?: boolean;
  navigate?: (url: string) => void;
}

export const scheduleUrl = (schedule: string) => `/portal/schedules/${encodeURIComponent(schedule)}`;

/** Why the design cannot be edited here, or null when it can. */
export function readOnlyReason(open: OpenDesign, status: string | undefined): string | null {
  if (open.schedule.is_locked) return 'This schedule version is locked, so its design is read-only.';
  if (!open.permissions.can_edit)
    return 'You can view this design. Only people who can edit the schedule can change it.';
  if (status && !EDITABLE_STATUSES.has(status)) return `This revision is ${status.toLowerCase()} and read-only.`;
  return null;
}

export function reviewChip(open: OpenDesign, status: string | undefined) {
  if (status === 'Approved') return { label: 'Approved', tone: 'ok' };
  return open.review_requirement.required
    ? { label: 'Review required', tone: 'warn' }
    : { label: 'Review optional', tone: 'quiet' };
}

/** "Saved · 12:04" from Frappe's "2026-10-09 12:04:31.000001". */
export function saveLabel(status: SaveStatus, dirty: boolean, modified: string | undefined, message: string | null) {
  if (status === 'saving') return 'Saving…';
  if (status === 'conflict' || status === 'locked' || status === 'error') return message || 'Not saved';
  if (dirty) return 'Unsaved changes';
  const time = modified?.match(/\d{2}:\d{2}/)?.[0];
  return time ? `Saved · ${time}` : 'Not saved yet';
}

export function Shell({ open, store, api, drafts, checks, restoredDraft = false, navigate }: ShellProps) {
  const meta = useStore(store, (s) => s.meta);
  const design = useStore(store, (s) => s.design);
  const dirty = useStore(store, (s) => s.dirty);
  const saveStatus = useStore(store, (s) => s.saveStatus);
  const saveMessage = useStore(store, (s) => s.saveMessage);
  const termsAccepted = useStore(store, (s) => s.termsAccepted);
  const canUndo = useStore(store.temporal, (s) => s.pastStates.length > 0);
  const canRedo = useStore(store.temporal, (s) => s.futureStates.length > 0);
  const [step, setStep] = useState<StepId>('start');
  // Engineering mode is always there for ilLumenate staff; dealers turn it on (plan §7).
  const staff = Boolean(open.permissions.can_engineer || open.permissions.can_review);
  const [optIn, setOptIn] = useState(readOptIn);
  const engineeringAvailable = staff || optIn;
  const [mode, setModeState] = useState<Mode>(staff ? 'engineering' : 'guided');
  const setMode = (value: Mode) => {
    setModeState(value);
    if (value === 'guided' && step === GRIDS_TAB.id) setStep('start');
  };
  const chooseEngineering = (value: boolean) => {
    writeOptIn(value);
    setOptIn(value);
    setMode(value ? 'engineering' : 'guided');
  };
  const [checksOpen, setChecksOpen] = useState(true);
  const reconcile = useStore(store, (s) => s.reconcile);
  const reconciled = useStore(store, (s) => s.reconciled);
  const catalog = useCatalog(api, open.catalog_hash);
  const limits = useMemo(() => vdLimits(open.settings), [open.settings]);
  const engine = useDesignCheck(design, catalog.state === 'ready' ? catalog.catalog : null, open.lines, limits, {
    reviewRequired: open.review_requirement.required,
    outOfSync: Boolean(reconcile && !reconcile.in_sync && !reconciled),
  });
  const allChecks = useMemo(() => {
    if (!design) return checks;
    const runItems = runCheckItems(design, open.builds);
    const runChecked = new Set(runItems.map((item) => item.id.split(':').slice(1).join(':')));
    const engineItems = engine.state === 'ready' ? engineCheckItems(engine.check.messages, design, runChecked) : [];
    return [...checks, ...runItems, ...engineItems];
  }, [checks, design, open.builds, engine]);
  const readOnly = readOnlyReason(open, meta?.status);
  const review = reviewChip(open, meta?.status);
  const canSave = !readOnly && dirty && saveStatus !== 'saving';
  const [verification, setVerification] = useState<VerifyResult | null>(null);
  const latestCheck = useRef(engine);
  useEffect(() => {
    latestCheck.current = engine;
  }, [engine]);
  // Save, then ask the server to re-check the gating subset of what was saved (plan §18.2).
  const saveAndVerify = useCallback(async () => {
    const saving = store.getState().design;
    const result = await saveDesign(store, api, drafts);
    const check = latestCheck.current;
    if (!result || !saving || check.state !== 'ready' || check.design !== saving) return;
    try {
      setVerification(await api.verifyDesign(result.name, verifySubset(saving, check.check)));
    } catch {
      // The server check is advisory for the dealer; reviewers see it on the design.
    }
  }, [store, api, drafts]);
  const save = () => {
    if (canSave) void saveAndVerify();
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 's') {
        event.preventDefault();
        if (!readOnly && store.getState().dirty) void saveAndVerify();
      }
      // Leave undo inside text fields to the browser.
      const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement;
      if (readOnly || typing || (key !== 'z' && key !== 'y')) return;
      event.preventDefault();
      if (key === 'y' || event.shiftKey) store.temporal.getState().redo();
      else store.temporal.getState().undo();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [store, readOnly, saveAndVerify]);

  const index = STEPS.findIndex((item) => item.id === step);
  const current = STEPS[index] ?? GRIDS_TAB;
  const title = open.schedule.schedule_name || open.schedule.name;

  return (
    <div className={`ill-sd ill-sd--${mode}`} data-testid="system-designer">
      <header className="ill-sd__header">
        <div className="ill-sd__heading">
          <span className="ill-sd__brand">ilLumenate</span>
          <h1 className="ill-sd__title">{PRODUCT_NAME}</h1>
          <p className="ill-sd__subtitle" data-testid="schedule-name">
            <a href={scheduleUrl(open.schedule.name)}>{title}</a> · Version {open.schedule.version}
          </p>
        </div>
        <div className="ill-sd__chips">
          <span className="ill-sd__chip">{meta ? `Revision ${meta.revision}` : 'New design'}</span>
          {meta ? <span className="ill-sd__chip">{meta.status}</span> : null}
          <span className={`ill-sd__chip ill-sd__chip--${review.tone}`} data-testid="review-chip">
            {review.label}
          </span>
          <span className="ill-sd__save-state" role="status" data-testid="save-state">
            {saveLabel(saveStatus, dirty, meta?.modified, saveMessage)}
          </span>
          <button
            type="button"
            className="ill-sd__button ill-sd__button--quiet"
            disabled={Boolean(readOnly) || !canUndo}
            onClick={() => store.temporal.getState().undo()}
          >
            Undo
          </button>
          <button
            type="button"
            className="ill-sd__button ill-sd__button--quiet"
            disabled={Boolean(readOnly) || !canRedo}
            onClick={() => store.temporal.getState().redo()}
          >
            Redo
          </button>
          <button type="button" className="ill-sd__button" disabled={!canSave} onClick={save}>
            Save
          </button>
          {engineeringAvailable ? (
            <div className="ill-sd__toggle" role="group" aria-label="Mode">
              {(['guided', 'engineering'] as const).map((value) => (
                <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)}>
                  {value === 'guided' ? 'Guided' : 'Engineering'}
                </button>
              ))}
            </div>
          ) : null}
          {!staff ? (
            <label className="ill-sd__pick">
              <input type="checkbox" checked={optIn} onChange={(event) => chooseEngineering(event.target.checked)} />
              <span>Engineering tools</span>
            </label>
          ) : null}
          <details className="ill-sd__help">
            <summary>Help</summary>
            <p>
              Work through the steps from Start to Finish. Your changes are kept in this browser until you save; Ctrl+S
              saves. Questions? Contact your ilLumenate representative.
            </p>
          </details>
        </div>
      </header>
      {readOnly ? (
        <p className="ill-sd__banner" role="note">
          {readOnly}
        </p>
      ) : null}
      {verification && !verification.ok ? (
        <p className="ill-sd__banner" role="note" data-testid="verify-banner">
          ilLumenate's server check disagrees with{' '}
          {verification.mismatches.length === 1 ? 'one result' : `${verification.mismatches.length} results`} in this
          design. Your reviewer will see the difference; contact your ilLumenate representative if it persists.
        </p>
      ) : null}
      {restoredDraft ? (
        <p className="ill-sd__banner ill-sd__banner--info" role="note">
          Unsaved changes from your last visit were restored.
        </p>
      ) : null}
      <div className="ill-sd__layout">
        <nav className="ill-sd__nav" aria-label={mode === 'guided' ? 'Design steps' : 'Design tabs'}>
          <ol>
            {(mode === 'engineering' ? [...STEPS, GRIDS_TAB] : STEPS).map((item, position) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-current={item.id === step ? 'step' : undefined}
                  onClick={() => setStep(item.id)}
                >
                  {mode === 'guided' ? <span className="ill-sd__step-number">{position + 1}</span> : null}
                  {item.label}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <main className="ill-sd__main">
          {step === 'start' ? (
            <StartStep open={open} store={store} api={api} readOnly={Boolean(readOnly)} navigate={navigate} />
          ) : step === 'spaces' ? (
            <SpacesStep open={open} store={store} readOnly={Boolean(readOnly)} />
          ) : step === 'runs' ? (
            <RunsStep open={open} store={store} readOnly={Boolean(readOnly)} />
          ) : step === 'power' ? (
            <PowerStep open={open} store={store} api={api} catalog={catalog} readOnly={Boolean(readOnly)} />
          ) : step === 'check' ? (
            <CheckStep
              open={open}
              store={store}
              engine={engine}
              catalog={catalog}
              limits={limits}
              readOnly={Boolean(readOnly)}
              goTo={setStep}
            />
          ) : step === GRIDS_TAB.id ? (
            <Suspense fallback={<p className="ill-sd__muted">Loading the grids…</p>}>
              <EngineeringTab
                store={store}
                engine={engine}
                catalog={catalog}
                readOnly={Boolean(readOnly)}
                staff={staff}
              />
            </Suspense>
          ) : step === 'views' ? (
            <ViewsStep open={open} store={store} engine={engine} api={api} />
          ) : (
            <section aria-labelledby="ill-sd-step-title">
              <h2 id="ill-sd-step-title">{current.label}</h2>
              <p>{current.summary}</p>
              <p className="ill-sd__muted">This step opens in an upcoming update of the System Designer.</p>
            </section>
          )}
          {mode === 'guided' ? (
            <div className="ill-sd__actions">
              <button
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                disabled={index === 0}
                onClick={() => setStep(STEPS[index - 1]!.id)}
              >
                Back
              </button>
              <button
                type="button"
                className="ill-sd__button"
                disabled={index === STEPS.length - 1}
                onClick={() => setStep(STEPS[index + 1]!.id)}
              >
                Continue
              </button>
            </div>
          ) : null}
        </main>
        <CheckPanel checks={allChecks} open={checksOpen} onToggle={() => setChecksOpen((value) => !value)} />
      </div>
      {!readOnly && !termsAccepted ? (
        <TermsDialog
          text={String(open.settings.terms_text || '')}
          scheduleUrl={scheduleUrl(open.schedule.name)}
          onAccept={() => store.getState().acceptTerms()}
        />
      ) : null}
    </div>
  );
}
