// recommend.js
// Hard filtering, ranking, and no-match relaxation for product recommendations.
// Pure functions. Reads seeded offline JSON only -- no network.

import productsData from '../data/products.seed.json';
import competitorsData from '../data/competitors.sample.json';
import attributes from '../data/attributes.seed.json';
import { lumensBandFor } from './engine.js';

export const PRODUCTS = productsData.products;
export const COMPETITORS = competitorsData.competitors;

// Ordering used for "rating must meet or exceed requirement" comparisons.
const ENV_ORDER = { Dry: 0, Damp: 1, Wet: 2 };
const IP_ORDER = { IP65: 0, IP67: 1, IP68: 2 };

// Usable single-supply capacity assumption for power-injection math.
// Mirrors the ilL-Spec-Driver fields named in the implementation plan §4:
// max_wattage (96 W) * usable_load_factor (0.8).
const DRIVER_MAX_WATTAGE = 100;
const USABLE_LOAD_FACTOR = 0.8;
const USABLE_SUPPLY_W = DRIVER_MAX_WATTAGE * USABLE_LOAD_FACTOR;

// The "Ambient" lumens band is open-ended (max ~99999 in questions.json). When a
// band has no real upper bound we treat anything at/above this threshold as
// "unbounded" and score closeness against an assumed spread instead of a midpoint.
const LUMENS_UNBOUNDED_THRESHOLD = 9000;
const UNBOUNDED_BAND_SPREAD = 400;

function kelvinOf(cctValue) {
  if (!cctValue) return null;
  const match = attributes.cct.find((c) => c.label === cctValue || String(c.kelvin) === String(cctValue));
  if (match) return match.kelvin;
  const num = parseInt(String(cctValue), 10);
  return Number.isFinite(num) ? num : null;
}

function criMinFor(criValue) {
  const row = attributes.cri.find((c) => c.label === criValue);
  return row ? row.minimum_ra : criValue === '95+' ? 95 : 90;
}

/* ------------------------------------------------------------------ *
 * Hard filters: a product must satisfy ALL of these to be eligible.
 * ------------------------------------------------------------------ */
function hardFilterReasons(product, answers) {
  const reasons = [];

  // Environment rating: product must meet or exceed the required moisture level.
  if (answers.moisture) {
    const need = ENV_ORDER[answers.moisture];
    const have = ENV_ORDER[product.environment_rating];
    if (have === undefined || have < need) reasons.push(`needs ${answers.moisture} rating`);
  }

  // IP rating: product must meet or exceed the required ingress protection.
  if (answers.ip_rating) {
    const need = IP_ORDER[answers.ip_rating];
    const have = product.ip_rating ? IP_ORDER[product.ip_rating] : undefined;
    if (have === undefined || have < need) reasons.push(`needs ${answers.ip_rating}+`);
  }

  // Light type (inferred from led_package family).
  if (answers.light_type && product.light_type !== answers.light_type) {
    reasons.push(`not ${answers.light_type}`);
  }

  // Color mode for full-color products.
  if (answers.color_mode) {
    const modes = product.color_modes || [];
    if (!modes.includes(answers.color_mode)) reasons.push(`no ${answers.color_mode}`);
  }

  // Dimming protocol compatibility (tape/driver/controller must speak it).
  if (answers.dimming_protocol) {
    const protos = product.supported_dimming_protocols || [];
    if (!protos.includes(answers.dimming_protocol)) reasons.push(`no ${answers.dimming_protocol}`);
  }

  // Supply voltage must match the tape input voltage.
  // TEMP: supply_voltage question is skipped; default to '24VDC' until re-enabled.
  const effectiveVoltage = answers.supply_voltage ?? '24VDC';
  if (product.input_voltage !== effectiveVoltage) {
    reasons.push(`needs ${effectiveVoltage}`);
  }

  // Installation method -> profile family support.
  if (answers.installation_method) {
    const methods = product.mounting_methods || [];
    if (!methods.includes(answers.installation_method)) reasons.push(`no ${answers.installation_method} mount`);
  }

  return reasons;
}

/* ------------------------------------------------------------------ *
 * Soft constraints: relaxed in priority order when nothing matches.
 * Priority (drop first -> last): CRI -> CCT -> lumens band.
 * ------------------------------------------------------------------ */
function softChecks(product, answers) {
  const checks = {};

  // CRI
  if (answers.cri) {
    checks.cri = (product.cri_typical || 0) >= criMinFor(answers.cri);
  }

  // CCT (static / dim-to-warm: discrete; tunable: range coverage)
  const targetK = kelvinOf(answers.target_cct);
  if (targetK) {
    checks.cct = (product.cct_available || []).includes(targetK);
  } else if (answers.cct_range && answers.light_type === 'Tunable white') {
    const lo = Number(answers.cct_range.low);
    const hi = Number(answers.cct_range.high);
    const pLo = product.cct_tunable_min;
    const pHi = product.cct_tunable_max;
    checks.cct = pLo != null && pHi != null && pLo <= lo && pHi >= hi;
  }

  // Lumens band (configurator heuristic from fixture purpose)
  const band = lumensBandFor(answers.fixture_purpose);
  if (band) {
    const lpf = product.lumens_per_foot || 0;
    checks.lumens = lpf >= band.min && lpf <= band.max;
  }

  return checks;
}

const RELAX_ORDER = ['cri', 'cct', 'lumens'];
const RELAX_LABEL = {
  cri: 'CRI requirement',
  cct: 'exact CCT',
  lumens: 'brightness (lumens/ft) band',
};

