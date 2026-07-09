import { useMemo, useRef, useEffect, useState } from 'react';
import { ChevronRight, AlertTriangle } from 'lucide-react';
import ProgressBar from './ProgressBar.jsx';
import SideNav from './SideNav.jsx';
import QuestionStep from './QuestionStep.jsx';
import Results from './Results.jsx';
import {
  visibleQuestions, pruneHiddenAnswers, isAnswered, progress, isAnswerStillValid,
} from '../lib/engine.js';

/**
 * Compute how many questions to reveal in the scroll.
 * All questions up to and including the first unanswered required question are shown.
 * Once all required questions are answered, all are revealed.
 */
function computeRevealedCount(visible, answers) {
  for (let i = 0; i < visible.length; i++) {
    const q = visible[i];
    if (q.required && q.type !== 'info' && !isAnswered(q, answers)) {
      return i + 1;
    }
  }
  return visible.length;
}

/**
 * Continuous-scroll wizard: all answered questions stack up in a feed; each new
 * question appears after the previous one is answered. A sticky sidebar on
 * desktop (or top bar on mobile) lets the user jump to any revealed step.
 * Broken answers (no longer matching any fixture) are flagged inline.
 */
export default function Wizard() {
  const [answers, setAnswers] = useState({});
  const [showResults, setShowResults] = useState(false);

  const questionsRef = useRef({});
  const prevRevealedRef = useRef(0);

  // Visible questions recompute on every answer change (branching/skip).
  const visible = useMemo(() => visibleQuestions(answers), [answers]);

  // Derived: how many steps are currently shown in the scroll.
  const revealedCount = computeRevealedCount(visible, answers);

  // The "active" step is the last revealed one (the one the user should answer next).
  const currentIndex = revealedCount - 1;

  // All required visible questions have been answered.
  const isAllAnswered = revealedCount >= visible.length && visible.length > 0;

  const prog = progress(answers);

  // Which revealed steps have a stale answer (no longer matches any fixture).
  const brokenSet = useMemo(() => {
    const broken = new Set();
    visible.forEach((q, i) => {
      if (i === currentIndex) return; // don't flag the active question
      if (answers[q.id] === undefined) return;
      if (!isAnswerStillValid(q, answers)) broken.add(i);
    });
    return broken;
  }, [visible, answers, currentIndex]);

  // Auto-scroll to each newly revealed question.
  useEffect(() => {
    if (revealedCount > prevRevealedRef.current && revealedCount <= visible.length) {
      const newQ = visible[revealedCount - 1];
      if (newQ) {
        // Small delay so React has committed the new card to the DOM first.
        setTimeout(() => {
          questionsRef.current[newQ.id]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 50);
      }
    }
    prevRevealedRef.current = revealedCount;
  }, [revealedCount, visible]);

  const setAnswer = (id, value) => {
    setAnswers((prev) => {
      const next = { ...prev, [id]: value };
      // Drop answers for now-hidden questions so stale branches don't persist.
      return pruneHiddenAnswers(next);
    });
  };

  const scrollToQuestion = (id) => {
    questionsRef.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const restart = () => {
    setAnswers({});
    setShowResults(false);
    prevRevealedRef.current = 0;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const navSteps = visible.map((q) => ({ id: q.id, shortLabel: q.shortLabel ?? q.id }));

  return (
    <div className="min-h-screen bg-ill-bg">
      <div className="mx-auto max-w-4xl px-4 py-8">

        {/* Mobile: horizontal progress bar at the top */}
        <div className="mb-6 md:hidden">
          <ProgressBar
            steps={navSteps}
            currentIndex={currentIndex}
            maxReached={revealedCount - 1}
            percent={prog.percent}
            brokenSet={brokenSet}
            onJump={(i) => scrollToQuestion(visible[i]?.id)}
          />
        </div>

        <div className="md:flex md:gap-8">

          {/* Desktop: sticky sidebar that follows scroll */}
          <aside className="hidden md:block md:w-14 flex-none sticky top-8 self-start">
            <SideNav
              steps={navSteps}
              currentIndex={currentIndex}
              revealedCount={revealedCount}
              brokenSet={brokenSet}
              onJump={scrollToQuestion}
            />
          </aside>

          {/* Main content: scrollable question feed */}
          <main className="flex-1 min-w-0">
            {visible.slice(0, revealedCount).map((q, i) => {
              const isCurrent = i === currentIndex;
              const isBroken = brokenSet.has(i);

              return (
                <div
                  key={q.id}
                  ref={(el) => { questionsRef.current[q.id] = el; }}
                  className={[
                    'mb-6 rounded-2xl border bg-ill-paper p-5 shadow-sm sm:p-7 scroll-mt-8',
                    isBroken
                      ? 'border-red-300'
                      : isCurrent
                      ? 'border-ill-accent shadow-md'
                      : 'border-ill-border',
                  ].join(' ')}
                >
                  {/* Step number badge */}
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-ill-subtle">
                    Step {i + 1}
                  </div>

                  {/* Broken-answer warning banner */}
                  {isBroken && (
                    <div
                      role="alert"
                      className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                    >
                      <AlertTriangle size={16} className="mt-0.5 flex-none" aria-hidden="true" />
                      <span>
                        Your earlier answer here no longer matches any available fixture.
                        Please update your selection below.
                      </span>
                    </div>
                  )}

                  <QuestionStep
                    question={q}
                    answers={answers}
                    onChange={(value) => setAnswer(q.id, value)}
                  />
                </div>
              );
            })}

            {/* See recommendations — appears once all required questions are answered */}
            {isAllAnswered && !showResults && (
              <div className="mb-6 text-center">
                <button
                  type="button"
                  onClick={() => setShowResults(true)}
                  className="inline-flex items-center gap-2 rounded-lg bg-ill-accent px-6 py-3 font-semibold text-white outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-2"
                >
                  See recommendations
                  <ChevronRight size={18} aria-hidden="true" />
                </button>
              </div>
            )}

            {/* Results panel — renders inline below the questions */}
            {showResults && (
              <div className="rounded-2xl border border-ill-border bg-ill-paper p-5 shadow-sm sm:p-7">
                <Results answers={answers} onRestart={restart} />
              </div>
            )}
          </main>
        </div>

        <p className="mt-8 text-center text-xs text-ill-subtle">
          Prototype using seeded offline data from real ERP attribute names. No live ERP calls.
        </p>
      </div>
    </div>
  );
}
