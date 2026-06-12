// engine.js
// Branching, skip logic, and step visibility for the wizard.
// Pure functions only -- no React, no DOM. Driven entirely by questions.json.

import questionsData from '../content/questions.json';

export const QUESTIONS = questionsData.questions;
export const LUMENS_BANDS = questionsData.lumensBands;

/**
 * Evaluate a single condition clause against the current answers.
 * Supported operators: eq, ne, in, gt, gte, lt, lte, exists.
 */
function testClause(clause, answers) {
  const value = answers[clause.q];
  if ('eq' in clause) return value === clause.eq;
  if ('ne' in clause) return value !== clause.ne;
  if ('in' in clause) return Array.isArray(clause.in) && clause.in.includes(value);
  if ('exists' in clause) {
    const has = value !== undefined && value !== null && value !== '';
    return clause.exists ? has : !has;
  }
  const num = Number(value);
  if ('gt' in clause) return Number.isFinite(num) && num > clause.gt;
  if ('gte' in clause) return Number.isFinite(num) && num >= clause.gte;
  if ('lt' in clause) return Number.isFinite(num) && num < clause.lt;
  if ('lte' in clause) return Number.isFinite(num) && num <= clause.lte;
  return false;
}

/**
 * Evaluate a condition group: { all: [...] } and/or { any: [...] }.
 * Undefined/empty group => true (no constraint).
 */
export function evalCondition(group, answers) {
  if (!group) return true;
  let result = true;
  if (Array.isArray(group.all)) {
    result = result && group.all.every((c) => testClause(c, answers));
  }
  if (Array.isArray(group.any)) {
    result = result && group.any.some((c) => testClause(c, answers));
  }
  return result;
}

/**
 * Is a question visible given current answers?
 * Visible when visibleWhen passes (or absent) AND skipWhen does not pass.
 */
export function isQuestionVisible(question, answers) {
  if (question.visibleWhen && !evalCondition(question.visibleWhen, answers)) {
    return false;
  }
  if (question.skipWhen && evalCondition(question.skipWhen, answers)) {
    return false;
  }
  return true;
}

/** The ordered list of currently-visible questions. */
export function visibleQuestions(answers) {
  return QUESTIONS.filter((q) => isQuestionVisible(q, answers));
}

/**
 * Visible options for a question (option-level visibleWhen / hideWhen).
 * Lets e.g. addressable-pixel runs hide non-DMX/SPI protocols.
 */
export function visibleOptions(question, answers) {
  if (!Array.isArray(question.options)) return [];
  return question.options.filter((opt) => {
    if (opt.visibleWhen && !evalCondition(opt.visibleWhen, answers)) return false;
    if (opt.hideWhen && evalCondition(opt.hideWhen, answers)) return false;
    return true;
  });
}

/** Has this question been answered acceptably? Optional questions are always OK. */
export function isAnswered(question, answers) {
  if (question.type === 'info') return true;
  const value = answers[question.id];
  if (!question.required) return true;
  if (question.type === 'range') {
    return value && Number.isFinite(Number(value.low)) && Number.isFinite(Number(value.high));
  }
  if (question.type === 'number') {
    return value !== undefined && value !== null && value !== '' && Number.isFinite(Number(value));
  }
  return value !== undefined && value !== null && value !== '';
}

/**
 * Remove answers for questions that are no longer visible, so stale branches
 * (e.g. an IP rating chosen then switched to Dry) don't leak into results.
 */
export function pruneHiddenAnswers(answers) {
  const next = { ...answers };
  for (const q of QUESTIONS) {
    if (!isQuestionVisible(q, next) && q.id in next) {
      delete next[q.id];
    }
  }
  return next;
}

/** Progress: how many visible questions are answered, out of the total visible. */
export function progress(answers) {
  const visible = visibleQuestions(answers);
  const answered = visible.filter((q) => q.type !== 'info' && isAnswered(q, answers) && answers[q.id] !== undefined).length;
  const required = visible.filter((q) => q.type !== 'info');
  return {
    total: required.length,
    answered,
    percent: required.length ? Math.round((answered / required.length) * 100) : 0,
  };
}

/** Look up the lumens band definition for a fixture purpose value. */
export function lumensBandFor(purpose) {
  return purpose ? LUMENS_BANDS[purpose] || null : null;
}
