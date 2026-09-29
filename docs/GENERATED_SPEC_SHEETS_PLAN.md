# Generated Spec Sheets and Submittals — Investigation and Plan

Status: **Phase 0 complete locally; Frappe Cloud probe pending** · Prepared 2026-09-29 · Updated 2026-09-29 (Phase 0 results, §15)

## 1. Goal

ERPNext becomes the only source for every standard-product spec sheet. After a product is authored
in the YAML Builder, imported, and its assets are uploaded, the system can:

1. **Generate the catalog spec sheet** (the document published on Webflow) whenever the product
   data changes, replacing InDesign for standard products.
2. **Generate a focused spec submittal** for any configured build on a fixture schedule. It uses
   the same design, cut down to the selected configuration, and fills the missing information from
   the fixture template and Webflow product.

This retires the fillable-PDF submittal templates (`spec_submittal_template`) and the per-template
PDF field mappings (`ilL-Spec-Submittal-Mapping`, `ilL-Neon-Submittal-Mapping`, and the others).

### Decisions already made

| # | Decision |
|---|---|
| 1 | Omit the per-lens / per-CCT delivered-lumens page (page 2 of some linear sheets). Integrators don't need it. |
| 2 | Generated sheets fully replace InDesign for standard products. |
| 3 | Output must **match the InDesign design exactly** (fonts, sizes, positions, colours, rules, imagery). |
| 4 | Drawings, icons and photos are uploaded into ERPNext DocTypes and pulled from there. |
| 5 | Focused submittal = **option (b)**: spec table cut down to the selection, plus the actual part number, manufactured length, runs, total watts and chosen power supply. Project name, fixture type and location are filled in. |
| 6a | **Dimming** = every protocol supported by any approved driver in `ilL-Rel-Driver-Eligibility` for the template. |
| 6b | Footer date code = `MMDDYY` + the initials of the person responsible for the document (existing convention, e.g. `031026RY`). |
| 6c | Footer email is **sales@ilLumenate.lighting**. |
| 7 | ilLumenate branding first. The design must accept a second brand (206 Lighting: own logo, colours, footer) later without template changes. |
| 8 | Order: linear fixtures, LED tape, LED neon, extrusion kits; then LED sheets, drivers, controllers. |
| 9 | The `custom_image_*` Webflow Product fields (added through Customize Form) hold local paths on the designer's Mac. They get real ERPNext homes. |
| 10 | **ERPNext is the source of truth** where it and a published PDF disagree (e.g. operating temperature). |
| 11 | Low-transmission lenses use brighter tape to reach the same delivered output: white ≈ 56 %, black ≈ 32 %, frosted/clear ≈ 99 % transmission (§9.1). |
| 12 | Catalog sheets show the same output columns as today. ERPNext keeps the extra levels so columns can be added later without data work. |
| 13 | **Custom finish (CU, "Provide RAL #") and Outdoor (O)** are standard options on every linear fixture and extrusion kit. |
| 14 | Feed directions and feed lengths vary by product and come from a child table on the template (§3.8). |
| 15 | Defaults accepted for every open item in §14. |
| 16 | **Horticulture** LED packages use the **Static White** spec line and logo. |
| 17 | **Tape behind a lens = closest delivered output** (§9.1). Implemented in the configurator engine and the Webflow lens map (`api/tape_selection.py`). |
| 18 | Missing designer assets use flagged placeholders until supplied and verified. |

---

## 2. What exists today

### 2.1 How documents are produced now

| Output | Path | Mechanism |
|---|---|---|
| Catalog spec sheet | InDesign data merge → PDF uploaded to Webflow Product `documents` | `api/spec_sheet_export.py` builds a flat CSV (≈622 fixed columns) that InDesign merges; images come from the `custom_image_*` local paths |
| Schedule spec submittal | `portal/packets.py::gather()` → `api/spec_submittal.py::generate_filled_*` | Fills AcroForm fields in `spec_submittal_template` using mapping rows |
| Webflow "Download Spec Sheet" | `api/webflow_configurator.download_spec_sheet` → `spec_sheet_generator.py` | Builds a preview configured record, then uses the same fillable-PDF path |
| LED sheet public download | `api/public_sheet.generate` | Same fillable-PDF path |
| Extrusion kit submittal | **None.** Kits save their configuration as JSON on the schedule line (`variant_selections`), and `gather()` has no kit branch | — |

### 2.2 Useful existing pieces

- **The data aggregation is already about 70% built.** `spec_sheet_export._collect_product_data`,
  `_collect_variant_rows`, `_collect_pn_builder_columns` and the tape/neon equivalents already compute:
  - per-lens wattage and max-run tables
  - input voltage strings (`24VDC (Power Supply: 120VAC-277VAC)`)
  - operating temperature in °F/°C, production interval, bend diameters
  - part-number builder columns
- **Webflow Product also computes specs** (`calculate_specifications`, `_get_output_levels_lens_map`).
  `api/webflow_export.py` has a third copy of similar logic. These must converge on one source (Phase 1).
- **Sealed engineering values.** Configured builds carry `build_snapshot_json` with
  `engineering_sources` (`api/engineering_sources.py`). A regenerated submittal therefore uses the
  values the build was saved with, not whatever the masters say today.
- **Useful fields already exist:** `ilL-Attribute-CCT.hex_color`,
  `ilL-Attribute-Lens Appearance.transmission`, and `ilL-Attribute-Certification.badge_image`.
- **The YAML Builder v2 reads DocType JSON directly** (`tools/fixture_builder/catalog_schema.py`,
  `tools/yaml_builder_ui`). Every field this plan adds appears in the builder and CLI once the schema
  snapshot is refreshed (`npm run schema`).
- **Packet provenance and a manifest already exist** (`portal/packet_manifest.py`). Generated
  documents plug into the same `source_kind` / `provenance` contract.
- **Private/public file handling** for generated downloads already exists
  (`portal/product_downloads.save_generated`).

### 2.3 Gaps

1. **No home for imagery.** There's nowhere to store cross-sections, side views, accessory
   dimensions, feed-type drawings, bend drawings, component photos, voltage/rating icons, the logo,
   or the gradient "spec line" bars. The Customize Form fields hold Mac paths, and the CAD sources
   are `.ai` files.
2. **No spec-sheet-specific copy.** Examples: the "Custom (Provide RAL #)" finish, the lens-group
   labels ("Other Lenses"), the length-rule note, and the "For use with UL Light Source" statement.
3. **No curated list of which outputs appear as columns on the catalog sheet.** See §9: ERP holds
   100–1500 lm/ft; the sheet shows 100/300/500/750/1000.
4. **No HTML-to-PDF path at design fidelity.** Frappe's default wkhtmltopdf uses a 2012 WebKit
   (no reliable flexbox/grid, weak font handling). Frappe v16 has a `chrome` PDF generator option
   (visible in the v16 schema fixture), but it hasn't been checked on the Frappe Cloud bench.
5. **Kits** have no submittal path, and Webflow Product has no kit-template link. The kit template
   links forward to Webflow Product, so that's workable.
6. **Brand-specific document settings** (logo, footer, colours) don't exist on `ilL-Webflow-Brand`.

---

## 3. Sheet anatomy → data sources

Measured from the supplied PDFs and InDesign files (see Appendix A for exact metrics).

### 3.1 Shared chrome (every page, every family)

