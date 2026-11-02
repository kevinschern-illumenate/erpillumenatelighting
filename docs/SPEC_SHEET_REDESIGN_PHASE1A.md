# Spec Sheet Redesign: Phase 1a (2026-10-31)

Plan: `erpnext_spec_sheet_redesign_plan.md` v0.6, Phase 1a, with the owner decisions recorded in
`SPEC_SHEET_REDESIGN_PHASE0.md` (D49 to D57). Branch `staging`.

## What changed

### Template fields (plan 4.1, D10, D17, D22, D54, D57)

All six templates, on the **Product Data** tab, through `web_listing_schema.py` and
`tools/stamp_web_listing_fields.py`:

| Field | Type | Notes |
|---|---|---|
| `target_brands` | Table `ilL-Child-Webflow-Brand-Target` | At most one enabled row. Exactly one is needed to link a product. |
| `sublabel` | Data | |
| `dimensions_image` | Attach Image | D46 |
| `certifications` | Table `ilL-Child-Spec-Certification` | D57. The existing table on Tape/Neon, LED Sheet, Driver and Controller moved here with the same fieldname, so no data moves. New on Kit and Fixture. |
| `spec_sheet_public_url` | Data, read-only | Filled in Phase 4. |
| `other_documents` | Table `ilL-Child-Webflow-Document` | Data copy from `custom_documents` is Phase 1b. |
| `webflow_category` | Link `ilL-Webflow-Category` | Tape/Neon only (D54). |

`ilL-Product-Publication` gets `review_reason` (read-only, used in Phase 5).

These fields are not mirrored to the product yet. The mirror (D21) is Phase 2.

**Held, waiting on the owner:**

- `part_number_builder`: name conflict (see questions below).
- `specifications`: its child doctype `ilL-Child-Webflow-Spec-Custom` exists only on the site (created in
  the UI), not in the app. The same is true of `ilL-Child-Comp-Power` (used by
  `custom_compatible_power_supplies`). Both must ship with the app before any field can use them.

### Link ownership (plan 4.2, D2, D3, D27, D28)

New module `template_link.py`, called from each template's `validate`, `on_update` and `on_trash`, and
from the product's `validate` and `after_insert`.

- `template.webflow_product` is the real link. It is editable while empty and read-only once set.
- The product's six link fields (`kit_template` and the others) are read-only mirrors. Editing one on an
  existing product is refused. A duplicated product drops the link.
- Creating a product with a template link is allowed (the catalog importer does this, and so will the
  Phase 6 "Create new" popup) when the template is unlinked, serves the product's type, and the user
  may change the template. The template side is written on insert.
- Linking from the template (picking the product while the field is empty, or
  `template_link.link_webflow_product`) checks: the product exists, its type fits the template, neither
  side is linked elsewhere, the template has exactly one enabled Target Brand, and permission (D28:
  System User, write on the template, `ilL Catalog Publisher` or System Manager). Then it saves the
  product with its mirror field set, so the product picks up the template's data in the same request.
- Unlinking only through **Actions > Unlink Webflow Product** on the template
  (`template_link.unlink_webflow_product`), same permission. Refused while the template is Active.
- Setting Product Status to **Active** without a Webflow Product is refused (D3). Templates that are
  already Active without one are listed by the report, not blocked on their next save.
- Target Brands: more than one enabled row is refused (D17). Changing the enabled brand is refused once
  the product has a `published_on` on the old brand (D27).
- A new template whose record name another template doctype already uses, in any letter case, is
  refused (plan 4.7, test matrix 26).
- Removed: the product's `_update_template_backlink` (the direction flipped) and
  `_clear_template_links_for_other_types`. A linked product now cannot change to a type its template
  does not serve; unlink it first. The product's `on_trash` still clears the template's link.
- No recursion: a product save never saves a template. A template save saves its product only when the
  link changes, with a flag that skips the product-side check.

### Consistency report and migration

`template_link_report.link_consistency_report`, System Manager only, dry run by default. It lists:
consistent pairs, template links to fill, product links to fill, template brands to seed from the
product, conflicts (two templates on one product, two products on one template, the sides
disagreeing, type mismatches), Active templates with no product, ambiguous brands, products whose
category or series would change once they mirror the template (D55), and duplicate record names.

With `apply` it only fills empty links where both sides agree and seeds a template brand when the
product has exactly one enabled brand. It never overwrites a value and runs no save hooks.

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report
```

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report --kwargs "{'apply': True}"
```

