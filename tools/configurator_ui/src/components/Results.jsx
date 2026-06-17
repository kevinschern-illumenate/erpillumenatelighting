import { useMemo, useState } from 'react';
import {
  CheckCircle2, AlertTriangle, Download, Copy, RotateCcw, Terminal, FileText, FileCheck, Building,
} from 'lucide-react';
import CompareTable from './CompareTable.jsx';
import { recommend, competitorRecommendations } from '../lib/recommend.js';
import { buildResultObject, downloadResultObject } from '../lib/resultObject.js';
import { lumensBandFor } from '../lib/engine.js';

/**
 * Final results screen: ranked ilLumenate recommendations, no-match relaxation
 * banner, competitor comparison stub, and result-object export.
 *
 * @param {object} props
 * @param {object} props.answers
 * @param {() => void} props.onRestart
 */
export default function Results({ answers, onRestart }) {
  const [copied, setCopied] = useState(false);

  const { recommendations, relaxedLabels, noHardMatch } = useMemo(
    () => recommend(answers),
    [answers]
  );
  const competitors = useMemo(() => competitorRecommendations(answers), [answers]);
  const resultObject = useMemo(() => buildResultObject(answers), [answers]);

  const band = lumensBandFor(answers.fixture_purpose);
  const top = recommendations[0] || null;

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(resultObject, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // eslint-disable-next-line no-console
      console.log('[IllConfigurator] result object:', resultObject);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 text-ill-success">
        <CheckCircle2 size={22} aria-hidden="true" />
        <h2 className="font-display text-2xl font-semibold">Your recommended fixtures</h2>
      </div>
      {band && (
        <p className="mt-1 text-sm text-ill-muted">
          Targeting <strong>{band.label}</strong> for a{' '}
          <strong>{answers.fixture_purpose}</strong> application (configurator heuristic).
        </p>
      )}

      {/* No-match relaxation banner */}
      {relaxedLabels.length > 0 && (
        <div
          role="status"
          className="mt-4 flex items-start gap-2 rounded-lg border border-ill-accent bg-ill-accentBg p-3 text-sm text-ill-ink"
        >
          <AlertTriangle size={18} className="mt-0.5 flex-none text-ill-accent" aria-hidden="true" />
          <span>
            No exact match was found, so we relaxed <strong>{relaxedLabels.join(', ')}</strong>.
            Review the trade-offs noted on each result below.
          </span>
        </div>
      )}

      {noHardMatch && (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-ill-danger bg-ill-dangerBg p-3 text-sm text-ill-ink"
        >
          No products satisfy the required compatibility constraints (environment, voltage,
          protocol, or installation). Try adjusting those answers.
        </div>
      )}

      {/* Recommendation cards */}
      <div className="mt-5 grid gap-3">
        {recommendations.map((rec, i) => (
          <div
            key={rec.sku}
            className={[
              'rounded-xl border p-4',
              i === 0 ? 'border-ill-accent bg-ill-accentBg' : 'border-ill-border bg-ill-paper',
            ].join(' ')}
          >
            <div className="flex flex-col gap-4">
              <div className="flex gap-4">
                {/* Image with badge */}
                <div className="relative inline-w-fit">
                  {rec.attributes.image_hero_url && (
                    <img
                      src={rec.attributes.image_hero_url}
                      alt={`${rec.family} fixture`}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      className="h-48 w-96 rounded-lg border border-ill-border bg-white object-contain"
                      onError={(e) => {
                        const el = e.currentTarget;
                        el.style.display = 'none';
                        const placeholder = el.parentElement.querySelector('[data-img-placeholder]');
                        if (placeholder) placeholder.style.display = 'flex';
                      }}
                    />
                  )}
                  {rec.attributes.image_hero_url && (
                    <div
                      data-img-placeholder="1"
                      style={{ display: 'none' }}
                      className="h-48 w-96 rounded-lg border border-ill-border bg-ill-paper flex flex-col items-center justify-center gap-1 text-ill-subtle text-xs"
                    >
                      <span className="text-2xl">🖼️</span>
                      Image unavailable
                      <a
                        href={rec.attributes.image_hero_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-ill-accent underline decoration-dotted"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Open URL
                      </a>
                    </div>
                  )}
                  {i === 0 && (
                    <span className="absolute top-2 left-2 rounded bg-ill-accent px-2 py-0.5 text-[11px] font-medium text-white">
                      Best match
                    </span>
                  )}
                </div>
                {/* Links to the right of image */}
                <div className="flex flex-col gap-2 justify-start">
                  {rec.attributes.spec_sheet_url && (
                    <a
                      href={rec.attributes.spec_sheet_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-sm font-medium text-ill-accent outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ill-accent"
                    >
                      <FileText size={16} aria-hidden="true" /> Spec Sheet
                    </a>
                  )}
                  {rec.attributes.spec_submittal_url && (
                    <a
                      href={rec.attributes.spec_submittal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-sm font-medium text-ill-accent outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ill-accent"
                    >
                      <FileCheck size={16} aria-hidden="true" /> Spec Submittal
                    </a>
                  )}
                  {rec.attributes.dealer_portal_url && (
                    <a
                      href={rec.attributes.dealer_portal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-sm font-medium text-ill-accent outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ill-accent"
                    >
                      <Building size={16} aria-hidden="true" /> Dealer Portal
                    </a>
                  )}
                </div>
              </div>
              <div>
                <div className="flex items-start justify-between gap-8">
                  <div className="flex flex-col max-w-lg">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-ill-ink">{rec.sku}</span>
                    </div>
                    <div className="text-sm text-ill-muted">
                      {rec.brand} &middot; {rec.family} &middot; {rec.attributes.lumens_per_foot} lm/ft
                      &middot; CRI {rec.attributes.cri_typical} &middot; {rec.attributes.input_voltage}
                    </div>
                  </div>
                  <div className="text-right flex-none">
                    <div className="font-display text-xl font-semibold text-ill-ink">{rec.score}</div>
                    <div className="text-[11px] uppercase tracking-wide text-ill-subtle">match score</div>
                  </div>
                </div>
                {rec.tradeoffs.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {rec.tradeoffs.map((t) => (
                      <li
                        key={t}
                        className="rounded bg-ill-paper/70 px-2 py-0.5 text-xs text-ill-danger ring-1 ring-inset ring-ill-border"
                      >
                        {t}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Competitor comparison */}
      <h3 className="mt-8 font-display text-lg font-semibold text-ill-ink">
        Competitor comparison
      </h3>
      <p className="mb-3 text-sm text-ill-muted">
        How the ilLumenate pick stacks up against comparable competitor products.
      </p>
      <CompareTable primary={top} competitors={competitors.slice(0, 3)} />

      {/* Export / actions */}
      <div className="mt-8 flex flex-wrap gap-2 border-t border-ill-border pt-5">
        <button
          type="button"
          onClick={() => downloadResultObject(resultObject)}
          className="inline-flex items-center gap-2 rounded-lg bg-ill-accent px-4 py-2 font-medium text-white outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-2"
        >
          <Download size={16} aria-hidden="true" /> Download result JSON
        </button>
        <button
          type="button"
          onClick={copyJson}
          className="inline-flex items-center gap-2 rounded-lg border border-ill-borderStr bg-ill-paper px-4 py-2 font-medium text-ill-ink outline-none transition hover:border-ill-accent focus-visible:ring-2 focus-visible:ring-ill-accent"
        >
          {copied ? <CheckCircle2 size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
          {copied ? 'Copied' : 'Copy JSON'}
        </button>
        <button
          type="button"
          onClick={() => {
            // eslint-disable-next-line no-console
            console.log('[IllConfigurator] result object:', resultObject);
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-ill-borderStr bg-ill-paper px-4 py-2 font-medium text-ill-ink outline-none transition hover:border-ill-accent focus-visible:ring-2 focus-visible:ring-ill-accent"
        >
          <Terminal size={16} aria-hidden="true" /> Log to console
        </button>
        <button
          type="button"
          onClick={onRestart}
          className="ml-auto inline-flex items-center gap-2 rounded-lg border border-ill-borderStr bg-ill-paper px-4 py-2 font-medium text-ill-ink outline-none transition hover:border-ill-accent focus-visible:ring-2 focus-visible:ring-ill-accent"
        >
          <RotateCcw size={16} aria-hidden="true" /> Start over
        </button>
      </div>
    </div>
  );
}