| Element | Source (new fields marked **new**) |
|---|---|
| Hero image (144×144pt, rounded) | Webflow Product **`spec_hero_image`** (new; today `custom_image_hero` → a TIF on the Mac) |
| Title (2 lines, Manrope Bold 20pt) | Webflow Product `product_name`, with an optional **`spec_title_line_break`** hint |
| Sublabel ("SURFACE", "DUAL-BENDING NEON") | Webflow Product `sublabel`, uppercased |
| Logo (top right, 112×72pt) | Brand document profile, **one logo per product line** (InDesign links `ilLumenate Logo_SW_Black_Main`, `…_DW_Black_Main`, …) |
| Spec line gradient bars (full-bleed, y=130.34pt and y=704.41pt; bottom mirrored) | **Vector gradient per product line** (SW, DW, TW, FS, CC, PS, OTHER), extracted from the InDesign files into `api/spec_sheets/spec_lines.json` (§15.4) |
| Icon row (24V DC, Dry/Damp/Wet, UL) | Derived; see §3.2 |
| Footer: PROJECT NAME / FIXTURE TYPE / LOCATION | Blank on catalog sheets; filled on submittals |
| Footer address, phone, email, © year | Brand document profile (email **sales@**); © year = generation year |
| Page x/y | Computed; this fixes St. Helens being numbered 1/4, 3/4, 4/4 |
| Date code (`031026RY`) | Revision date + responsible person's initials (§7) |

### 3.2 Icon row and certification statement

| Icon | Rule |
|---|---|
| Voltage (5/12/24/120V DC) | Tape spec `input_voltage` → `ilL-Attribute-Output Voltage` **`spec_icon`** |
| Dry / Damp / Wet rated | Environment ratings the product supports → `ilL-Attribute-Environment Rating` **`spec_icon`** |
| UL / ETL | Linked certifications → existing `badge_image`, plus **`spec_sheet_placement`** (`Icon Row` or `For use with … Light Source statement`) |

Today "24V DC", "Dry Rated", "Damp Rated" and "Wet Rated" are modelled as *certifications* on the
St. Helens Webflow Product. Deriving them from engineering data keeps icons correct when a product
gains or loses a rating. Those pseudo-certifications can then be dropped.

### 3.3 Linear fixture (St. Helens [SF] Static White)

| Section | Content | Source |
|---|---|---|
| **Specifications** | Output columns | Fixture output levels chosen for the sheet (**new** curated list, §9) |
| | Fixture Wattage / Max Run rows per lens group | Existing per-lens computation (tape offering × lens `transmission` → W/ft, max run). Lenses whose rows are identical collapse into one group ("Other Lenses") automatically; group label from **`spec_group_label`** on the lens attribute |
| | Light Color (CCT) + gradient | Allowed CCTs; gradient stops from `ilL-Attribute-CCT.hex_color` (swatches 27K/30K/35K/40K exist in the INDD) |
| | Color Rendering ("95+ CRI / 2-Step") | CRI + SDCM attributes via tape offerings |
| | Lenses / Mounting / Finish | Allowed options; spec labels from **`spec_label`** ("Anodized Silver") plus **`spec_note`** ("Provide RAL #") |
| | Input Voltage | Existing combined tape + driver voltage string |
| | Dimming | **Union of `input_protocols` over all active, allowed `ilL-Rel-Driver-Eligibility` rows** (decision 6a); today only the top-priority driver is used |
| | Dimensions, Production Interval, Operating Temp | Profile spec, tape offering/spec, Webflow Product temperatures |
| **Fixture Dimensions** | Cross-section + side view drawings | Profile spec drawings (§4) |
| **Accessories Dimensions** | Mounting Clip, Pivot Clip drawings | `ilL-Spec-Accessory` drawings for each mounting method in `ilL-Rel-Mounting-Accessory-Map` for this template |
| **Components** | Profile photo, LED tape photo | Profile spec photo + default tape spec photo; titles from linked Webflow product names |
| **Part Number Example** | Coloured example PN (+ power supply PN) | Default/first options from the PN builder rows; colour roles (§3.7) |
| **Part Number Builder** | Series, Dry/Wet, CCT, Output, Lens, Mounting, Finish, Length, Start/End feed direction + length | `ilL-Child-PN-Builder-Row` on the fixture template, feed lengths from `ilL-Child-Webflow-Feed-Length`, feed directions from allowed options |
| **Length note** | "built as close … 1.31" (33.3mm) production interval … longer than 78in …" | Template text with variables: production interval, `assembled_max_len_mm` |
| **Power Supply** | PS builder | Driver template linked through eligibility (shared block across families) |

### 3.4 LED tape (Static White HD)

As for linear, except:
- Output columns: tape output levels, with rows **Watts per Foot**, **Max Run Length** and **Max Footage per 100W Supply** (the existing `MAX_FOOTAGE_100W` logic).
- Adds **Beam Spread**, **Mounting** (3M Adhesive Backing), **Finish** (White PCB), **Warranty**.
- Dimensions come from a tape drawing with the cut interval.
- The header uses the unframed, bleeding hero variant.
- PN builder comes from the tape-neon template options.

### 3.5 LED neon (Glacier: Cowlitz [DB])

- Single-output spec table (Output, Watts per Foot, Max Run, Max Footage per 100W).
- Adds **Minimum Bending Diameter** (side/top from the template), **Production Interval**: "Free-Cutting" (`is_free_cutting`), **Warranty**.
- **Dimensions page:** End / Back / Side feed drawings (one per allowed feed direction) and Side/Top bend drawings.
- **Mounting Accessories list:** `ilL-Rel-Mounting-Accessory-Map` rows (`template_type = ilL-Tape-Neon-Template`) → item code + spec label.
- **PN builder:** IP rating, CCT, output, finish, length, start/end feed (B/E/L/R + lengths).
- The length note is family-aware. The current neon PDF wrongly says "channel and lens"; generated text won't.

### 3.6 Extrusion kit (St. Helens [SF] Extrusion Kit)

- **Spec table:** Lenses, Mounting, Finish, Dimensions, Operating Temperature.
- **Dimension drawings:** profile cross-section and mounting clip.
- **PN builder:** `KIT-SH01`, Length (2M), Lens, Finish, Mounting. Data from `ilL-Extrusion-Kit-Template.allowed_options` and the stock lengths.
- **Components page:** four cards (profile, lens, mounting, endcaps), each with a photo, a part-number stem (`CH-SH01-`, `LNS-SH01-`, `ACC-SH01-`, `EC-SH01-`) and its option list. Built from the kit profile/lens/mounting/endcap maps and each component spec's photo.
- **Blue-grey** spec line and the Onest font on the components page (as measured).

### 3.7 Part-number colour roles (measured)

| Role | Colour | Used for |
|---|---|---|
| Configurable product segments | `#FDAD0D` | Series and option codes |
| Length / feed segments | `#00588C` | Length, start feed, end feed |
| Power supply segments | `#AC212A` | PS builder |
| Separators and labels | `#231F20` | Dashes, option labels |

Each `ilL-Child-PN-Builder-Row` section gets a **`color_role`** (Product / Length-Feed / Power).

### 3.8 Feed options (new child table)

Feed directions and lengths differ per product, and today they are spread across Webflow
configurator rows (`feed_lengths`) and allowed options. Add **`ilL-Child-Feed-Option`** to the
fixture template and the tape/neon template:

