import { useEffect, useRef, useState } from 'react';
import { Zap, Info as InfoIcon } from 'lucide-react';
import GlossaryTerm from './GlossaryTerm.jsx';
import { visibleOptions } from '../lib/engine.js';
import { recommend, computePower, optionWouldEliminateAll } from '../lib/recommend.js';

// Indoor / Outdoor
import indoorImg from '../assets/indoor-outdoor-indoor.jpg';
import outdoorImg from '../assets/indoor-outdoor-outdoor.jpg';
// Moisture
import moistureDryImg from '../assets/moisture-dry.jpg';
import moistureDampImg from '../assets/moisture-damp.jpg';
import moistureWetImg from '../assets/moisture-wet.jpg';
// IP Rating
import ipRating65Img from '../assets/ip-rating-ip65.jpg';
import ipRating67Img from '../assets/ip-rating-ip67.jpg';
import ipRating68Img from '../assets/ip-rating-ip68.jpg';
// Color Mode
import colorModeAnalogImg from '../assets/color-mode-analog-rgb.jpg';
import colorModePixelImg from '../assets/color-mode-addressable-pixel.jpg';
// Fixture Purpose
import fixtureAccentImg from '../assets/fixture-purpose-accent.jpg';
import fixtureTaskImg from '../assets/fixture-purpose-task.jpg';
import fixtureAmbientImg from '../assets/fixture-purpose-ambient.jpg';
// Installation Method
import installSurfaceImg from '../assets/installation-method-surface.jpg';
import installRecessedImg from '../assets/installation-method-recessed.jpg';
import installAngledImg from '../assets/installation-method-angled.jpg';
import installDrywallImg from '../assets/installation-method-drywall-plaster-in.jpg';
import installSuspendedImg from '../assets/installation-method-suspended.jpg';
// CRI
import cri90Img from '../assets/cri-90-plus.jpg';
import cri95Img from '../assets/cri-95-plus.jpg';
// Continuous Run
import continuousRunYesImg from '../assets/continuous-run-yes.jpg';
import continuousRunNoImg from '../assets/continuous-run-no.jpg';
// Supply Voltage
import voltage24vdcImg from '../assets/supply-voltage-24vdc.jpg';
import voltage120vacImg from '../assets/supply-voltage-120vac.jpg';
// Dimming Protocol
import dimming010vImg from '../assets/dimming-protocol-0-10v.jpg';
import dimmingTriacImg from '../assets/dimming-protocol-triac.jpg';
import dimmingElvImg from '../assets/dimming-protocol-elv.jpg';
import dimmingDaliImg from '../assets/dimming-protocol-dali.jpg';
import dimmingDmx512Img from '../assets/dimming-protocol-dmx512.jpg';
import dimmingSpiImg from '../assets/dimming-protocol-spi.jpg';
// Diffuser
import diffuserClearImg from '../assets/diffuser-clear.jpg';
import diffuserFrostedImg from '../assets/diffuser-frosted.jpg';
import diffuserWhiteImg from '../assets/diffuser-white.jpg';
import diffuserBlackImg from '../assets/diffuser-black.jpg';
// Finish
import finishSilverImg from '../assets/finish-silver.jpg';
import finishBlackImg from '../assets/finish-black.jpg';
import finishWhiteImg from '../assets/finish-white.jpg';

const imageMap = {
  // Indoor / Outdoor
  'indoor-outdoor-indoor': indoorImg,
  'indoor-outdoor-outdoor': outdoorImg,
  // Moisture
  'moisture-dry': moistureDryImg,
  'moisture-damp': moistureDampImg,
  'moisture-wet': moistureWetImg,
  // IP Rating
  'ip-rating-ip65': ipRating65Img,
  'ip-rating-ip67': ipRating67Img,
  'ip-rating-ip68': ipRating68Img,
  // Color Mode
  'color-mode-analog-rgb': colorModeAnalogImg,
  'color-mode-addressable-pixel': colorModePixelImg,
  // Fixture Purpose
  'fixture-purpose-accent': fixtureAccentImg,
  'fixture-purpose-task': fixtureTaskImg,
  'fixture-purpose-ambient': fixtureAmbientImg,
  // Installation Method
  'installation-method-surface': installSurfaceImg,
  'installation-method-recessed': installRecessedImg,
  'installation-method-angled': installAngledImg,
  'installation-method-drywall-plaster-in': installDrywallImg,
  'installation-method-suspended': installSuspendedImg,
  // CRI
  'cri-90-plus': cri90Img,
  'cri-95-plus': cri95Img,
  // Continuous Run
  'continuous-run-yes': continuousRunYesImg,
  'continuous-run-no': continuousRunNoImg,
  // Supply Voltage
  'supply-voltage-24vdc': voltage24vdcImg,
  'supply-voltage-120vac': voltage120vacImg,
  // Dimming Protocol
  'dimming-protocol-0-10v': dimming010vImg,
  'dimming-protocol-triac': dimmingTriacImg,
  'dimming-protocol-elv': dimmingElvImg,
  'dimming-protocol-dali': dimmingDaliImg,
  'dimming-protocol-dmx512': dimmingDmx512Img,
  'dimming-protocol-spi': dimmingSpiImg,
  // Diffuser
  'diffuser-clear': diffuserClearImg,
  'diffuser-frosted': diffuserFrostedImg,
  'diffuser-white': diffuserWhiteImg,
  'diffuser-black': diffuserBlackImg,
  // Finish
  'finish-silver': finishSilverImg,
  'finish-black': finishBlackImg,
  'finish-white': finishWhiteImg,
};

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
            answers={answers}
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

