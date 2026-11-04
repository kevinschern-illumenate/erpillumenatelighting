# Spec Sheet Redesign: Phase 4 (stable link and file lifecycle)

Plan 4.7 (D6, D7, D19, D24). `spec_sheet_route.py`.

- **Stable link** per template: `https://<site>/spec-sheets/<record name, lowercase>.pdf`, for example
  `/spec-sheets/kit-ra01.pdf` (the `.pdf` is optional). A redirect, not a file: 302 with
  `Cache-Control: no-store` to the file the template's Spec Sheet field points at, so the previous PDF
  is served until the new one is registered. Unknown name, or a name two templates share in any case:
  404 (the second is logged). Served by a `page_renderer` hook, which Frappe asks before its own pages
  and static files.
- **On every successful generation** (`spec_sheet_job.register_spec_sheet`): Spec Sheet points at the
  new file, `spec_sheet_public_url` is set to the stable link, older files attached to the template's
  Spec Sheet field are deleted through their File documents keeping the newest 2 and never the current
  one, and the linked Webflow Product is saved so its Spec Sheet document row is the stable link. A
  failed run changes nothing.
- **File name** (D7): `<Template Name>_Spec Sheet.pdf`, record name when Template Name is empty, no
  brand prefix. Decided in ERPNext (`context.spec_sheet_file_name` in `get_spec_sheet_data`): spaces,
  brackets and dots kept; path separators, `: * ? " < > |` and control characters dropped. The
  per-brand regexes in the old Convert nodes are not used.
- **`webflow_export_v2.spec_sheet(product)`** (guest): read a product field that does not exist;
  now redirects through the product's template to its current spec sheet.

## Checks on staging (spikes S1, S2)