/**
 * Score a candidate 0..100. Higher = better fit.
 * Rewards: closeness to lumens band, CCT match, CRI margin, run feasibility.
 */
function scoreProduct(product, answers) {
  let score = 50;
  const soft = softChecks(product, answers);

  // Lumens band closeness.
  const band = lumensBandFor(answers.fixture_purpose);
  if (band) {
    const lpf = product.lumens_per_foot || 0;
    if (soft.lumens) {
      score += 20;
    } else {
      const unbounded = band.max > LUMENS_UNBOUNDED_THRESHOLD;
      const mid = (band.min + (unbounded ? band.min + UNBOUNDED_BAND_SPREAD : band.max)) / 2;
      const spread = Math.max(150, unbounded ? UNBOUNDED_BAND_SPREAD : band.max - band.min);
      score += Math.max(-10, 15 - (Math.abs(lpf - mid) / spread) * 15);
    }
  }

  // CCT match.
  if ('cct' in soft) score += soft.cct ? 12 : -6;

  // CRI margin.
  if ('cri' in soft) score += soft.cri ? 10 : -8;

  // Run-length feasibility (fewer required supplies = better).
  const power = computePower(answers, product);
  if (power.applicable) {
    if (!power.needs_power_injection) score += 8;
    else score += Math.max(-6, 6 - power.supply_count_estimate);
  }

  return Math.max(0, Math.min(100, Math.round(score)));
}

/** Human-readable trade-offs (unmet soft constraints) for a candidate. */
function tradeoffsFor(product, answers) {
  const soft = softChecks(product, answers);
  const out = [];
  if (soft.cri === false) out.push(`CRI below requested ${answers.cri}`);
  if (soft.cct === false) out.push('CCT differs from request');
  if (soft.lumens === false) {
    const band = lumensBandFor(answers.fixture_purpose);
    out.push(`${product.lumens_per_foot} lm/ft outside ${band ? band.label : 'target band'}`);
  }
  // Diffuser / finish are informational trade-offs (not hard filters).
  if (answers.diffuser && product.lens_appearance && !product.lens_appearance.includes(answers.diffuser)) {
    out.push(`${answers.diffuser} lens not stocked (alt available)`);
  }
  if (answers.finish && product.finish && !product.finish.includes(answers.finish)) {
    out.push(`${answers.finish} finish not stocked`);
  }
  return out;
}

/**
 * Power-injection derivation: watts/ft x length vs. usable single-supply load,
 * and run length vs. the tape's max single-feed run length.
 */
export function computePower(answers, product) {
  const length = Number(answers.run_length);
  if (!product || !Number.isFinite(length) || length <= 0) {
    return { applicable: false, needs_power_injection: false, supply_count_estimate: 0 };
  }
  const totalW = (product.watts_per_foot || 0) * length;
  const supplyCount = Math.max(1, Math.ceil(totalW / USABLE_SUPPLY_W));
  const exceedsRun = product.voltage_drop_max_run_length_ft
    ? length > product.voltage_drop_max_run_length_ft
    : false;
  return {
    applicable: true,
    total_watts: Math.round(totalW * 10) / 10,
    usable_supply_watts: USABLE_SUPPLY_W,
    max_single_feed_run_ft: product.voltage_drop_max_run_length_ft || null,
    needs_power_injection: exceedsRun || supplyCount > 1,
    exceeds_max_run: exceedsRun,
    supply_count_estimate: supplyCount,
  };
}

function rank(list, answers) {
  return list
    .map((p) => ({
      sku: p.sku,
      family: p.series,
      brand: p.brand,
      attributes: p,
      score: scoreProduct(p, answers),
      tradeoffs: tradeoffsFor(p, answers),
    }))
    .sort((a, b) => b.score - a.score);
}

/**
 * Main entry: returns ranked ilLumenate recommendations + which soft criteria
 * (if any) had to be relaxed to produce them.
 *
 * @returns {{ recommendations: Array, relaxed: string[], relaxedLabels: string[] }}
 */
export function recommend(answers) {
  const eligible = PRODUCTS.filter((p) => hardFilterReasons(p, answers).length === 0);

  if (eligible.length === 0) {
    return { recommendations: [], relaxed: [], relaxedLabels: [], noHardMatch: true };
  }

  // Exact match: passes every applicable soft check too.
  const exact = eligible.filter((p) => Object.values(softChecks(p, answers)).every(Boolean));
  if (exact.length > 0) {
    return { recommendations: rank(exact, answers), relaxed: [], relaxedLabels: [] };
  }

  // Relax soft constraints in priority order until something survives.
  const dropped = [];
  for (const crit of RELAX_ORDER) {
    dropped.push(crit);
    const survivors = eligible.filter((p) => {
      const soft = softChecks(p, answers);
      return Object.entries(soft).every(([k, v]) => dropped.includes(k) || v);
    });
    if (survivors.length > 0) {
      return {
        recommendations: rank(survivors, answers),
        relaxed: [...dropped],
        relaxedLabels: dropped.map((d) => RELAX_LABEL[d]),
      };
    }
  }

  // Nothing satisfied even after full relaxation: rank all hard-eligible.
  return {
    recommendations: rank(eligible, answers),
    relaxed: [...RELAX_ORDER],
    relaxedLabels: RELAX_ORDER.map((d) => RELAX_LABEL[d]),
  };
}

/** Competitor comparison stub, ranked the same way (illustrative only). */
export function competitorRecommendations(answers) {
  return rank(COMPETITORS, answers);
}
