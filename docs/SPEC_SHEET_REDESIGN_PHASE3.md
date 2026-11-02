# Spec Sheet Redesign: Phase 3 (generate a spec sheet from the template)

## ERPNext

- **Generate Spec** button on the six templates (`public/js/template_spec_sheet.js`). The template
  must be saved first. An opaque dialog with no close button stays open while the job runs and polls
  its status; the job keeps running if the page is closed. Phase 5 changes the label to "Generate Spec
  & Sync to Webflow" when a sync follows.
- `spec_sheet_job.generate_spec_sheet(template_doctype, template_id, brand=None)`: permission as for
  linking (D28), checks the n8n site config, queues a background job (queue `long`) and returns a job
  id. `spec_sheet_job_status(job_id)`: Queued, Running, Done or Failed, with a message.
- The job posts `{template_doctype, template_id, brand}` to `n8n_spec_webhook_url` with the shared
  secret header, waits for `{success, file_url}` (5 minutes), then `register_spec_sheet` checks the
  template's Spec Sheet points at that file (and sets it if n8n did not). Phase 4 adds the stable URL
  and removes older files. Nothing here calls Webflow.
- n8n keeps uploading through `upload_spec_pdf` and then setting the template's `spec_sheet` (owner:
  that is what fills the File's attached-to fields).

### Data for templates without a Webflow Product

`get_spec_sheet_data` now always has a `legacy` record. With a linked product it is the real export
record. Without one it is built by the same export code (`webflow_export_v2.export_template_record`)
on a temporary, unsaved product that points at the template and has run the product calculations
(spec rows, attribute links, compatible power supplies, certification badges, configurator steps,
hero image). The export's per-product code was moved into `_finish_products` so both paths share it.

Keys only a real product fills come out empty in a template-only record
(`spec_sheet_data.PRODUCT_ONLY_KEYS`): name and slug, Webflow Status, badge, Is Discontinued, short
description, features, featured and series images, gallery, documents, compatible products,
configurator intro text, sync fields, Is Configurable, and the spec links.

Staging check: for linked templates, the template-only record compared with the real export, product-
only keys left out. `differences` should be empty:

```python
import json
from illumenate_lighting.illumenate_lighting.spec_sheet_data import check_template_records
print(json.dumps(check_template_records(), default=str, indent=1))
```

## Moving the spec workflow off `legacy` (owner, 2026-11-02)

New template columns, filled on every template save (`template_images.py`):

- Kit components `component_image`: per component type, the first item's template item image
  (`variant_of`), else the item's own image. Example: KIT-RA01, Profile, CH-RA01-SW -> CH-RA01's image.
- Certifications `badge_image`: the linked certification's dark badge for the template's brand
  (ilLumenate `custom_badge_image_dark`, 206 Lighting `custom_206_badge_image_dark`).

`context` gains `product_type`, `include_configurator` and `base_url`.

Owner's mapping for the spec workflow:

| Spec sheet key | Template source |
|---|---|
| `product_name` | `display_name`, else `template_name` |
| `sublabel` | `sublabel` |
| `featured_image` | `hero_image` |
| `dimensions_image_dark`, `custom_dimensions_image_2` | `dimensions_image` |
| `product_slug` | `template_code`, lowercase |
| `product_type` | `context.product_type` |
| `configurator_options` | `part_no_configurator` (empty when `context.include_configurator` is false) |
| `specifications` | `specifications`: `spec_label`, `spec_value`, `display_order` only |
| `kit_components` | `kit_components` grouped by type, as before: `[{hero_image: component_image}, {code: component_item, label: webflow_description}...]` |
| `certifications` | `certifications`: `certification`, badge from `badge_image` |
| `photometric_image`, `photometric_data`, `colorimetry` | still `legacy` |
| `custom_compatible_power_supplies` | still `legacy` (product owns it) |
