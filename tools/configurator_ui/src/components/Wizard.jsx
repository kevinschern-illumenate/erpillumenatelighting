import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-react';
import ProgressBar from './ProgressBar.jsx';
import QuestionStep from './QuestionStep.jsx';
import Results from './Results.jsx';
import {
  visibleQuestions, pruneHiddenAnswers, isAnswered, progress,
} from '../lib/engine.js';

/**
 * Wizard shell: drives navigation through the visible question set, handling
 * branching/skip via the engine, and renders the Results screen at the end.
 */
export default function Wizard() {
  const [answers, setAnswers] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [done, setDone] = useState(false);

  // Visible questions recompute on every answer change (branching/skip).
  const visible = useMemo(() => visibleQuestions(answers), [answers]);

  // Clamp the step index when the visible set shrinks (e.g. a branch closes).
  const safeIndex = Math.min(stepIndex, Math.max(0, visible.length - 1));
  const current = visible[safeIndex];

  const prog = progress(answers);

  const setAnswer = (id, value) => {
    setAnswers((prev) => {
      const next = { ...prev, [id]: value };
      // Drop answers for now-hidden questions so stale branches don't persist.
      return pruneHiddenAnswers(next);
    });
  };

  const canAdvance = current ? isAnswered(current, answers) : false;
  const isLast = safeIndex >= visible.length - 1;

  const goNext = () => {
    if (!canAdvance) return;
    if (isLast) setDone(true);
    else setStepIndex(safeIndex + 1);
  };
  const goBack = () => {
    if (done) {
      setDone(false);
      return;
    }
    setStepIndex(Math.max(0, safeIndex - 1));
  };
  const restart = () => {
    setAnswers({});
    setStepIndex(0);
    setDone(false);
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6 flex items-center gap-2">
        <Sparkles size={22} className="text-ill-accent" aria-hidden="true" />
        <h1 className="font-display text-xl font-semibold text-ill-ink">
          ilLumenate Product Configurator
        </h1>
      </header>

      <div className="rounded-2xl border border-ill-border bg-ill-bg p-5 shadow-sm sm:p-7">
        {done ? (
          <Results answers={answers} onRestart={restart} />
        ) : (
          <>
            <ProgressBar
              current={safeIndex + 1}
              total={visible.length}
              percent={prog.percent}
            />

            {current && (
              <QuestionStep
                key={current.id}
                question={current}
                answers={answers}
                onChange={(value) => setAnswer(current.id, value)}
              />
            )}

            <div className="mt-8 flex items-center justify-between">
              <button
                type="button"
                onClick={goBack}
                disabled={safeIndex === 0}
                className="inline-flex items-center gap-1.5 rounded-lg border border-ill-borderStr bg-ill-paper px-4 py-2 font-medium text-ill-ink outline-none transition hover:border-ill-accent focus-visible:ring-2 focus-visible:ring-ill-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft size={16} aria-hidden="true" /> Back
              </button>

              <button
                type="button"
                onClick={goNext}
                disabled={!canAdvance}
                className="inline-flex items-center gap-1.5 rounded-lg bg-ill-accent px-5 py-2 font-medium text-white outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isLast ? 'See recommendations' : 'Next'}
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </>
        )}
      </div>

      <p className="mt-4 text-center text-xs text-ill-subtle">
        Prototype using seeded offline data from real ERP attribute names. No live ERP calls.
      </p>
    </div>
  );
}
