# Configurator UI Improvements — Implementation Plan

> **Audience:** This document is a complete, self-contained implementation plan for an AI coding agent.
> No additional research should be required. All file paths, function signatures, and exact content
> are provided below. Implement all three features in the order listed.
>
> **Repo root:** `tools/configurator_ui/`
> **All paths below are relative to that root unless stated otherwise.**

---

## Table of Contents

1. [Feature 1 — Dimming Option Glossary Hovers](#feature-1--dimming-option-glossary-hovers)
2. [Feature 2 — Hide Operating Temperature Question](#feature-2--hide-operating-temperature-question)
3. [Feature 3 — Interactive Progress Bar with Jump Navigation and Broken-Step Highlighting](#feature-3--interactive-progress-bar-with-jump-navigation-and-broken-step-highlighting)

---

## Feature 1 — Dimming Option Glossary Hovers

### Goal

Each option in the **"Which dimming / control protocol will you use?"** question should show a `?` info
icon that, when hovered or clicked, reveals a short tooltip explaining what that protocol is and when to
use it — exactly like `GlossaryTerm` already works for question-level labels.

### How it already works (no code changes needed for rendering)

`src/components/QuestionStep.jsx` already renders `GlossaryTerm` per option:

```jsx
<span className="flex items-center gap-2 font-medium text-ill-ink">
  {opt.label}
  {opt.glossaryKey && <GlossaryTerm termKey={opt.glossaryKey}>?</GlossaryTerm>}
</span>
```

So the **only changes needed** are in the two JSON content files.

---

### Step 1A — Add glossary entries to `src/content/glossary.json`

Add the following **six new top-level keys** to `glossary.json`. Insert them after the existing
`"dimming_protocol"` entry (which covers the question as a whole) so they stay grouped together.
Do **not** remove or modify the existing `"dimming_protocol"` entry.

```json
"dimming_0_10v": {
  "label": "0-10V Dimming",
  "tooltip": "An analog signal between 0 and 10 volts controls brightness. 10V = full output, 1V = dim-low, 0V = off.",
  "learnMore": "0-10V is the most common protocol in architectural LED lighting. The driver needs a dedicated 0-10V input; standard wall dimmers will not work without a 0-10V wall station. Supported by virtually all LED tape drivers in our catalog.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
},
"dimming_triac": {
  "label": "TRIAC Dimming",
  "tooltip": "Phase-cut dimming that works with most standard wall dimmers — common for residential and retrofit 120VAC applications.",
  "learnMore": "TRIAC (also called Forward Phase dimming) clips the AC sine wave to reduce average power. Works with most standard incandescent-style wall dimmers. Best for 120VAC line-voltage products. Some LED drivers have a minimum-load threshold below which they may flicker — confirm driver compatibility.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
},
"dimming_elv": {
  "label": "ELV Dimming",
  "tooltip": "Electronic Low Voltage dimming — also called Reverse Phase dimming. Smoother phase-cut than TRIAC for many LED loads.",
  "learnMore": "ELV removes the trailing edge of the AC waveform rather than the leading edge (TRIAC). Many modern LED drivers prefer ELV because it puts less stress on the switching circuitry, resulting in smoother dimming and fewer compatibility issues. Requires an ELV-compatible wall dimmer.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
},
"dimming_dali": {
  "label": "DALI",
  "tooltip": "Digital Addressable Lighting Interface — a two-wire digital bus that can independently address up to 64 fixtures on one circuit.",
  "learnMore": "DALI (IEC 62386) is the premium protocol for commercial and architectural projects. Each device has a unique address so scenes, schedules, and occupancy responses can be programmed per fixture without re-wiring. Provides status feedback (lamp failure, power failure) back to the building management system. Requires a DALI controller and DALI-capable drivers.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
},
"dimming_dmx512": {
  "label": "DMX512",
  "tooltip": "Industry-standard digital protocol for stage and architectural lighting. One universe = up to 512 channels of control.",
  "learnMore": "DMX512 (EIA-485) is used for color mixing, effects, and architectural dynamic lighting. A single DMX run (universe) can carry 512 channels; RGB tape uses 3 channels per zone, RGBW uses 4. Requires a DMX controller (hardware or software). Common for hospitality, retail, and entertainment-grade color installations.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
},
"dimming_spi": {
  "label": "SPI (Addressable Pixel)",
  "tooltip": "High-speed serial protocol that gives each pixel its own IC chip — enables per-pixel chases, gradients, and video-mapped effects.",
  "learnMore": "SPI (e.g., WS2812B, SK6812, APA102) embeds a controller IC inside every pixel. Each pixel is independently addressable, so thousands of pixels can run different colors simultaneously. Requires an SPI-compatible pixel controller and appropriate power injection. This is automatically forced when you select Addressable Pixel in the Color Mode question.",
  "refs": ["ilL-Attribute-Dimming Protocol"]
}
```

---

### Step 1B — Add `glossaryKey` to each dimming option in `src/content/questions.json`

Locate the `dimming_protocol` question object (id: `"dimming_protocol"`). Add a `glossaryKey` field
to each of the six options as shown below. **Do not change anything else in this question.**

```json
{
  "id": "dimming_protocol",
  "label": "Which dimming / control protocol will you use?",
  "glossaryKey": "dimming_protocol",
  "type": "single",
  "required": true,
  "filters": { "attribute": "dimming_protocol" },
  "options": [
    {
      "value": "0-10V",
      "label": "0-10V",
      "glossaryKey": "dimming_0_10v",
      "hideWhen": { "any": [{ "q": "color_mode", "eq": "Addressable pixel (SPI)" }] },
      "imageId": "dimming-protocol-0-10v",
      "color": "linear-gradient(90deg, #c5cae9, #9fa8da)"
    },
    {
      "value": "TRIAC",
      "label": "TRIAC",
      "glossaryKey": "dimming_triac",
      "hideWhen": { "any": [{ "q": "color_mode", "eq": "Addressable pixel (SPI)" }] },
      "imageId": "dimming-protocol-triac",
      "color": "#e0e0e0"
    },
    {
      "value": "ELV",
      "label": "ELV",
      "glossaryKey": "dimming_elv",
      "hideWhen": { "any": [{ "q": "color_mode", "eq": "Addressable pixel (SPI)" }] },
      "imageId": "dimming-protocol-elv",
      "color": "#e8d7e8"
    },
    {
      "value": "DALI",
      "label": "DALI",
      "glossaryKey": "dimming_dali",
      "hideWhen": { "any": [{ "q": "color_mode", "eq": "Addressable pixel (SPI)" }] },
      "imageId": "dimming-protocol-dali",
      "color": "#c8e6c9"
    },
    {
      "value": "DMX512",
      "label": "DMX512",
      "glossaryKey": "dimming_dmx512",
      "imageId": "dimming-protocol-dmx512",
      "color": "#ffccbc"
    },
    {
      "value": "SPI",
      "label": "SPI (addressable pixel)",
      "glossaryKey": "dimming_spi",
      "imageId": "dimming-protocol-spi",
      "color": "linear-gradient(90deg, #00bcd4, #03a9f4, #2196f3)"
    }
  ]
}
```

### Verification for Feature 1

1. Run `npm run dev` and navigate to the dimming protocol step.
2. Confirm each of the six options now shows a small `?` info icon to the right of the label text.
3. Hover over (or click) each icon — a tooltip panel should appear with the short description.
4. Clicking "Learn more" inside the tooltip should expand the longer explanation.
5. Pressing `Escape` should close the tooltip.

---

## Feature 2 — Hide Operating Temperature Question

### Goal

Remove the operating temperature step from the visible wizard flow for now. When re-enabling is
needed later, removing one JSON property should be all that is required.

### How the skip mechanism works

`src/lib/engine.js` evaluates `skipWhen` via `evalCondition()`. The pattern
`{ "all": [] }` uses `[].every(...)` which is always `true` in JavaScript — so the question is
unconditionally skipped. This same pattern is already used on `supply_voltage`.

### Step 2A — Add `skipWhen` to `operating_temp` in `src/content/questions.json`

Locate the `"operating_temp"` question object and add the `skipWhen` block shown below.
No other fields should be changed.

**Before:**
```json
{
  "id": "operating_temp",
  "label": "What is the ambient operating temperature? (optional)",
  "glossaryKey": "operating_temp",
  "type": "number",
  "required": false,
  "min": -40,
  "max": 80,
  "step": 1,
  "unit": "\u00b0C",
  "placeholder": "e.g. 25"
}
```

**After:**
```json
{
  "id": "operating_temp",
  "label": "What is the ambient operating temperature? (optional)",
  "glossaryKey": "operating_temp",
  "type": "number",
  "required": false,
  "skipWhen": {
    "_note": "Hidden for now — remove this skipWhen block entirely to re-enable the question.",
    "all": []
  },
  "min": -40,
  "max": 80,
  "step": 1,
  "unit": "\u00b0C",
  "placeholder": "e.g. 25"
}
```

### Verification for Feature 2

Walk through the entire wizard — the operating temperature input should no longer appear as a step.
The step count displayed in the progress bar should decrease by one.

---

## Feature 3 — Interactive Progress Bar with Jump Navigation and Broken-Step Highlighting

### Goal

Replace the static progress bar with an interactive step-by-step navigator:

- A row of numbered bubbles — one per visible question.
- **Answered** past steps (before the current question): gold/accent fill, clickable — clicking jumps
  directly to that step without clearing any future answers.
- **Current** step: outlined ring, not clickable.
- **Future unanswered** steps: light gray, not clickable.
- **Broken** steps — a step that *has* a stored answer but the answer is no longer valid (e.g., the
  user jumped back and changed an earlier answer that hid that option): displayed with a red fill
  and `!` icon, clickable so the user can navigate directly there to fix it.
- A thin fill bar below the bubble row continues to show overall percentage progress.
- Below the bubbles on mobile: a single text label for the current step name.

---

### Step 3A — Add a short label to each question in `src/content/questions.json`

Add a `"shortLabel"` field to every question. This label appears inside or alongside the progress
bubble on hover (tooltip) and in the mobile label bar. The labels must be concise (≤ 15 chars).

Apply the following values:

| Question `id`         | `shortLabel` to add     |
|-----------------------|-------------------------|
| `indoor_outdoor`      | `"Location"`            |
| `moisture`            | `"Moisture"`            |
| `ip_rating`           | `"IP Rating"`           |
| `light_type`          | `"Light Type"`          |
| `color_mode`          | `"Color Mode"`          |
| `fixture_purpose`     | `"Purpose"`             |
| `installation_method` | `"Install Method"`      |
| `target_cct`          | `"Color Temp"`          |
| `cct_range`           | `"CCT Range"`           |
| `cri`                 | `"CRI"`                 |
| `run_length`          | `"Run Length"`          |
| `continuous_run`      | `"Continuous?"`         |
| `power_injection`     | `"Power Feed"`          |
| `supply_voltage`      | `"Voltage"`             |
| `dimming_protocol`    | `"Dimming"`             |
| `diffuser`            | `"Diffuser"`            |
| `operating_temp`      | `"Temp"` (hidden anyway)|
| `finish`              | `"Finish"`              |

Example (apply the same pattern to all questions):

```json
{
  "id": "indoor_outdoor",
  "shortLabel": "Location",
  "label": "Is this an indoor or outdoor installation?",
  ...
}
```

---

### Step 3B — Add `isAnswerStillValid` to `src/lib/engine.js`

Add the following exported function at the **bottom** of `engine.js`, after the existing `lumensBandFor`
function. Import nothing extra — it uses only functions already in scope in that file.

```js
/**
 * Returns true when the stored answer for `question` is still a valid choice
 * given the current `answers` map (i.e., the option has not been hidden by a
 * `hideWhen` rule).
 *
 * Always returns true for non-option question types (number, range, info)
 * because those are free-entry and cannot become "stale" through branching.
 *
 * Used by the progress bar to detect broken steps after a user jumps back
 * and changes an earlier answer.
 *
 * @param {object} question  Question definition from questions.json.
 * @param {object} answers   Current answers map.
 * @returns {boolean}
 */
export function isAnswerStillValid(question, answers) {
  const value = answers[question.id];

  // No answer stored — cannot be broken.
  if (value === undefined || value === null) return true;

  // Non-option types: always valid (user typed the value freely).
  if (question.type !== 'single' && question.type !== 'multi') return true;

  const opts = visibleOptions(question, answers);
  const validValues = new Set(opts.map((o) => o.value));

  if (question.type === 'single') {
    return validValues.has(value);
  }

  // multi: broken if ANY selected value is no longer a visible option.
  if (question.type === 'multi' && Array.isArray(value)) {
    return value.every((v) => validValues.has(v));
  }

  return true;
}
```

---

### Step 3C — Rewrite `src/components/ProgressBar.jsx`

Replace the **entire file** with the following:

```jsx
import { useId } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Wizard progress navigator.
 *
 * Renders a row of numbered step bubbles above a thin fill bar.
 * Answered past steps are clickable (jump navigation).
 * Broken steps (answered but no longer valid) are highlighted red and clickable.
 *
 * @param {object}   props
 * @param {Array}    props.steps          Ordered array of { id, shortLabel } for each visible question.
 * @param {number}   props.currentIndex   0-based index of the currently active step.
 * @param {number}   props.maxReached     0-based highest step index the user has navigated to.
 * @param {number}   props.percent        Overall completion percentage (0–100).
 * @param {Set}      props.brokenSet      Set of step indices whose stored answer is no longer valid.
 * @param {Function} props.onJump         Callback: (index: number) => void.
 */
export default function ProgressBar({ steps, currentIndex, maxReached, percent, brokenSet, onJump }) {
  const navId = useId();

  return (
    <nav aria-label="Configuration progress" aria-describedby={navId} className="mb-6">
      {/* ── Bubble row ─────────────────────────────────────────────────── */}
      <ol
        id={navId}
        className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none"
        style={{ scrollbarWidth: 'none' }}
      >
        {steps.map((step, i) => {
          const isCurrent = i === currentIndex;
          const isPast = i < currentIndex || (i > currentIndex && i <= maxReached);
          const isBroken = brokenSet.has(i);
          const isClickable = (isPast || isBroken) && !isCurrent;

          let bubbleClass = '';
          let labelClass = 'sr-only';

          if (isBroken) {
            // Red: answered but invalid — user must fix.
            bubbleClass =
              'bg-red-500 text-white ring-2 ring-red-300 ring-offset-1 hover:bg-red-600 cursor-pointer';
          } else if (isCurrent) {
            // Outlined ring: active step.
            bubbleClass =
              'bg-white border-2 border-ill-accent text-ill-accent cursor-default';
          } else if (isPast) {
            // Accent filled: answered, can jump back.
            bubbleClass =
              'bg-ill-accent text-white hover:opacity-80 cursor-pointer';
          } else {
            // Gray: future unanswered, not reachable yet.
            bubbleClass =
              'bg-ill-accentSoft text-ill-subtle cursor-not-allowed';
          }

          return (
            <li key={step.id} className="flex-none">
              <button
                type="button"
                title={step.shortLabel}
                aria-label={`Step ${i + 1}: ${step.shortLabel}${isBroken ? ' — needs attention' : ''}${isCurrent ? ' (current)' : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
                disabled={!isClickable}
                onClick={() => isClickable && onJump(i)}
                className={[
                  'flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-semibold',
                  'outline-none transition focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-1',
                  bubbleClass,
                ].join(' ')}
              >
                {isBroken ? (
                  <AlertTriangle size={13} aria-hidden="true" />
                ) : (
                  i + 1
                )}
              </button>
            </li>
          );
        })}
      </ol>

      {/* ── Fill bar ───────────────────────────────────────────────────── */}
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Configuration progress"
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ill-accentSoft"
      >
        <div
          className="h-full rounded-full bg-ill-accent transition-all duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* ── Step label (visible text) ────────────────────────────────── */}
      <div className="mt-1.5 flex items-center justify-between text-xs font-medium text-ill-muted">
        <span>{steps[currentIndex]?.shortLabel ?? ''}</span>
        <span>{percent}% complete</span>
      </div>

      {/* ── Broken-step callout ─────────────────────────────────────── */}
      {brokenSet.size > 0 && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          <AlertTriangle size={14} className="mt-0.5 flex-none text-red-500" aria-hidden="true" />
          <span>
            {brokenSet.size === 1
              ? 'One earlier answer is no longer valid after your change. Click the red step to fix it.'
              : `${brokenSet.size} earlier answers are no longer valid after your change. Click the red steps to fix them.`}
          </span>
        </div>
      )}
    </nav>
  );
}
```

> **Tailwind note:** `scrollbar-none` may require the `tailwind-scrollbar-hide` plugin or equivalent.
> Alternatively, add `[&::-webkit-scrollbar]:hidden` as a custom class or use the inline style
> `style={{ scrollbarWidth: 'none' }}` already present above (works in Firefox/Chrome/Safari).

---

### Step 3D — Update `src/components/Wizard.jsx`

This requires four targeted changes to the Wizard component.

#### 3D-1 — Update imports

Add `isAnswerStillValid` to the engine import. Also import `useMemo` if not already imported (it is).

**Find:**
```js
import {
  visibleQuestions, pruneHiddenAnswers, isAnswered, progress,
} from '../lib/engine.js';
```

**Replace with:**
```js
import {
  visibleQuestions, pruneHiddenAnswers, isAnswered, progress, isAnswerStillValid,
} from '../lib/engine.js';
```

#### 3D-2 — Add `maxReachedIndex` state

Add a new piece of state directly below the existing `useState` declarations (after `const [done, setDone] = useState(false);`).

**Find:**
```js
  const [answers, setAnswers] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [done, setDone] = useState(false);