| Field | Type | Notes |
|---|---|---|
| `position` | Select `Start`/`End` | |
| `kind` | Select `Direction`/`Length` | |
| `feed_direction` | Link → `ilL-Attribute-Feed-Direction` | Direction rows (E, B, L, R, Endcap) |
| `length_ft` | Float | Length rows |
| `code` / `label` | Data | What the PN builder prints ("E — End", "2 — 2ft", "C — Endcap", "Blank — Endcap") |
| `is_default`, `display_order`, `is_active` | | |

The PN builder, the Webflow configurator payload and the engine's feed validation all read this one
table. The St. Helens sheet (start E/B; end E/B/C; lengths 2/5/10/15/20/25 ft) and the Cowlitz sheet
(B/E/L/R; lengths 2–30 ft) become two sets of rows instead of hand-typed columns.

---

## 4. Asset model (where every image lives)

Principle: **an asset belongs to the record it depicts**, so it's uploaded once and reused. For
example, the St. Helens profile cross-section appears on the fixture, kit and submittal sheets. The
HD tape photo appears on the tape sheet and on every fixture's components section.

Add one reusable child table, **`ilL-Child-Spec-Asset`**:

| Field | Type | Notes |
|---|---|---|
| `asset_role` | Select | `Hero`, `Product Photo`, `Cross Section`, `Side View`, `Dimension Drawing`, `Feed Drawing`, `Bend Drawing`, `Accessory Drawing` |
| `file` | Attach | Public file; SVG for drawings and icons, PNG/JPG for photos |
| `title` | Data | Caption shown above the drawing ("Side View", "Mounting Clip", "End Feed") |
| `feed_direction` | Link → `ilL-Attribute-Feed-Direction` | Feed drawings only |
| `bend_axis` | Select `Side`/`Top` | Bend drawings only |
| `display_order` | Int | |
| `sha256` | Data (read only) | Set on upload; used by the fidelity and revision fingerprints |

Add it as a `spec_assets` table on:

| DocType | Typical assets |
|---|---|
| `ilL-Webflow-Product` | Hero (also add a `spec_hero_image` shortcut field) |
| `ilL-Spec-Profile` | Cross Section, Side View, Product Photo |
| `ilL-Spec-Lens` | Product Photo |
| `ilL-Spec-Accessory` | Accessory Drawing, Product Photo (plus a `spec_title` field, e.g. "Pivot Clip") |
| `ilL-Spec-LED Tape` | Product Photo, Dimension Drawing |
| `ilL-Tape-Neon-Template` | Feed Drawing (per direction), Bend Drawing, Cross Section |
| `ilL-Extrusion-Kit-Template` | Hero override, component photos (endcap set) |

Icons and branding live on masters: `spec_icon` on Output Voltage and Environment Rating (the designer's
`Rating_*_GrayLine.svg` files are 72-unit artboards drawn at 24.55pt, so icon size is a layout token);
`badge_image` (existing) on Certification; logo and spec lines on the brand profile (§8).

**Mapping from today's Customize Form fields:**

| Current field | New home |
|---|---|
| `custom_image_illumenate_logo`, `custom_image_spec_line` | Brand document profile |
| `custom_image_hero` | Webflow Product `spec_hero_image` |
| `custom_component_1..3_*` | Derived from the template's profile/tape/lens specs (Product Photo) |
| `custom_image_*_icon` (ETL, UL, voltages, Dry/Damp/Wet) | Certification / Output Voltage / Environment Rating masters |
| `custom_image_dimensions_1..5`, titles | Profile or tape-neon template `spec_assets` |
| `custom_acc_1..5_*` | `ilL-Spec-Accessory.spec_assets` |

Once every product has migrated, the Customize Form fields are removed, and the InDesign CSV export
(`spec_sheet_export.py`) either becomes a thin wrapper over the new sheet model or is retired.

### 4.1 Asset format rules

- **Drawings (`.ai` today):** Export as **SVG with text converted to outlines**, or as **PDF**; a
  PDF is converted to SVG at upload with PyMuPDF.
  - Why: an SVG loaded with `<img>` can't use the page's web fonts, so live text in the SVG would
    fall back to a system font and break "exact match".
  - Alternative: keep live text, and the renderer inlines the SVG and applies the Manrope/Poppins
    `@font-face`. That keeps drawings searchable but requires the SVG to reference the same font
    family names.
- **Photos (TIF today):** Upload as PNG/JPG at ≥300 dpi at printed size: 144pt hero = 2 in → 600 px.
  The 601×601 px hero embedded in today's PDF confirms this. Browsers can't render TIF, so the
  uploader converts TIF with Pillow (already a dependency).
- **CC Library assets** (the UL icon and the "Dark Gray Sparkle" logo in the INDD links) must be
  exported once and uploaded to their master records.
- **FPO marks:** marketing flags placeholder ("for position only") content with the InDesign
  `C=0 M=100 Y=0 K=0` magenta swatch. The renderer refuses SVG artwork that still contains that
  magenta (`svg.reject_fpo`), and the asset importer will apply the same check at upload, so
  placeholder art cannot reach a published sheet. Everything else uses the standard colours.
- Uploads are validated with the existing `portal/file_validation.validate_content`, and each
  `sha256` is recorded.

---

## 5. Architecture

```
            YAML Builder ──► CSV + asset pack ──► ERPNext import (+ asset importer)
                                                        │
                                                        ▼
  ┌────────────────────────── Spec Sheet Model (pure Python) ──────────────────────────┐
  │ build_catalog_model(webflow_product, brand)                                        │
  │ build_submittal_model(build_ref, schedule_context, brand)                          │
  │   • product facts   ← one shared spec-facts module (replaces the 3 copies)         │
  │   • build facts     ← sealed build_snapshot_json / engineering_sources             │
  │   • assets          ← spec_assets tables + masters                                 │
  │   • brand           ← document brand profile                                       │
  │ → JSON-serialisable "sheet model" + content fingerprint                            │
  └────────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                                                        ▼
          SVG page description: measured tokens, baseline-placed text (pages.py)
                                                        │
                                                        ▼
                        Renderer (Chrome headless) ──► PDF bytes
                                                        │
          ┌─────────────────────────────┬───────────────┴──────────────┬──────────────────────┐
          ▼                             ▼                              ▼                      ▼
  Catalog revision (approve)   packets.gather() submittals   Webflow configurator download   Public LED sheet
  → Webflow Product documents  (replaces fillable PDFs)      (replaces fillable PDFs)
```

### 5.1 Sheet model (`api/spec_sheets/model.py`)

- A **pure function** of its inputs: no writes, no permissions, no commercial fields. This keeps the
  existing `_commercial_source_blocked` guarantee: the model never reads price, cost or customer data.
- The output is a typed dict: `header`, `icons`, `spec_rows`, `sections[]`, `pn_builder`,
  `power_supply`, `footer`, `assets[]`, `revision`.
- The **content fingerprint** is the SHA-256 of the canonical model plus the asset hashes plus the
  template version. It drives catalog revision detection and caching.
- **Families:** `linear.py`, `tape.py`, `neon.py`, `kit.py`, then `sheet.py`, `driver.py`,
  `controller.py`. Each has a catalog builder and a submittal builder.
- **Unit tests** run without Frappe (the repo already uses Frappe doubles in `tests/portal_unit`),
  with golden JSON models for the four sample products.

### 5.2 Shared spec facts (`api/spec_sheets/facts.py`)

