# Production Linear Fixture readiness: design

**Status:** design, for owner review (2026-11-24)
**Belongs to:** runbook Part B of `docs/superpowers/plans/2026-11-23-spec-sync-production-linear-fixtures.md`. This design replaces "move fixture catalog data from staging" (B5b) with steps that work from production's own data.

## Goal

The spec sheet and the Webflow sync should work on production for every Linear Fixture that is on the website. Production's data is the real data (owner, 2026-11-24). Staging data is not copied; anything that exists only on staging is uploaded again by hand.

## What was found (read-only, production, 2026-11-24)

**The fields exist.**
- Every field `main` defines exists on production for `ilL-Fixture-Template`, `ilL-Webflow-Product` and all 27 child tables they use. Production's extra fields are only layout breaks.
- So once #503 is deployed and migrated, no field the spec sheet or the sync needs is missing.

**The data sits on the Webflow Product, not the template.** Before the redesign, the product record held this information; the spec sheet and sync now read it from the template.
- 71 Linear Fixture Webflow Products exist. How many have each field:

  | Field | Products that have it |
  |---|---|
  | Sublabel, category, series | 71 |
  | Featured image | 69 |
  | Documents | 62 |
  | Target brand | 61 |
  | Dimensions image, gallery, configurator | 44 |
  | Certifications | 25 |

- Only **26** of the 71 products are linked to a template.
- 156 fixture templates are Active. None has a Target Brand, Sublabel, Hero Image, Dimensions Image or Certifications, and 154 have no Product Category.
- For example, production's product `ill-sh01-sw` has Sublabel "Surface", category, series, 4 certifications, 6 gallery images and a dimensions image. Its template `ILL-SH01-SW` has none of these.

**Existing tools cover only part of the copy.**
- `template_link_report.link_consistency_report` links products and templates and seeds a template's **brand**, **category** and **series** from its product.
- `web_listing_migration.migrate` copies lengths, feed lengths, weight, warranty and kit components.
- **Nothing copies Sublabel, Dimensions Image, Hero Image or Certifications** to the template. On staging these were entered by hand.

**What the spec sheet requires** (`spec_sheet_check.check`):
- Typed in by hand: Target Brand, a name, Sublabel, Hero Image, Dimensions Image, Product Category.
- Calculated when the template is saved: at least one Specifications row and Part No. Configurator steps.
- Also calculated on save, from inputs that already exist on production (allowed options and tape offerings): Output Options, Delivered Lumens and Compatible Power Supplies.

## Design

Two additions to the app, plus a changed runbook order. Both additions follow `web_listing_migration`:
- System Manager only.
- Dry run by default.
- Never overwrite a field that already has a value; differences are reported instead.
- Write directly to the database, so template controllers and publication hashes are not triggered. The later `refresh_all_templates` save recalculates everything.
- Limited to `webflow_sync_scope` doctypes; fixtures first.

### 1. Carry product data onto the template (`web_listing_migration`, extended)

For each template linked to a Webflow Product, fill **empty** template fields from the product:

| Template field | From the Webflow Product | Note |
|---|---|---|
| `sublabel` | `sublabel` | |
| `dimensions_image` | `dimensions_image` | same file URL; no file copy |
| `certifications` (table) | `certifications` links → rows `{certification}` | badge image comes from the certification record, as on staging |
| `hero_image` | `featured_image` | **owner decision, see below** |
| `target_brands`, `product_category`, `series` | already seeded by `link_consistency_report` | not duplicated here |

- **Interface:** `web_listing_migration.carry_listing_fields(dry_run=1)`.
- **Returns:** `{"carried": [{template, fields}], "kept": [{template, field, template_value, product_value}], "not_linked": [...]}`.
- Runs again safely.

### 2. Readiness report (new Script Report, "Fixture Readiness")

One row per template in scope (default: Linear Fixtures that are Active, Active + Live, or linked to a Webflow Product). Columns:

| Column | What it shows |
|---|---|
| Template, Status, Webflow Product | |
| **Missing: you fill in** | Target Brand, Sublabel, Hero Image, Dimensions Image, Product Category, Webflow Product link, Certifications |
| **Missing: from the product** | Fields the product has and step 1 can copy |
| **Missing: calculated** | Specifications, Part No. Configurator, Output Options, Delivered Lumens, Compatible Power Supplies. These clear after `refresh_all_templates`. If they are still empty after that, an input is missing, and the report names it. |
| **Optional** | Spec Gallery (accessory and side-view drawings), photometrics, documents |
| **Ready** | Yes when `spec_sheet_check.check` passes and the product's readiness (`product_readiness.evaluate`) has no issues |

The report is read-only, filterable and exportable from the desk. It replaces the one-off CSV from this review (`prodfx/readiness.csv` in the session scratchpad).

### 3. Runbook B6, new order (Linear Fixtures)

1. `link_consistency_report(doctypes=…)`: dry run, then `apply` with `link_suggestions`. This links the 45 unlinked products where names match, and seeds brand, category and series.
2. Link any product still unlinked by hand. The report lists these.
3. `carry_listing_fields()`: dry run, then apply.
4. Fixture Readiness report: fill in the "you fill in" column by hand, typically hero images, missing dimensions images, certifications and spec gallery drawings, uploaded again from your files.
5. `refresh_all_templates(doctypes=…, apply=True, push=False)`: this calculates the specifications, configurator, outputs, lumens and power supplies.
6. Fixture Readiness report again: every website fixture shows **Ready**.
7. Continue with the existing runbook steps: `promote_live_templates`, regenerate (B8 dry run), pilot (B7).

## Tests (TDD, `tests/portal_unit`)

- `carry_listing_fields` dry run lists the copies and writes nothing. Apply fills only empty fields. A template field that differs from the product is reported in `kept` and left unchanged. Certifications become template rows. Templates out of scope are not touched.
- The readiness report puts each gap in the right column for a template with no data, a partly filled one (calculated fields missing) and a ready one, and lists inputs missing after a refresh.

## Open decision

**Hero image.** On staging, the template's hero image (e.g. `SH01_ASSEMBLED_1x1.jpg`) differs from the product's featured image (`SH01_LIT.jpg`). The spec sheet uses the hero image as its main picture.
- **Recommended:** copy `featured_image` into empty hero images as a starting point. The report marks it "from product, check", so you can replace the ones that should show the assembled fixture.
- **Alternative:** leave hero images empty and upload each one by hand.

## Out of scope

- Copying anything from staging.
- Fixture types other than Linear Fixtures, and 206 (later runbook phases).
- Webflow item IDs and sync state. Production keeps its own.