```

**Replace with:**
```js
  const [answers, setAnswers] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [done, setDone] = useState(false);
  // Tracks the highest step index the user has reached so far (used to determine
  // which future steps are "reachable" and can be clicked in the progress bar).
  const [maxReachedIndex, setMaxReachedIndex] = useState(0);
```

#### 3D-3 — Add `brokenSet` computed value and update `goNext`/`goBack`/`restart`

**Find the `goNext` / `goBack` / `restart` block:**
```js
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
```

**Replace with:**
```js
  const canAdvance = current ? isAnswered(current, answers) : false;
  const isLast = safeIndex >= visible.length - 1;

  // Compute which visible steps have a stored answer that is no longer valid
  // (the user jumped back and changed an earlier choice that hid their option).
  const brokenSet = useMemo(() => {
    const broken = new Set();
    visible.forEach((q, i) => {
      if (i === safeIndex) return; // don't mark the active step
      if (answers[q.id] === undefined) return; // not yet answered
      if (!isAnswerStillValid(q, answers)) broken.add(i);
    });
    return broken;
  }, [visible, answers, safeIndex]);

  const goNext = () => {
    if (!canAdvance) return;
    if (isLast) setDone(true);
    else {
      const nextIndex = safeIndex + 1;
      setStepIndex(nextIndex);
      setMaxReachedIndex((prev) => Math.max(prev, nextIndex));
    }
  };
  const goBack = () => {
    if (done) {
      setDone(false);
      return;
    }
    setStepIndex(Math.max(0, safeIndex - 1));
  };
  const goJump = (index) => {
    setStepIndex(index);
  };
  const restart = () => {
    setAnswers({});
    setStepIndex(0);
    setDone(false);
    setMaxReachedIndex(0);
  };
