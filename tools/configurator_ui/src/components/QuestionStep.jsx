import { useEffect } from 'react';
import { Zap, Info as InfoIcon } from 'lucide-react';
import GlossaryTerm from './GlossaryTerm.jsx';
import { visibleOptions } from '../lib/engine.js';
import { recommend, computePower } from '../lib/recommend.js';

/**
 * Renders one wizard step for a question definition.
 * Supported types: single | multi | number | range | info.
 *
 * @param {object} props
 * @param {object} props.question  Question definition from questions.json.
 * @param {object} props.answers   Current answers map.
 * @param {(value:any)=>void} props.onChange  Update this question's answer.
 */
export default function QuestionStep({ question, answers, onChange }) {
  const value = answers[question.id];

  // Auto-select the sole remaining option (e.g. protocol forced to SPI/DMX).
  const opts = question.options ? visibleOptions(question, answers) : [];
  useEffect(() => {
    if (
      (question.type === 'single' || question.type === 'multi') &&
      question.required &&
      opts.length === 1 &&
      value === undefined
    ) {
      onChange(question.type === 'multi' ? [opts[0].value] : opts[0].value);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id, opts.length]);

  return (
    <div>
      <h2 className="font-display text-2xl font-semibold text-ill-ink">
        {question.label}
        {!question.required && question.type !== 'info' && (
          <span className="ml-2 align-middle text-sm font-normal text-ill-subtle">(optional)</span>
        )}
      </h2>

      {question.glossaryKey && (
        <p className="mt-1 text-sm text-ill-muted">
          Not sure?{' '}
          <GlossaryTerm termKey={question.glossaryKey} />
        </p>
      )}

      <div className="mt-5">
        {(question.type === 'single' || question.type === 'multi') && (
          <OptionList
            question={question}
            options={opts}
            value={value}
            onChange={onChange}
          />
        )}

        {question.type === 'number' && (
          <NumberInput question={question} value={value} onChange={onChange} />
        )}

        {question.type === 'range' && (
          <RangeInput question={question} value={value} onChange={onChange} />
        )}

        {question.type === 'info' && question.id === 'power_injection' && (
          <PowerInjectionInfo answers={answers} />
        )}
      </div>
    </div>
  );
}

function OptionList({ question, options, value, onChange }) {
  const multi = question.type === 'multi';
  const isSelected = (v) => (multi ? Array.isArray(value) && value.includes(v) : value === v);

  const toggle = (v) => {
    if (!multi) {
      onChange(v);
      return;
    }
    const set = new Set(Array.isArray(value) ? value : []);
    if (set.has(v)) set.delete(v);
    else set.add(v);
    onChange([...set]);
  };

  return (
    <div role={multi ? 'group' : 'radiogroup'} className="grid gap-2.5">
      {options.map((opt) => {
        const selected = isSelected(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            role={multi ? 'checkbox' : 'radio'}
            aria-checked={selected}
            onClick={() => toggle(opt.value)}
            className={[
              'flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition outline-none',
              'focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-1',
              selected
                ? 'border-ill-accent bg-ill-accentBg'
                : 'border-ill-border bg-ill-paper hover:border-ill-borderStr',
            ].join(' ')}
          >
            <span
              aria-hidden="true"
              className={[
                'mt-0.5 flex h-5 w-5 flex-none items-center justify-center border',
                multi ? 'rounded' : 'rounded-full',
                selected ? 'border-ill-accent bg-ill-accent' : 'border-ill-borderStr bg-white',
              ].join(' ')}
            >
              {selected && <span className="h-2 w-2 rounded-full bg-white" />}
            </span>
            <span className="flex-1">
              <span className="flex items-center gap-2 font-medium text-ill-ink">
                {opt.label}
                {opt.glossaryKey && <GlossaryTerm termKey={opt.glossaryKey}>?</GlossaryTerm>}
              </span>
              {opt.note && (
                <span className="mt-0.5 block text-xs text-ill-danger">{opt.note}</span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function NumberInput({ question, value, onChange }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        inputMode="decimal"
        min={question.min}
        max={question.max}
        step={question.step}
        placeholder={question.placeholder}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
        className="w-40 rounded-lg border border-ill-borderStr bg-ill-paper px-3 py-2 text-ill-ink outline-none focus-visible:ring-2 focus-visible:ring-ill-accent"
        aria-label={question.label}
      />
      {question.unit && <span className="text-ill-muted">{question.unit}</span>}
    </div>
  );
}

function RangeInput({ question, value, onChange }) {
  const low = value?.low ?? question.defaultLow ?? question.min;
  const high = value?.high ?? question.defaultHigh ?? question.max;

  const update = (next) => {
    let lo = Number(next.low);
    let hi = Number(next.high);
    if (lo > hi) [lo, hi] = [hi, lo];
    onChange({ low: lo, high: hi });
  };

  return (
    <div className="max-w-md">
      <div className="flex items-center justify-between text-sm font-medium text-ill-ink">
        <span>
          {low}
          {question.unit}
        </span>
        <span>
          {high}
          {question.unit}
        </span>
      </div>
      <div className="mt-2 grid gap-3">
        <label className="text-xs text-ill-muted">
          Low end
          <input
            type="range"
            min={question.min}
            max={question.max}
            step={question.step}
            value={low}
            onChange={(e) => update({ low: e.target.value, high })}
            className="mt-1 block w-full accent-ill-accent"
          />
        </label>
        <label className="text-xs text-ill-muted">
          High end
          <input
            type="range"
            min={question.min}
            max={question.max}
            step={question.step}
            value={high}
            onChange={(e) => update({ low, high: e.target.value })}
            className="mt-1 block w-full accent-ill-accent"
          />
        </label>
      </div>
    </div>
  );
}

/**
 * Informational, auto-derived step (Q9): power injection / multiple supplies.
 * Computed against the current top recommendation so the math reflects a real
 * candidate's watts/ft and max single-feed run length.
 */
function PowerInjectionInfo({ answers }) {
  const { recommendations } = recommend(answers);
  const top = recommendations[0] ? recommendations[0].attributes : null;
  const power = computePower(answers, top);

  if (!power.applicable) {
    return (
      <p className="rounded-lg border border-ill-border bg-ill-bg p-4 text-sm text-ill-muted">
        Enter a run length on the previous step to see whether power injection is needed.
      </p>
    );
  }

  const tone = power.needs_power_injection
    ? 'border-ill-accent bg-ill-accentBg'
    : 'border-ill-success bg-ill-successBg';

  return (
    <div className={`rounded-lg border p-4 ${tone}`}>
      <div className="flex items-center gap-2 font-medium text-ill-ink">
        <Zap size={18} aria-hidden="true" />
        {power.needs_power_injection
          ? 'Power injection / multiple supplies recommended'
          : 'A single power feed should be sufficient'}
      </div>
      <ul className="mt-2 space-y-1 text-sm text-ill-muted">
        <li>
          Estimated load: <strong>{power.total_watts} W</strong> over {answers.run_length} ft
          {top ? ` (${top.sku})` : ''}.
        </li>
        <li>
          Usable single-supply capacity: ~{power.usable_supply_watts} W &rarr; estimated{' '}
          <strong>{power.supply_count_estimate}</strong> supply
          {power.supply_count_estimate === 1 ? '' : 's'}.
        </li>
        {power.max_single_feed_run_ft != null && (
          <li>
            Max single-feed run for this product: {power.max_single_feed_run_ft} ft
            {power.exceeds_max_run ? ' — your run exceeds this, so inject power mid-run.' : '.'}
          </li>
        )}
      </ul>
      <p className="mt-2 flex items-start gap-1 text-xs text-ill-subtle">
        <InfoIcon size={13} className="mt-0.5 flex-none" aria-hidden="true" />
        Derived estimate for planning only; confirm against the final driver schedule.
      </p>
    </div>
  );
}