## Tests

- New, bench-free: `tests/portal_unit/test_template_link.py` (18 with the report tests),
  `test_template_link_report.py`; schema tests in `test_web_listing.py`.
- Updated: `test_cob_tape.py` (stubs the link module), bench test
  `test_ill_webflow_product.py::test_fixture_template_link_moves_only_through_the_templates`.
- Full `tests/portal_unit` suite passes. The bench tests could not be run in this environment.

## After deploying to staging

1. `bench migrate` (the template, product and publication doctypes changed) and a build for the new
   desk script `public/js/template_webflow_link.js`.
2. Run the consistency report dry run and send the output for review. Phase 1a is done when it is
   clean, or when every remaining item has an owner decision.

## Follow-up (2026-10-31, after the first staging run)

**D58 (owner):** the Fixture template keeps its existing `part_number_builder` (part-number sections,
child `ilL-Child-PN-Builder-Row`, read by the spec sheet export and the Dry/Wet code sync). Its
configurator table is a separate `part_no_configurator` (child `ilL-Child-Webflow-Configurator-Option`).
Revised by the owner: all six templates use `part_no_configurator` for the configurator table, for
consistency (`web_listing_schema.CONFIGURATOR_FIELD`). Only the Fixture template has the older
`part_number_builder` sections table.

The two site-only child doctypes now ship with the app (`ilL-Child-Webflow-Spec-Custom`,
`ilL-Child-Comp-Power`, fields from the staging export), and the templates have their `specifications`
table.

**First staging report** (dry run): 56 consistent pairs, 10 product links to fill, 55 template brands to
seed, 1 conflict, 28 Active templates with no product, 11 brands needing review, 66 category or series
differences, no duplicate names. The report was reworked from what it showed:

- A product with no Target Brand rows syncs to the default brand today, so its template is seeded with
  the default brand instead of being listed for review.
- 62 of the 66 differences were empty template fields. Empty template category, Tape/Neon Webflow
  Category and series are now **seeded from the product** with `apply` (nothing on the product changes).
  Only real disagreements stay listed, as `category_series_conflicts`.
- Templates with no link on either side are matched to a free product with the same name (any case) and
  a fitting type, listed as `suggested_links`, and linked only with `link_suggestions`.
- The conflict entry now shows which product the template itself points at.
- When two products claim a template whose own link points at one of them, `apply` clears the other
  product's link (`clear_product_link`): the template owns the link (D2). This resolves KIT-RA01
  (`ext001-a`).

**D59 (owner):** the product's configurator table `configurator_options` is renamed to
`part_no_configurator` in Phase 1b, after the Phase 2 adapter that keeps n8n reading the old key
(supersedes the product name in D25).

## Result on staging (2026-10-31)

After `link_suggestions` and two `apply` runs, the dry run reports: 79 consistent pairs; 0 links to
fill or clear, 0 brands or categories to seed, 0 suggestions, 0 conflicts, 0 duplicate names. 16 Active
templates have no Webflow Product (PS-NON, PS-PRI, PS-WALL, KIT-MS01, KIT-MS13, KIT-MS15, KIT-MS16,
KIT-SN03, ILL-CR01-SW, ILL-CR02-FS, ILL-MS13-FS, ILL-TR03-FS, cob-sn-sw, led-sd-cc, non-bst-sw,
non-tdr-sw). They are not blocked; the owner links a product or moves each to Internal Only.

**Phase 1a is done**: links change only through the allowed paths, saves do not recurse, and the
consistency report is clean apart from those owner decisions.

## D60: new Product Status "Active + Live" (owner, 2026-10-31)

Product Status options are now: Draft, Active, **Active + Live**, Internal Only, Discontinued, Archived.

- **Active**: offered to dealers and staff in ERPNext and the portal. Not listed on the website, and no
  Webflow Product is needed.
- **Active + Live**: offered the same way, and listed on the website through its Webflow Product. The
  Webflow Product is required: setting this status without one is refused, and a Live template cannot
  be unlinked. (This replaces "required when Active" from D3 and Phase 1a.)
- Active + Live counts as active everywhere Active did: `is_active` is set, dealers see it on the portal
  (list filters, list permission, document permission, the product finder conditions), and staff see it.