```

#### 3D-4 — Update the `<ProgressBar />` call

**Find:**
```jsx
            <ProgressBar
              current={safeIndex + 1}
              total={visible.length}
              percent={prog.percent}
            />
```

**Replace with:**
```jsx
            <ProgressBar
              steps={visible.map((q) => ({ id: q.id, shortLabel: q.shortLabel ?? q.id }))}
              currentIndex={safeIndex}
              maxReached={maxReachedIndex}
              percent={prog.percent}
              brokenSet={brokenSet}
              onJump={goJump}
            />
```

---

### Step 3E — Suppress scrollbar on the bubble row (optional polish)

If `scrollbar-none` is not available as a Tailwind class, open `src/index.css` and add:

```css
/* Hide scrollbar on the progress bubble row without affecting scroll behaviour */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
```

---

### Verification for Feature 3

1. Start the wizard and answer questions one at a time using **Next**.
   - Confirm bubble `1` turns gold/accent as you move to step `2`, etc.
   - Confirm the current bubble always has the outlined ring.
   - Confirm future bubbles remain gray.
   - Confirm the fill bar and percentage update.

2. Reach step 5 or later, then click a **past bubble** (e.g., step 2).
   - Confirm the wizard jumps immediately to that step.
   - Confirm answers for steps 3–5 are still stored (changing the step alone should NOT clear them).

3. While on step 2, change your answer to something different.
   - Confirm `pruneHiddenAnswers` removes answers for any questions that are now invisible (branching).
   - If any future step's answer is now invalid (its selected option is hidden by the new answer),
     that bubble should turn **red with a `!` icon**.
   - Confirm the red callout banner appears below the bubbles.

4. Click a **red bubble**.
   - Confirm the wizard jumps to that step.
   - Confirm a new selection fixes the red state (the bubble returns to gold once answered).

5. Restart via the **Results screen** → confirm all bubbles reset to gray and `maxReachedIndex` resets.

6. **Accessibility:** Tab through the bubble row — past and broken bubbles should receive focus and
   be operable with `Enter` / `Space`. Future (disabled) bubbles should be skipped. The `aria-current="step"`
   attribute should be on the active bubble.

---

## Summary of Files Changed

| File | Type of Change |
|------|---------------|
| `src/content/glossary.json` | Add 6 new dimming protocol option glossary entries |
| `src/content/questions.json` | Add `glossaryKey` to each dimming option; add `skipWhen` to `operating_temp`; add `shortLabel` to every question |
| `src/lib/engine.js` | Add exported `isAnswerStillValid` function |
| `src/components/ProgressBar.jsx` | Complete rewrite — clickable bubbles, broken-step highlighting |
| `src/components/Wizard.jsx` | New state (`maxReachedIndex`), new computed `brokenSet`, new `goJump` handler, updated `ProgressBar` props |