After deploying, generate a spec sheet for KIT-RA01, then from any terminal:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/illumenate-lighting_kit-ra01.pdf
```

Expect `302`, `Cache-Control: no-store` and a `Location` pointing at the current file. Also:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/206-lighting_kit-ra01.pdf
```

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/no-such-template.pdf
```

The first is a 302 to the current file; the second and third are 404s (KIT-RA01 is an ilLumenate template).

Not yet (migration, plan 4.7): repointing Webflow to the stable links and removing the old
`<Brand>_<Product>_Spec Sheet.pdf` files once Webflow shows the new links.

## Owner changes (2026-11-03)

- **Link and file name carry the brand.** Link: `/spec-sheets/<brand>_<record name, lowercase>.pdf`,
  for example `/spec-sheets/illumenate-lighting_kit-ra01.pdf` or `/spec-sheets/206-lighting_kit-ra01.pdf`.
  The brand part must be the template's own Target Brand, else 404; a link without it still resolves.
  File: `<Brand>_<Display Name>_Spec Sheet.pdf` (Display Name, else Template Name, else record name),
  for example `ilLumenate Lighting_Rainier [SF] Extrusion Kit_Spec Sheet.pdf`. Brand names:
  `illumenate` ilLumenate Lighting, `lighting_206` 206 Lighting, others their Brand Label.
- **Older files are unattached, not deleted.** After a successful run only the current spec sheet stays
  attached to the template; older ones stay in File Manager. (Replaces keep-2 pruning, D24.)

## Bulk regeneration (moving Webflow to the stable links)

`spec_sheet_job.regenerate_spec_sheets`, System Manager only, dry run by default. Active + Live
templates unless `statuses` or `templates` say otherwise; templates without a Target Brand are
skipped and listed. With `apply`, one background job generates them one after another (one call to
n8n and Vercel at a time); one failure does not stop the rest. Each is the same as the Generate Spec
button, so each linked Webflow Product's Spec Sheet row becomes the stable link, and Webflow shows it
on that product's next sync. Progress: `spec_sheet_bulk_status(bulk_id)` (kept 24 hours).

Rollout (owner, 2026-11-03): only the Extrusion Kit spec sheet page exists in Webflow so far, so the
bulk run goes one template type at a time (`doctypes="ilL-Extrusion-Kit-Template"`). Other types keep
their current spec sheets and links until their Webflow page (`/spec-sheet-templates/<product type>`)
is built and that type is regenerated and checked. The dry run's `webflow_pages_needed` lists the
pages a run needs.

## Readiness check and product attachment (owner, 2026-11-03)

- **Generate Spec checks the template first** (`spec_sheet_check.py`) and lists everything missing;
  nothing is sent to n8n until it passes. Required: Target Brand, Display Name or Template Name,
  Sublabel, Hero Image, Dimensions Image, at least one Specifications value, and the brand's Webflow
  page `/spec-sheet-templates/<product type>`. Kits also need a Default Profile Spec with dimensions,
  Kit Components rows with Type and Item, and a Component Image per type. Warnings (shown after the
  spec is generated): rows without Description, certifications without Badge Image, no configurator
  steps. Other template types get their own rules when their Webflow page is built. The bulk run
  skips templates that fail the check and says why.
- **The Webflow page comes from the template's product type**, never the Webflow Product's, so
  templates without a product work. The page check uses site config `spec_sheet_template_sites`
  ({brand code: Webflow site}) when set, else the brand's Webflow Site URL.
- **The current spec sheet is also attached to the linked Webflow Product** (a second File record for
  the same stored file); the product's earlier spec sheet attachments are unattached, as on the
  template.

## Follow-up (owner, 2026-11-03)

- The Webflow page is **not** checked (not every template has one). The template's Webflow Category
  is required instead (Product Category; Tape/Neon: Webflow Category, D54). The page is picked from it.
- New required fields: Part No. Configurator (at least one step, each with Option Type, Option Label
  and Depends On Step); for kits, Operating Temperature Min and Max (both 0 counts as unset) and a
  Description on every Kit Components row. Component Images are a warning, not required.
- **The Webflow Product's Product Category mirrors the template's Webflow Category, and its Product
  Type follows it**: extrusions Extrusion Kit, cob-tape COB Tape, controls Controller, landscape and
  linear-fixtures Fixture Template, led-sheets LED Sheet, led-tape LED Tape, neon LED Neon,
  power-supplies Driver. Both are read-only on a linked product. `web_product_category` is removed.
  `web_series` is labelled Series.
- Environment Ratings are always listed Dry, Damp, Wet (others after, A to Z).
- `web_series` is removed. The product's `series` (a link to ilL-Attribute-Series, like the
  template's) mirrors the template's Series on save and is read-only on a linked product.
- Kit Stock Length and Max Assembled Length use `"` for inches, like Dimensions: `78.7" (2000mm)`.
- Kit Components Description is set on template save from the item's variant attributes: Profile
  Finish, Lens Lens Color, Endcap Set Endcap Color (attribute names matched in any case). Other
  types, and items without that attribute, keep the typed Description.
- **n8n refuses too.** `get_spec_sheet_data` runs the same readiness check and returns an error for a
  template that is missing anything required, so the spec workflow stops at its first node (Get Spec
  Sheet Data, which answers through its error reply) whoever started it. The Generate Spec job shows
  the missing fields from that answer. (`check_ready=False` is used only by the staging checks.)
  Operating temperatures: an empty Int field reads 0, so "both 0" counts as not set; one bound set and
  the other empty passes.
- Template forms (owner, 2026-11-04): the Template Name is shown under the record name in the sidebar,
  and Actions > Apply Calculations recalculates a saved template on demand (specifications,
  configurator, component and badge images) and saves its Webflow Product
  (`template_listing.apply_calculations`, same permission as linking).
- The Environment row is labelled "Environment Rating(s)" (the old "Environment Ratings" row is
  replaced on the next calculation).

## Spec Gallery (owner, 2026-11-04)

All six templates have a **Spec Gallery** section on the Product Data tab (`spec_gallery`, child
`ilL-Child-Spec-Gallery`): Section (required; Dimensions, Accessories Dimensions, Bend Diameter(s),
Overview, Emission Angle), Title (optional), Image (required, any file type including SVG). Spec
sheets only; nothing is copied to the Webflow Product or Webflow. The rows reach n8n in
`get_spec_sheet_data` (`template.spec_gallery`) in table order.

ilLumenate kit sheet: the first `.dimension-item` keeps `dimensions_image` in `#spec-dims-img`;
`#dimension-item` is repeated once per Dimensions row (title in `#dimension-title`, hidden when
empty; image in `#spec-dims-img-other`) and hidden when there are none. The other sections wait for
their Webflow pages.

Template sidebar: brand pill, then the record name, then the Template Name directly under it.

## Kits waiting for data (2026-11-04)

The owner runs the kit bulk regeneration later, once the foundations are set. On
2026-11-04, KIT-RA01 to KIT-RA04 were ready. These were skipped for missing data:

| Kit | Missing |
|---|---|
| KIT-AZ01 | Sublabel, Hero Image, Dimensions Image, Operating Temperature Min and Max |
| KIT-BN03 | Same as KIT-AZ01, plus the Description on Kit Components row 7 |
| KIT-CH02 | Same as KIT-AZ01, plus all Kit Components |
| KIT-RA05 | Hero Image, Dimensions Image, and the Description on Kit Components row 3 |
| KIT-SH01 | Same as KIT-CH02 |
| KIT-SH02 | Same as KIT-CH02 |
| KIT-SH03 | Same as KIT-CH02 |
| KIT-SL01 | Same as KIT-AZ01 |