Extract the calculations now spread across `spec_sheet_export.py`, `ill_webflow_product.py`
(`calculate_specifications`, `_get_output_levels_lens_map`) and `webflow_export.py` into one module:

- per-lens / per-output wattage and max run
- voltage strings
- temperature formatting
- dimming union
- feed options
- PN builder columns

Webflow Product, the CSV export and the sheet model all call it. The first PR is a pure refactor
with characterization tests, so the website and the sheet can never disagree again.

### 5.3 Page description and design tokens (built in Phase 0)

Phase 0 replaced the HTML/CSS template idea with a **point-accurate SVG page description**, because
it matches InDesign's model: every element sits at an absolute position, and text is placed by
baseline.

- `api/spec_sheets/tokens.py` holds the measured tokens (Appendix A): page size, margins, text styles
  (font, size, InDesign tracking, colour role), chrome positions, table metrics and the CCT gradient.
- `api/spec_sheets/svg.py` provides `Page` primitives: `text` (baseline, `start`/`middle`/`end`
  anchor), `line`, `circle`, `image` (rounded clip, mirroring), `gradient_rect`. `document()`
  assembles one self-contained HTML file with one inline SVG per page and data-URI fonts and images.
- `api/spec_sheets/pages.py` contains the layout functions: `page_chrome`, `icon_row`, `spec_table`,
  `drawings`. Family pages are compositions of these. Later phases add PN builder, power supply,
  component cards, accessory grid, feed drawings and the focused submittal table.
- `api/spec_sheets/text.py` measures text from `fonts/metrics.json`, a HarfBuzz shaping table built by
  `tools/spec_sheets/build_font_metrics.py`. This is used for right-aligned composites (footer bullets,
  the "For use with … Light Source" statement), overflow checks and future wrapping, without a
  shaping library on the server.
- **Why SVG and not HTML boxes:** Chrome rounds font ascent and descent to whole pixels, so an HTML
  box's baseline moves by up to 0.4pt depending on font and size. SVG `<text y>` is the baseline:
  measured error 0.014pt.
