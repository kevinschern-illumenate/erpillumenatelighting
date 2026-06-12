// resultObject.js
// Builds the downstream-ready result object (takeoff / spec-submittal / schedule).
// Pure functions.

import { lumensBandFor, visibleQuestions } from './engine.js';
import { recommend, competitorRecommendations, computePower } from './recommend.js';

/**
 * Assemble the canonical result object from the user's answers.
 *
 * @param {object} answers
 * @param {object} [opts]
 * @param {string} [opts.intendedFor] one of takeoff|spec-submittal|fixture-schedule
 * @returns {object}
 */
export function buildResultObject(answers, opts = {}) {
  const { recommendations, relaxed, relaxedLabels } = recommend(answers);
  const competitors = competitorRecommendations(answers);

  // Derive power needs against the top recommendation (if any).
  const topAttrs = recommendations[0] ? recommendations[0].attributes : null;
  const power = computePower(answers, topAttrs);
  const band = lumensBandFor(answers.fixture_purpose);

  // Only persist answers for questions that are currently visible.
  const visibleIds = new Set(visibleQuestions(answers).map((q) => q.id));
  const cleanAnswers = {};
  for (const [k, v] of Object.entries(answers)) {
    if (visibleIds.has(k)) cleanAnswers[k] = v;
  }

  return {
    answers: cleanAnswers,
    derived: {
      lumens_target_band: band ? band.label : null,
      needs_power_injection: power.applicable ? power.needs_power_injection : null,
      supply_count_estimate: power.applicable ? power.supply_count_estimate : null,
      total_watts: power.applicable ? power.total_watts : null,
      relaxed_criteria: relaxedLabels,
    },
    recommendations: recommendations.map((r) => ({
      sku: r.sku,
      family: r.family,
      brand: r.brand,
      attributes: r.attributes,
      score: r.score,
      tradeoffs: r.tradeoffs,
    })),
    competitors: competitors.map((c) => ({
      sku: c.sku,
      family: c.family,
      brand: c.brand,
      attributes: c.attributes,
      score: c.score,
      tradeoffs: c.tradeoffs,
    })),
    meta: {
      version: '1.0',
      generatedAt: new Date().toISOString(),
      intendedFor: opts.intendedFor || 'takeoff',
      relaxed,
      source: 'ilLumenate configurator prototype (seeded offline data)',
    },
  };
}

/** Trigger a browser download of the result object as pretty JSON. */
export function downloadResultObject(resultObject, filename = 'ill-configurator-result.json') {
  const blob = new Blob([JSON.stringify(resultObject, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