- The readiness message for Internal Only templates now says to set the template to Active + Live.
- The consistency report lists `live_without_product` instead of `active_without_product`. The 16
  Active templates without a product on staging are no longer flagged.
- For the plan's status table (4.3): its "Active" rows 4 to 11 mean **Active + Live**. A plain Active
  template has no Webflow action of its own.
- No data was changed. Templates whose product is meant to be on the website today are still Active and
  need to be moved to Active + Live by the owner (or by a migration, if wanted) before Phase 5's
  automatic pushes are turned on.

**D61 (owner, answers Q21):** when an Active + Live template whose product has been published moves
back to plain Active, the page is **hidden** and the owner is **notified**; the owner then decides
whether to change the product's Webflow Status. (Phase 5: same hide-and-notify path as D45.)

**Migration (owner):** Active templates whose product is Published in Webflow become Active + Live.
`template_link_report.promote_live_templates`, System Manager only, dry run by default. "Published"
is the product's Webflow Status stage (`custom_webflow_status`, later `webflow_status`), value
"Published" or the older "Publish"; the publication records' dates were cleared on staging by the
Phase 0 reset, so they cannot be used there. Only linked templates change. It also lists, without
changing them, templates in another status whose product is Published, and Active templates whose
product is Discontinued (still public).

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.promote_live_templates
```

```bash
bench --site stagingillumenate.v.frappe.cloud execute illumenate_lighting.illumenate_lighting.template_link_report.promote_live_templates --kwargs "{'apply': True}"
```

## Later phase: layout and field cleanup (owner, 2026-11-02)

A separate final phase, after a spec sheet can be generated and Webflow updated end to end and that has
been verified on staging: go back over the templates and the Webflow Product, find the fields that were
never used, and clean up layout and fields. Until then, layout changes are kept to what the work needs.

## Questions for the owner

1. *(Answered: D58 above.)* **`part_number_builder` name conflict (D25).** The Fixture template already has a
   `part_number_builder` table (child `ilL-Child-PN-Builder-Row`: section, code, label). The spec sheet
   export and environment codes read it. D25 wants the same name for the configurator-option table
   (`ilL-Child-Webflow-Configurator-Option`), which is a different structure. Recommended: keep the
   Fixture's existing table as it is, and name the configurator table `configurator_options` on the
   templates (the product already uses that name, so nothing on the product is renamed), with the label
   "Configurator Options". Alternative: rename the Fixture's existing table and update its readers.
2. *(Answered: shipped.)* **Site-only child doctypes.** Please export these two so they can ship with the app:

   ```bash
   bench --site stagingillumenate.v.frappe.cloud execute frappe.client.get --kwargs "{'doctype': 'DocType', 'name': 'ilL-Child-Webflow-Spec-Custom'}"
   ```

   ```bash
   bench --site stagingillumenate.v.frappe.cloud execute frappe.client.get --kwargs "{'doctype': 'DocType', 'name': 'ilL-Child-Comp-Power'}"
   ```

## Phase 1b leftovers, done 2026-11-02 (plan 4.3, 4.8, D33, D36, D48)

Patch `webflow_status_draft_badge_discontinued`:

- **Webflow Status:** the stage `Draft` is gone; those products (and any with no stage) are now
  `Webflow Draft`, the new default. Options: Webflow Draft, Published, Discontinued, Archived. The n8n
  Transform nodes already treated Draft and Webflow Draft the same, so nothing changes on the website.
  No automatic pushes exist yet (Phase 5), so nothing is sent to Webflow by this.
- **Badge:** `product_badge` is copied into `webflow_badge` where that is empty. Products whose two
  badges disagree, or whose old badge is `Hide` (not an option on Web Badge, D50), keep their Web
  Badge and are listed in the Error Log entry "Product Badge values not moved to Web Badge". The old
  field is hidden and read-only; both exports now fill `product_badge` from `webflow_badge`, so n8n
  and Webflow's `product-badge` field read the new value. The field is deleted once nothing reads it.
- **Is Discontinued** (read-only check on the product, `webflow_state.py`): on when the Webflow Status
  is Discontinued, or when the template is Discontinued or Internal Only and the product has been
  published (a publication date, or a Webflow item for any brand). Off for Archived and everything
  else. Stored on every product save; a template save saves its product, so a template status change
  refreshes it. The patch sets the first values. Exported as `is_discontinued` (0 or 1) and in payload
  v2. Webflow does not use it yet (R1, Phase 9).