- **Tracking:** InDesign tracking becomes SVG `letter-spacing`. Chrome turns off ligatures when
  letter-spacing is set, but InDesign keeps them (Manrope's `t_t` in "Wattage"), so pages set
  `font-feature-settings: 'liga' 1`.
- **Fonts** are bundled under `api/spec_sheets/fonts/` (Poppins 4.004, the version InDesign used;
  Manrope and Onest as static instances of the Google Fonts variable fonts; all OFL, licences
  included). Menlo and Minion Pro are not bundled; the "×" uses Poppins (approved default).
- **Assets are sized by their own SVG dimensions**, exported 1:1 in points. The icon row, for example,
  places each icon at its natural width with a 4.9pt gap, which is InDesign's spacing.

### 5.4 Renderer (decided in Phase 0)

`api/spec_sheets/render.py::render_pdf(html) -> bytes` runs a **pinned Chrome for Testing
headless shell** with `--print-to-pdf`.

- **Frappe's own Chrome print path is not used.** Frappe v16's Chrome generator (#35812) is built
  for Print Formats: without a header/footer it forces 15 mm margins, and it rounds "Letter" to
  216 × 279 mm. Spec sheets need a full-bleed 612 × 792pt page.
- **Frappe's default Chromium (133) is not used either.** Chrome 136 and earlier embed `@font-face`
  fonts as **Type 3** glyph procedures, not as the real fonts. Bisected on this project's page:
  134/135/136 → Type 3, 137/141 → TrueType. So the renderer pins **141.0.7390.54**. It downloads the
  build once per bench into `<bench>/chromium-spec-sheets/<version>/`, verifies its SHA-256 and
  unpacks it with path checks. Frappe's Chromium and Print Formats are untouched.
- **Lookup order:** `ILL_SPEC_SHEET_CHROMIUM` (local tools/CI), the site-config key
  `spec_sheet_chromium_path`, then the pinned build. The download happens only in a background job,
  never inside a web request.
- **Security:** a Content-Security-Policy is injected as the first `<head>` element: no scripts, no
  network, no file access; only inline styles and data-URI images and fonts. (Chrome's
  `scriptEnabled=false` switch silently stops `--print-to-pdf`, so the policy does this job instead.)
  A test proves an inline script and an external image do not load.
- **Speed:** ≈ 0.25–0.35 s per page locally, including Chromium start-up.
- **Version drift:** CI uses the runner's Google Chrome (≥ 137); the bench uses the pinned build.
  Both pass the same fidelity test.

Post-processing with pypdf (already a dependency) will set PDF metadata (title, author = brand,
subject = revision code) and merge into packets as today.

### 5.5 Catalog revisions and publishing

New DocType **`ilL-Spec-Sheet-Revision`**:

| Field | Purpose |
|---|---|
| `webflow_product`, `brand` | Scope |
| `content_fingerprint`, `template_version` | Change detection |
| `status` | `Draft` → `Approved` → `Published` / `Superseded` |
| `file` | Generated PDF (public once approved) |
| `date_code` | `MMDDYY` of approval + approver initials (e.g. `092926KS`) |
| `approved_by`, `approved_on` | Replaces the designer's manual QA |
| `model_json` | Frozen sheet model, for audit and diffing against the next revision |
| `diff_summary` | Human-readable changes since the previous revision |

**Flow:**
1. A save on any contributing record (Webflow Product, template, specs, relevant masters, driver
   eligibility) enqueues a background fingerprint check.
2. If the fingerprint changed, a `Draft` revision is rendered. Staff see a preview and a
   "what changed" diff on the Webflow Product form.
3. **Approve** stamps the date code and initials. The PDF is then attached to Webflow Product
   `documents` as `Spec Sheet` (replacing the previous one) and published through the existing
   revision-fenced publication pipeline (`api/publication.py`, n8n).

Adding a "catalog spec sheet is approved and current" readiness check to `api/product_readiness.py`
means a product can't publish with a stale sheet.

### 5.6 Focused submittals

`portal/packets.gather()` already dispatches per family. Plan:

- Replace each `generate_filled_*` renderer with `spec_sheets.render_submittal(build_ref, …)`.
  Keep the same return contract (`success`, `file_url`, `provenance`), with
  `source_kind = "generated_submittal"`.
- **Add a kit branch:** lines with `product_type = "Extrusion Kit"` and `variant_selections` JSON.
- Webflow downloads (`spec_sheet_generator.py`) and `public_sheet.generate` call the same function
  with an unsaved preview build, as today.
- Provenance records the model fingerprint, the build's `config_hash`, the template version and the
  asset hashes. This replaces `mapping_hash`.

---

## 6. Focused submittal content (option b)

**Page 1:** header, icon row and footer as on the catalog sheet, with the footer lines filled from
schedule, project and line (`FIXTURE TYPE` = line ID). The existing submittal INDD already has this
layout with an empty value column; it is the layout reference. The single-column spec table
contains:

| Row | Linear | Tape / Neon | Kit |
|---|---|---|---|
| Part Number | Full configured PN (colour-coded segments) | ✓ | ✓ |
| Output | Selected delivered lm/ft | Selected lm/ft | — |
| Light Color (CCT) | Selected CCT (single gradient cell) | ✓ | — |
| Color Rendering | ✓ | ✓ | — |
| Lens | Selected | Selected (neon lens, if any) | Selected |
| Mounting / Finish | Selected (spec labels) | Selected | Selected |
| Fixture Wattage | W/ft for selected output × lens | W/ft | — |
| Total Wattage | `total_watts` | `total_watts` | — |
| Requested / Manufactured Length | `requested_overall_length_mm` / `manufacturable_overall_length_mm` (in and mm) | requested / manufacturable | Kit length (2M) |
| Runs | `runs_count` (+ segments summary for multi-segment) | `total_segments` | — |
| Feed | Start/end direction + leader length | Feed direction / type | — |
| Max Run Length | For the selection (with override if enabled) | ✓ | — |
| Power Supply | Chosen driver PN(s) × qty from `drivers` / power plan | From `power_plan_json` | — |
| Input Voltage, Dimming, Dimensions, Production Interval, Operating Temp | From build snapshot / masters | ✓ | Dims, temp |

**Remaining pages:** only the relevant items are kept.
- The fixture dimensions drawing.
- The **selected** mounting accessory drawing.
- The component photos.
- A **"Your Part Number"** block in place of the PN example and builder: one column per PN
  section, showing the selected code and its label.
- For kits, the component cards list only the resolved component part numbers.

Grouped fixtures (`ilL-Configured-Group`) and LED sheets follow in their phases, reusing the same
sections.

---

## 7. Date code

- **Catalog sheet:** `MMDDYY` of the approval date + the approver's initials (from a new
  **`document_initials`** field on User, defaulting to first/last initials). This matches the
  existing meaning ("when created + who made it"). The code changes only when a new revision is
  approved.
- **Submittal:** `MMDDYY` of generation + the initials of the user who generated it. Portal
  customers get the brand's default initials set on the brand profile, to avoid putting customer
  initials on an ilLumenate document. Provenance keeps the exact timestamp and user.

---

## 8. Branding (ready for 206 Lighting)

Add a **Document Branding** section to `ilL-Webflow-Brand` (one row per brand):

- `document_logos`: one logo per product line (SW, DW, TW, FS, CC, PS, OTHER)
- `spec_lines`: gradient stops per product line (JSON), seeded from `spec_lines.json`; 206 Lighting
  supplies its own stops rather than images
- `document_address_line`, `document_phone`, `document_email` (sales@), `copyright_holder`
- `accent_product` (`#FDAD0D`), `accent_length` (`#00588C`), `accent_power` (`#AC212A`), `text_color` (`#231F20`), `muted_color` (`#A2ABB6`), `rule_color` (`#D1D6DB`)
- `document_font_heading` / `document_font_body` (default Manrope / Poppins)
- `default_document_initials`

Templates read only tokens from the brand, never literals. A 206 Lighting sheet is then a data
change plus a one-time visual QA pass. Product-level brand overrides (a different hero or product
name per brand) can use the existing `target_brands` rows later if needed.

---

## 9. Data reconciliation findings (St. Helens [SF] Static White)

Comparing the supplied Webflow Product export with the InDesign PDF shows that **the generated sheet
prints what ERPNext says**. Decisions received on 2026-09-29:

| Item | ERPNext today | Current PDF | Resolution |
|---|---|---|---|
| Operating temperature | −40 °C to 65 °C | −20 °C to 45 °C | **ERPNext wins**; generated sheets print −40 °F (−40 °C) to 149 °F (65 °C) |
| Output columns shown | 100–1500 incl. 200/250/400 | 100/300/500/750/1000 | **Keep today's columns** via `show_on_spec_sheet` on the template's output levels; extra levels stay in ERPNext for later |
| White / black lens wattage | see §9.1 | 1.7 W / 2.5 W at 100 lm/ft | Brighter tape behind low-transmission lenses (decision 11); **rule to confirm, §9.1** |
| Finishes | SV/BK/WH | + **CU (Provide RAL #)** | **Standard on every linear fixture and kit**: add the Custom finish option with `spec_note` "Provide RAL #" |
| Dry/Wet | Only `I — Dry` | `I — Indoor`, `O — Outdoor` | **Outdoor is standard on every linear fixture and kit**: add the option |
| Feed directions / lengths | B/E/L/R(/CAP); 2–30 ft | E/B(/C); 2–25 ft | **Per product**, from the new feed options table (§3.8) |
| Dimming | TRIAC/ELV/0-10V (attribute links) | + DMX, DALI, Bluetooth | Union of all approved drivers in `ilL-Rel-Driver-Eligibility` (decision 6a) |
| Icon row / UL | "24V DC", "Dry/Damp/Wet Rated" modelled as certifications; no UL cert | UL "For use with … Light Source" | Model per §3.2 |
| Hero image | `featured_image` = `SH01_LIT.jpg` (website) | `SH01 Hero Image - TIF` | New `spec_hero_image` |

A **data readiness report** (Phase 2) lists gaps like these per product before its first generated
revision is approved.

### 9.1 Which tape sits behind each lens

The published St. Helens sheet follows one rule exactly. For each output column, choose the tape
whose **delivered output (tape lm/ft × lens transmission) is closest to the column value**, and
print "—" when the best tape misses by more than about 15 %. With 56 % (white), 32 % (black) and
≈ 99 % (frosted/clear) transmission this reproduces every wattage and every "—" on the sheet.

The configurator engine (`configurator_engine.py`, `auto_select_tape_offering`) uses a different rule.
It snaps each tape's delivered output to the nearest fixture level, then picks the **highest-output**
tape among those that snap to the selected level. With the fixture levels in the St. Helens export
and 56 % / 32 % transmission, the two rules disagree in two cells:

| Column | Published sheet (closest) | Engine today (highest that snaps) |
|---|---|---|
| White lens, 750 lm/ft | 1250 lm/ft tape → 700 delivered, 11.6 W/ft | 1500 lm/ft tape → 840 delivered, 14.4 W/ft |
| Black lens, 100 lm/ft | 300 lm/ft tape → 96 delivered, 2.5 W/ft | 400 lm/ft tape → 128 delivered, 3.6 W/ft |

The Webflow configurator's lens map (`_get_output_levels_lens_map`) showed yet another tape, the
first one that snaps (e.g. white 100 → 100 lm/ft tape).

**Resolved 2026-09-29: closest.** Which output columns exist is unchanged (a tape offers the
level its delivered output rounds to). When several tapes round to the same level, the one whose
delivered output is closest to it builds the fixture; ties go to the lower-output tape.
`api/tape_selection.py` holds the rule and is used by `get_delivered_outputs_for_template`,
`auto_select_tape_for_configuration` and the Webflow lens map, so the configurator, the website and
the spec sheet agree. It reproduces every wattage and "—" on the published St. Helens sheet
(`tests/portal_unit/test_tape_selection.py`). Transmission is read as a fraction (0.56); a percent
(56) is now also understood. Builds already saved keep their sealed tape. New quotes for white 750
and black 100 lm/ft (and similar cells on other templates) now select the lower-wattage tape.

The published max-run values also differ slightly from the tape sheet in five cells (e.g. 36 ft vs
35 ft for 200 lm/ft tape). Generated sheets print the engine's computed max run.

## 10. YAML Builder, import and asset upload

1. **Schema:** new fields and tables appear in the builder automatically after `npm run schema`.
   `catalog_examples.py` gains spec-sheet examples for each family.
2. **Asset references in YAML:** Attach fields accept a **relative asset path**
   (`assets/st-helens/SH01_cross_section.svg`). The CLI:
   - checks that the file exists and has an allowed type
   - computes its SHA-256
   - copies it into `output/<catalog>/assets/`
   - writes `assets_manifest.json` (path → sha256 → target DocType/field/row)
   - writes the CSV cell as the final public URL `/files/spec-assets/<sha8>-<name>`
3. **Asset importer** (a new whitelisted staff method plus a Desk page, "Import Spec Asset Pack"):
   takes the zip and manifest, validates every file, creates public `File` records at the exact
   manifest URLs (idempotent by sha256), converts TIF to PNG and PDF to SVG, and reports anything
   missing. It **runs before the CSV import**, so Attach values resolve.
4. The **`IMPORT.md`** the builder generates gets the new first step: "Import the asset pack".
5. **Updates to existing products:** re-running the asset importer is idempotent. Changed files get
   new sha-based URLs, so old revisions keep their exact assets. Record updates go through the
   ERPNext update workflow noted in `CATALOG.md`.
6. **Stop generating** `ilL-Spec-Submittal-Mapping` / `ilL-Neon-Submittal-Mapping` CSVs once a
   family is on generated documents (`gen_spec_submittal_mapping.py`,
   `gen_neon_submittal_mapping.py`, `gen_led_sheet_submittal_mapping.py`).

---

## 11. Proving "exact match"

A **fidelity harness** (`tools/spec_sheets/fidelity.py`, built in Phase 0) compares a generated PDF with the InDesign "golden" PDF:

1. **Text geometry:** every text span matched by content must use the same font family and weight,
   the same size (±0.05pt), the same colour (exact hex), and the same baseline and x-position
   (±0.5pt). This uses PyMuPDF span extraction, the same method used for Appendix A.
2. **Images and rules:** the same bounding boxes (±0.5pt), rule widths and colours.
3. **Raster diff:** both PDFs rendered at 150 dpi; the per-page changed-pixel ratio must stay below
   an agreed threshold, and a highlighted diff image is produced for review.
4. **Goldens:** the four supplied PDFs, re-exported from InDesign **after** the data is reconciled
   (§9), so the goldens and ERPNext agree. Otherwise the harness measures data drift, not layout.

Text inside drawing and icon boxes is artwork, so it is covered by the raster check only. Approved
content changes are listed per fixture (`approved_differences`); where one changes a string's width
(sales@ vs info@), the rest of that line may move sideways.

The harness runs in CI (`b2b-contracts.yml`, "Generated spec sheet matches the InDesign golden")
against local fixtures, and against staging-generated PDFs during rollout. Sign-off per family is:
harness green + designer visual approval.

Known deliberate differences, listed for approval: corrected page numbering, sales@ email, family-
correct length note, generated © year, and Menlo "×" replaced with the Poppins glyph if that is
approved.

---

## 12. Phased delivery

Sizes are relative (S ≈ days, M ≈ 1–2 weeks, L ≈ 2–4 weeks of focused work).

### Phase 0 — Feasibility spike (S) — done locally, Cloud probe pending
- ✅ Renderer decided and built (§5.4): pinned Chrome for Testing 141 headless shell, exact page
  size, CSP-locked; Frappe's Print Format path and Chrome 133 ruled out, with reasons.
- ✅ St. Helens page 1 rebuilt from a sheet model and **passes the fidelity harness** against the
  InDesign PDF (§15).
- ✅ Fonts bundled with licences; HarfBuzz metrics table; stand-in assets cut from the golden PDF
  (`tools/spec_sheets/extract_standins.py`) until the designer's exports arrive.
- ⏳ Run the probe on the Frappe Cloud bench (§15.3) to confirm the pinned Chromium downloads and
  runs there.
- ✅ Designer asset pack received (§15.4): CAD drawings, rating/certification icons and all seven
  InDesign files. The fixture now uses the real drawings and icons and still passes.
- ✅ Logos received for Static White, Dim to Warm and Full Spectrum (plus the black logo); converted
  to vector SVG in `api/spec_sheets/brands/illumenate/logos/`, placed at InDesign's 40 %.
- ⏳ Placeholders until the designer supplies them (the renderer lists every placeholder it uses,
  and Phase 2 blocks approving a revision while any remain): Tunable White logo (Static White logo
  stands in), Color Changing / Power Supply / Other Products logos (black logo stands in), the
  St. Helens spec hero (`SH01 Hero Image`, cut from the PDF) and the inline UL mark (CC Libraries:
  Icons/UL, cut from the PDF).

### Phase 1 — Foundations (M)
- `spec_sheets/facts.py` refactor, with characterization tests proving Webflow Product and CSV
  outputs are unchanged.
- New fields/tables: `ilL-Child-Spec-Asset`, `ilL-Child-Feed-Option` (§3.8), `spec_icon`,
  `spec_label`/`spec_note`/`spec_group_label`, `show_on_spec_sheet`, `color_role`, certification
  `spec_sheet_placement`, brand document fields, User `document_initials`.
- Standard options: Custom finish (CU, "Provide RAL #") and Outdoor (O) on every linear fixture and
  extrusion kit template; YAML Builder examples include them by default.
- Background job (after migrate) that installs the pinned Chromium, so no request waits on it.
- Patches: seed the ilLumenate brand document profile. Also migrate existing `custom_image_*` data
  where a value is already an ERPNext `/files/` URL; Mac paths are reported, not copied.
- YAML Builder schema refresh, examples, asset-path support, asset pack output; asset importer.

### Phase 2 — Linear fixture catalog sheet (L)
- Sheet model, templates, CSS tokens, renderer integration.
- Data readiness report (§9) and St. Helens reconciliation with engineering.
- `ilL-Spec-Sheet-Revision`, the approve flow, and Webflow `documents` publishing plus the readiness
  check.
- **Exit:** St. Helens catalog sheet passes the fidelity harness and is published from ERPNext.

### Phase 3 — Linear focused submittal (M)
- Submittal model and page variants, the `packets.gather` switch behind a per-template
  **`document_source`** flag (`Generated` / `Legacy PDF`), Webflow download and portal build
  documents.
- **Exit:** a schedule packet with St. Helens lines uses generated submittals; legacy templates still
  work for untouched families.

### Phase 4 — LED tape and LED neon (M each)
- Tape: multi-output table, 100W-supply footage, tape drawing, tape PN builder.
- Neon: feed-type drawings, bend drawings, mounting-accessory list, neon PN builder.
- Catalog + submittal for each, with fidelity sign-off.

### Phase 5 — Extrusion kits (M)
- Kit catalog sheet with the components page and blue-grey chrome.
- Kit submittal from `variant_selections`, plus the new `gather()` kit branch (kits currently get
  no submittal at all).

### Phase 6 — Rollout and retirement (S–M)
- Migrate every standard product (readiness report → assets → reconcile → approve).
- Flip `document_source` to `Generated` everywhere. Stop generating mapping CSVs in the builder.
- Remove `custom_image_*` Customize Form fields; retire or thin-wrap the InDesign CSV export.
- Keep the fillable-PDF code for one release as a fallback, then delete it along with the mapping
  DocTypes (after exporting their data for the record).

### Phase 7 — LED sheets, drivers, controllers (M each)
Same pattern. The driver/controller catalog sheets reuse the Power Supply builder block.

### Phase 8 — 206 Lighting branding (S)
Brand profile data + visual QA; no template changes expected.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pinned Chromium cannot download or run on Frappe Cloud (egress, missing system libraries) | The Phase 0 probe checks both; `spec_sheet_chromium_path` accepts a bench-provided binary; the HTML is self-contained, so an external render service remains a fallback |
| "Exact" match fails on text shaping (kerning, line breaks) | Absolute positioning with measured coordinates; fixed-width note blocks with explicit line breaks; harness tolerance agreed up front |
| Data disagreements surface on generated sheets | Readiness report plus the approval gate; nothing publishes without approval |
| Designer workload for asset export | Each asset is exported once per component and reused across products; batch export presets in Illustrator |
| Variable-length content overflowing a page (many outputs, long option lists) | Layout rules per section (max columns; wrap to a second table row as InDesign does); an overflow check fails the render instead of clipping |
| Performance of on-demand submittals in large packets | Cache by fingerprint (the same build + context reuses the PDF); packets already run as background jobs (`portal/packet_jobs.py`) |
| Proprietary fonts (Menlo, Minion Pro) | Substitute glyphs, noted in the approved-differences list |

## 14. Open items (non-blocking; defaults in bold)

1. Output columns on catalog sheets: **curated per template via `show_on_spec_sheet`**, or all fixture levels.
2. Asset storage: **child table on the owning record (§4)**, or a single standalone `ilL-Spec-Sheet-Asset` DocType with a dynamic link. Both keep assets in ERPNext; the child table avoids duplication.
3. SVG text: **outlined text**, or live text with inlined SVGs (searchable drawings).
4. Submittal initials for portal-generated packets: **brand default initials**, or the portal user's.
5. Catalog regeneration trigger: **automatic Draft on change + manual approve**, or fully automatic publish.

All five defaults were accepted on 2026-09-29. New item:

6. ~~Tape selection rule behind low-transmission lenses~~ **Resolved: closest delivered output** (§9.1).

---

## Appendix A — Measured design tokens (St. Helens PDF, InDesign 20.5 export)

Page: US Letter **612 × 792 pt**; outer margin **36 pt** (0.5 in).

| Element | Font | Size | Colour | Position (x, top) |
|---|---|---|---|---|
| Title lines | Manrope Bold | 20 pt, tracking 0 | `#231F20` | 198, baselines 57.32 / 81.32 |
| Sublabel ("SURFACE"), section headers | Manrope Bold | 8.78 pt, tracking +7 | `#231F20` | 198, baseline 109.98 · 36, baseline 208.98 |
| Spec labels | Manrope SemiBold | 7.8 pt, tracking −12 | `#231F20` | 37.44, baselines every **15.84 pt** from 240.40 |
| Spec values | Poppins Light | 7.8 pt, tracking −12 | `#231F20` | centred in equal columns across 192.9–576.0; baseline 0.07 above the label |
| Table rules | — | 0.25 pt stroke | `#D1D6DB` | full content width |
| CCT gradient bar | raster 384×16 pt | — | stops = CCT swatches | 192, 339 |
| Drawing callouts | Manrope Bold / Poppins Light | 7 pt | `#231F20` (accent `#0C598D`) | inside the drawing |
| "For use with … Light Source." | Poppins Light | 7.8 pt | `#231F20` | 469.4, 171.6 |
| Footer labels | Manrope Regular | 8 pt, tracking +50 | `#231F20` | 36 / 233.17 / 424.43, baseline 731.21; 108pt rules at y 731.0 |
| Footer address / notice / date code | Poppins Light | 7 pt | `#A2ABB6` | baselines 748 / 756; 2pt `#9FABB7` bullet dots, 3.85pt gap after |
| Page number | Poppins Medium | 7 pt | `#231F20` | right-aligned at 576, 740.5 |
| PN example | Manrope SemiBold | 10 pt | `#FDAD0D` / `#00588C` / `#AC212A` | centred, 207.1 / 231.5 |
| PN builder series | Manrope SemiBold | 11.7 pt | role colour | 37.8, 294.5 |
| PN builder column headers | Poppins Light | 7.8 pt | `#7F8081` | |
| PN option code / label | Poppins SemiBold / Poppins Light | 7.8 pt | `#231F20` | "code — label" with em dash |
| PN builder underline rules | — | 0.75 pt | role colour | |
| Length note | Poppins Light Italic | 5.85 pt | `#231F20` | 36–≈390 |

| Image | Box (pt) | Source pixels |
|---|---|---|
| Hero | 36,36 → 180,180 | 601×601 |
| Logo | 463.6,36 → 575.9,108 | 468×300 |
| Spec line (top) | 0,130.3 → 612,133.9 | 2550×15 |
| Spec line (bottom) | 0,704.4 → 612,708.0 | 2550×15 |

InDesign swatches present: `27K`, `30K`, `35K`, `40K`, `Darker 27K`, `Dark Gray`, `Gray`,
`Light Gray 2`, `Secondary`, `#00588C`, `Dark Red`.
Fonts referenced: Poppins (full family), Manrope, Onest (kit components page), Menlo, Minion Pro.

Tracking is in 1/1000 em, derived by comparing HarfBuzz-shaped widths with the golden spans. Row
rules sit 3.70pt below the label baseline (0.25pt `#D1D6DB`). The bottom spec line is the top image
mirrored. The hero clip radius is 14.4pt. These values live in `api/spec_sheets/tokens.py`; each new
family page is measured with `python -m tools.spec_sheets.fidelity extract <pdf> --page N`.

## Appendix B — Files this plan touches

| Area | Files |
|---|---|
| Built in Phase 0 | `api/spec_sheets/{render,probe,svg,text,tokens,pages}.py`, `api/spec_sheets/fonts/*` (+ `metrics.json`), `api/spec_sheets/fixtures/st_helens_sf_sw/*`, `api/spec_sheets/spec_lines.json`, `tools/spec_sheets/{fidelity,render_fixture,extract_standins,extract_indesign,convert_artwork,build_font_metrics}.py`, `tools/spec_sheets/tests/`, `tests/fixtures/spec_sheets/st_helens_sf_sw/{golden.pdf,fidelity.json}`, CI step in `b2b-contracts.yml` |
| New | `api/spec_sheets/{model,facts,revision}.py`, `api/spec_sheets/families/*.py`, DocTypes `ilL-Child-Spec-Asset`, `ilL-Child-Feed-Option`, `ilL-Spec-Sheet-Revision` |
| Changed | `portal/packets.py` (dispatch + kit branch), `api/spec_sheet_generator.py`, `api/public_sheet.py`, `api/webflow_configurator.py` (download), `api/product_readiness.py`, `api/publication.py` (documents), `doctype/ill_webflow_product/ill_webflow_product.py` (facts), `api/spec_sheet_export.py` (facts), attribute/spec/brand DocType JSON, `tools/fixture_builder/catalog*.py`, `tools/yaml_builder_ui` schema + examples |
| Retired (Phase 6) | Fillable-PDF paths in `api/spec_submittal.py`, `portal/pdf_mapping.py`, mapping DocTypes, mapping generators, `custom_image_*` Customize Form fields |

---

## 15. Phase 0 results (2026-09-29)

### 15.1 Fidelity: St. Helens [SF] Static White, page 1

The generated page is built from `fixtures/st_helens_sf_sw/model.json` (values transcribed from the
PDF; assets cut from the PDF as stand-ins) and compared with the InDesign export:

| Check | Result |
|---|---|
| Page size | 612 × 792pt, identical |
| Words (text, font, size, colour) | **174 / 174** match |
| Baseline position | max 0.014pt off |
| Horizontal position | max 0.37pt; mean 0.044pt; 0.2pt outside the approved footer line |
| Word width | max 0.38pt |
| Images | 5 / 5 boxes match (hero, logo, both spec lines, CCT band); after §15.4 the spec lines are vector gradients and 3 / 3 raster images match |
| Rules | 59 / 59 match (table rules, footer rules, drawing lines), none extra |
| Raster (150 dpi) | 0.57 % of pixels differ; almost all in the two approved changes below |
| Fonts in the PDF | Real subset TrueType (Manrope-Bold, Poppins-Light, …), not Type 3 |

Approved differences in this fixture: footer email **sales@** (was info@) and page count **1/3**
(the published PDF skips page 2 but prints 1/4).

Checked on three Chromium builds: Playwright Chromium 141, Chrome for Testing 141.0.7390.54 (the
pinned build) and full Chromium 141. Chrome for Testing 133 (Frappe's default) passes visually but
embeds Type 3 fonts, which is why the build is pinned.

### 15.2 Reproduce locally

```bash
pip install pymupdf
export ILL_SPEC_SHEET_CHROMIUM=/path/to/chrome-headless-shell   # or google-chrome
python -m tools.spec_sheets.render_fixture \
    illumenate_lighting/illumenate_lighting/api/spec_sheets/fixtures/st_helens_sf_sw/model.json out.pdf
python -m tools.spec_sheets.fidelity compare tests/fixtures/spec_sheets/st_helens_sf_sw/fidelity.json out.pdf --report out/
python -m unittest discover -s tools/spec_sheets/tests
```

`out/diff.png` highlights every differing pixel in red over a grey blend of both pages.

### 15.3 Run the probe on Frappe Cloud

After this branch is deployed, sign in as a System Manager, open the browser console on the site
and run:

```js
frappe.call({
  method: "illumenate_lighting.illumenate_lighting.api.spec_sheets.probe.run",
  type: "POST",
}).then((r) => console.log(r.message));
```

The first call starts a background job (long queue) that downloads the pinned Chromium (~110 MB,
SHA-256 checked) and renders St. Helens page 1; it returns `status: "running"`. Call it again after
a few minutes. A successful result reports the Chromium version, render time, page size, embedded
font names and a private `file_url` for the PDF. Download that PDF and run the §15.2 `compare`
command on it to confirm the bench output matches.

If the result is `failed`, the error names the cause (download blocked, missing system library,
timeout); the full trace is in Error Log under "Spec sheet render probe failed".

### 15.4 Designer asset pack (St. Helens)

| Asset | What it is | Result |
|---|---|---|
| `St. Helens [SF]_Spec CAD.ai` (2 artboards), `_Side View`, `_Mounting Clip`, `_Pivot Clip` | PDF-compatible Illustrator, 1:1 artboards (108, 407 × 46.8, 144, 144pt) | Converted to SVG with outlined text (`tools/spec_sheets/convert_artwork.py`). InDesign placed them at exactly (36, 559.7) and (170.1, 568.7), which gives the drawing layout rule: 1:1, left to right, 26.1pt gap, captioned drawings 9pt lower |
| `certifications/*.svg` (19 icons) | 72-unit artboards with the grey rounded tile | Rating icons used as-is at 24.55pt; they match the PDF |
| 7 InDesign files (SW, DW, TW, FS, CC, Power Supply, Extrusion Kit) | Each embeds its full-resolution `Spec Line_<LINE>.png` (2550 × 15/16px; kit 1224 × 8px) | Gradients fitted to ≤ 1 colour level (`tools/spec_sheets/extract_indesign.py`) → `spec_lines.json`. Rendered through Chrome at 300 dpi they match the PNGs to 0.6–2.3 levels on average |
| Swatches in the InDesign files | 27K `#FFC35A`, 30K `#FFFCAD`, 35K `#FFFFDC`, 40K `#F6FBFF`, 18K `#FF990A` (DW/TW), Darker 27K `#FDAD0D`, Gray `#A2ABB6`, Secondary `#00588C`, Other Products `#006833`, Light Gray `#B9C0C8` | Seed values for `ilL-Attribute-CCT.hex_color` and the brand colour roles (Phase 1) |
| `ilLumenate Lighting Logo_White_Main.svg` | White logo (all fills `#FFF`) | Not usable on white paper; stand-in kept |
| `SH01_ASSEMBLED.jpg` | A different lit product photo | Not the spec hero; stand-in kept |

**The gradient lines are built from the CCT swatches.** Static White runs 27K → 30K → 35K → 40K at
0/50/75/100 %; Dim to Warm runs the other way and ends at 18K; Tunable White alternates warm and
cool; Full Spectrum continues past 40K into blue, green and red; Color Changing runs through the
RGB hues; Power Supply fades Secondary blue into Dark Red at 26–68 % opacity; kits go Light Gray → blue
→ green. Each is a horizontal gradient (checked row by row), so it is stored as colour stops, not
an image. The renderer draws it as a vector: the top bar left to right, the bottom bar mirrored.

**Which line a product uses** comes from data: `ilL-Attribute-LED Package.spectrum_type` (Static
White → SW, Dim to Warm → DW, Tunable White → TW, RGB/RGB+W/RGBW/RGB+TW/RGBTW → CC); drivers and
controllers → PS; extrusion kits and accessories → OTHER. `spectrum_type` has no "Full Spectrum"
option yet, so Phase 1 adds it; Horticulture needs a decision.

**Fixture result with the real assets:** 174/174 words, 3/3 raster images (hero, logo, CCT band;
the two spec lines are now vectors, checked by the raster comparison), 59/59 rules,
0.58 % of pixels differ. The same as with stand-ins, so the conversions line up with the published
sheet.

**Authoring note:** `.ai`/PDF → SVG conversion and InDesign extraction run on the authoring side
(YAML Builder CLI) with PyMuPDF/Pillow; the ERPNext server only ever receives SVG, PNG or JPEG.
PyMuPDF is AGPL-licensed, which is fine for internal tooling but is why it is kept out of the app.

### 15.5 Logos, placeholders and product lines

- **Brand folder** `api/spec_sheets/brands/illumenate/brand.json`: footer copy (with `{year}`), the
  notice, colour overrides and one logo per spec line, each either a designer file or a flagged
  placeholder. A second brand (206 Lighting) is another folder; Phase 1 moves the same fields onto
  `ilL-Webflow-Brand`.
- **Logo placement:** the line logos are 309.26 × 205pt artboards; InDesign placed them at 40 % with
  the artboard at (457.76, 31.8), found by aligning the lettering with the published PDF. The
  fixture passes with the vector SW logo: 174/174 words, 59/59 rules, 0.68 % of pixels differ
  (logo edges are now vector-crisp where the published PDF used a 300 dpi PNG).
- **Placeholders** are reported by `pages.placeholders(model)` and printed by
  `tools/spec_sheets/render_fixture.py`, so nothing is mistaken for final art.
- **Product line** comes from `tokens.spec_line_for(family, spectrum_type)`: Static White and
  Horticulture → SW, Dim to Warm → DW, Tunable White → TW, Full Spectrum → FS, the RGB types → CC,
  drivers/controllers → PS, extrusion kits/accessories → OTHER.

