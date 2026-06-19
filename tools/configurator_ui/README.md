# ilLumenate Product Configurator (prototype)

A standalone **Vite + React 18 + Tailwind 3** wizard that walks a user through a
14-question tree and recommends ilLumenate LED tape/neon products, with a
competitor comparison stub. It is designed to be **embedded into Webflow** as a
single mountable bundle.

It mirrors the tooling conventions of [`tools/yaml_builder_ui`](../yaml_builder_ui).

> **Data is seeded offline.** All product/attribute data lives in `src/data/` and
> is drawn from real ERP attribute names (`ilL-Spec-*`, `ilL-Attribute-*`) and
> real SKUs found in `output/<brand>/`. There are **no live ERP or network calls**.

## Run

```bash
cd tools/configurator_ui
npm install
npm run dev      # local prototype in the browser (http://localhost:5174)
npm run build    # produces the embeddable bundle in dist/
npm run preview  # preview the built bundle
```

> The sandbox used to generate this prototype has no access to the npm registry,
> so `npm install`/`npm run build` must be run in a networked environment. The
> dependency set is copied verbatim from `yaml_builder_ui`, which builds there.

## What you get

Complete the wizard in the browser → hover/tap any underlined term for a tooltip
plus an inline **"Learn more"** disclosure → see ranked ilLumenate
recommendations with a competitor-comparison table → download / copy / log the
downstream-ready result object.

## Where the content lives

| File | Purpose | Edit by |
|------|---------|---------|
| `src/content/questions.json` | The 14-question tree, branching/skip logic, and the **lumens-band heuristic** | Non-engineers |
| `src/content/glossary.json` | Tooltip + "Learn more" copy, keyed by term | Non-engineers |
| `src/data/products.seed.json` | Seeded ilLumenate products (real SKUs / attribute names) | Data owner |
| `src/data/competitors.sample.json` | Competitor comparison sample (illustrative only) | Data owner |
| `src/data/attributes.seed.json` | Controlled vocab (CCT, IP, env, protocol, lens, finish, output) | Data owner |

### Logic / UI (engineers)

```
src/lib/engine.js        branching, skip logic, visibility, progress
src/lib/recommend.js     hard filters + ranking + no-match relaxation + power math
src/lib/resultObject.js  builds + exports the downstream-ready result object
src/components/          Wizard, QuestionStep, ProgressBar, Tooltip, GlossaryTerm,
                         Results, CompareTable
```

## How to add a question

1. Add an object to the `questions` array in `src/content/questions.json`.
   Position in the array = order in the wizard.
   ```jsonc
   {
     "id": "my_question",                 // unique; becomes the answer key
     "label": "Your question text?",
     "glossaryKey": "ip_rating",          // optional, links to glossary.json
     "type": "single",                    // single | multi | number | range | info
     "required": true,
     "options": [
       { "value": "A", "label": "Option A", "glossaryKey": "..." }
     ],
     "visibleWhen": { "all": [{ "q": "other_q", "eq": "X" }] },  // optional
     "skipWhen":    { "any": [{ "q": "other_q", "eq": "Y" }] }   // optional
   }
   ```
2. Condition operators (used in `visibleWhen` / `skipWhen` and option-level
   `visibleWhen` / `hideWhen`): `eq`, `ne`, `in`, `gt`, `gte`, `lt`, `lte`,
   `exists`. Groups combine with `all` (AND) and/or `any` (OR).
3. To filter products, set `"filters": { "attribute": "<name>" }` and ensure the
   matching field exists on the seed products + the hard/soft logic in
   `recommend.js` handles it.

## How to add a glossary term

Add a keyed entry to `src/content/glossary.json`:

```jsonc
"my_term": {
  "label": "My Term",
  "tooltip": "Short, always-visible explanation.",
  "learnMore": "Longer text revealed by the inline 'Learn more' button.",
  "refs": ["ilL-Attribute-..."]      // optional source references
}
```

Reference it from a question/option via `"glossaryKey": "my_term"`.

## Webflow embed

`npm run build` emits an IIFE bundle (`dist/ill-configurator.js` + CSS) that
exposes a global mount function and inlines React, so it is self-contained.

```html
<!-- 1. Mount point on the Webflow page -->
<div id="ill-configurator-root"></div>

<!-- 2. Built assets (host them and reference the URLs) -->
<link rel="stylesheet" href="/path/to/ill-configurator.css" />
<script src="/path/to/ill-configurator.js"></script>

<!-- 3. Mount (auto-mounts if #ill-configurator-root exists; or call manually) -->
<script>
  // Optional explicit mount; pass config or read window.ILL_CONFIGURATOR_CONFIG
  window.IllConfigurator.mount('ill-configurator-root', {});
</script>
```

- Tailwind's Preflight is **disabled** and all utilities are **scoped to
  `#ill-configurator-root`** (see `tailwind.config.js`), so the widget's styles
  do not leak into the host Webflow page, and a scoped reset lives in
  `src/index.css`.
- The mount target is forced to `id="ill-configurator-root"` so the scope always
  applies even if a different selector is used to locate it.

## Known data gaps (configurator heuristics, **not** ERP values)

These are clearly labeled in the data/content files and must not be presented as
ERP spec values:

- **Fixture purpose → lumens/ft band** — defined in `questions.json#lumensBands`
  (accent ≈ 150–300, task ≈ 300–500, ambient ≈ 500+ lm/ft). Used for ranking only.
- **Light type** — inferred from the `led_package` name (no first-class field).
- **IP rating** — stored directly on seed product records (indirect in ERP).
- **CRI 95+** — shown but flagged "limited availability"; not verified in data.
- **Operating temp** — free-text on tape in ERP; optional/informational here.