function OptionList({ question, options, value, answers, onChange }) {
  const multi = question.type === 'multi';
  const isSelected = (v) => (multi ? Array.isArray(value) && value.includes(v) : value === v);

  const disabledMap = {};
  for (const opt of options) {
    disabledMap[opt.value] = optionWouldEliminateAll(question, opt.value, answers);
  }
  const allDisabled =
    options.length > 0 && options.every((opt) => disabledMap[opt.value] && !isSelected(opt.value));

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
      {allDisabled && (
        <div
          role="alert"
          className="rounded-lg border border-ill-danger bg-ill-paper px-3 py-2 text-sm text-ill-danger"
        >
          No products match every previous answer. Go back and adjust an earlier
          choice to continue.
        </div>
      )}
      {options.map((opt) => {
        const selected = isSelected(opt.value);
        const disabled = disabledMap[opt.value] && !selected;
        const btn = (
          <button
            key={opt.value}
            type="button"
            role={multi ? 'checkbox' : 'radio'}
            aria-checked={selected}
            aria-disabled={disabled || undefined}
            disabled={disabled}
            onClick={() => {
              if (disabled) return;
              toggle(opt.value);
            }}
            className={[
              'flex w-full flex-col rounded-xl border text-left transition outline-none overflow-hidden',
              'focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-1',
              selected
                ? 'border-ill-accent bg-ill-accentBg'
                : 'border-ill-border bg-ill-paper hover:border-ill-borderStr',
              disabled ? 'cursor-not-allowed opacity-40 hover:border-ill-border' : '',
            ].join(' ')}
          >
            <span className="flex items-start gap-3 px-4 py-3">
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
            </span>
            {opt.imageId ? (
              <div className="px-4 pb-4">
                <img
                  src={imageMap[opt.imageId]}
                  alt=""
                  className="w-full rounded-lg object-cover"
                />
              </div>
            ) : opt.image ? (
              <div className="px-4 pb-4">
                <img
                  src={opt.image}
                  alt=""
                  className="w-full rounded-lg object-cover"
                />
              </div>
            ) : opt.color ? (
              <div className="px-4 pb-4">
                <div
                  aria-hidden="true"
                  className="w-full rounded-lg"
                  style={{ background: opt.color, height: '5rem' }}
                />
              </div>
            ) : null}
          </button>
        );

        return disabled ? (
          <DisabledOptionWrapper key={opt.value}>
            {btn}
          </DisabledOptionWrapper>
        ) : (
          <div key={opt.value}>{btn}</div>
        );
      })}
    </div>
  );
}

/**
 * Wraps a disabled option button. Shows a centered tooltip on hover that
 * lingers for 400 ms so the user can move the mouse onto the email link.
 */
function DisabledOptionWrapper({ children }) {
  const [open, setOpen] = useState(false);
  const hideTimer = useRef(null);

  useEffect(() => () => clearTimeout(hideTimer.current), []);

  const show = () => {
    clearTimeout(hideTimer.current);
    setOpen(true);
  };
  const scheduleHide = () => {
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setOpen(false), 400);
  };

  return (
    <div className="relative" onMouseEnter={show} onMouseLeave={scheduleHide}>
      {children}
      {open && (
        <div
          role="tooltip"
          onMouseEnter={show}
          onMouseLeave={scheduleHide}
          className="absolute inset-x-2 top-1/2 z-10 -translate-y-1/2 rounded-lg border border-ill-border bg-ill-paper px-4 py-3 shadow-xl text-sm text-ill-ink text-center"
        >
          Please contact us at{' '}
          <a
            href="mailto:sales@illumenate.lighting"
            className="font-medium text-ill-accent underline decoration-dotted underline-offset-2 hover:opacity-80"
            onClick={(e) => e.stopPropagation()}
          >
            sales@illumenate.lighting
          </a>{' '}
          for this configuration.
        </div>
      )}
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
          Estimated load:{' '}
          <strong aria-label={`Estimated power load ${power.total_watts} watts`}>
            {power.total_watts} W
          </strong>{' '}
          over {answers.run_length} ft
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
