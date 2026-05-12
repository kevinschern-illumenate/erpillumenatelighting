# Multi-Brand Webflow Architecture

This document describes the per-brand Webflow integration introduced for the
two-site MVP (`illumenate` and `lighting_206`). It supersedes the
single-site flow described in [WEBFLOW_INTEGRATION_GUIDE.md](WEBFLOW_INTEGRATION_GUIDE.md)
during the migration window.

## Concepts

- **Brand** — A first-class entity stored in `ilL-Webflow-Brand`. The
  `brand_code` is the stable identifier (lowercase, e.g. `illumenate`,
  `lighting_206`); `brand_label` is the human-friendly name.
- **Default brand** — Exactly one brand has `is_default=1`. Used as the
  back-compat fallback whenever a caller (UI / n8n / API) does not supply a
  `brand` parameter.
- **Target brands** — Each `ilL-Webflow-Product` and `ilL-Webflow-Category`
  has a `target_brands` table. A record is published to a brand only if a
  row exists with `enabled=1`.
- **Per-brand sync state** — Each Product / Category / Attribute has a
  `sync_targets` (or `webflow_sync_targets` for attributes) table whose rows
  point to a brand and carry the per-brand `webflow_item_id`,
  `sync_status`, `last_synced_at`, and `sync_error_message`.

## DocTypes

| DocType | Purpose |
| --- | --- |
| `ilL-Webflow-Brand` | Brand master record — site ID, n8n credential name, configurator gating, base URL. |
| `ilL-Webflow-Brand-Collection` | Child of brand — maps `collection_kind` (`Products`, `Categories`, `CCT`, …) → Webflow CMS collection ID. |
| `ilL-Child-Webflow-Sync-State` | Reusable child table — one row per (parent doc, brand) carrying sync status. |
| `ilL-Child-Webflow-Brand-Target` | Reusable child table — `(brand, enabled)` for product/category brand targeting. |

## API surface

All public endpoints accept an optional `brand` query parameter (default =
default brand). Per-brand sync rows are authoritative; legacy scalar fields
on Product / Category / Attribute documents are dual-written for the default
brand only during the migration window.

```
GET  /api/method/illumenate_lighting...api.webflow_export.get_webflow_products?brand=illumenate
GET  /api/method/illumenate_lighting...api.webflow_export.get_webflow_categories?brand=lighting_206
GET  /api/method/illumenate_lighting...api.webflow_attributes.get_webflow_attributes?attribute_type=cct&brand=illumenate
POST /api/method/illumenate_lighting...api.webflow_export.mark_webflow_synced { brand, product_slug, webflow_item_id }
POST /api/method/illumenate_lighting...api.webflow_export.mark_webflow_error  { brand, product_slug, error_message }
POST /api/method/illumenate_lighting...api.webflow_export.trigger_sync         { brand, mode, target }
POST /api/method/illumenate_lighting...api.webflow_attributes.mark_attribute_synced { brand, attribute_type, doc_name, webflow_item_id }
POST /api/method/illumenate_lighting...api.webflow_attributes.mark_attribute_error  { brand, attribute_type, doc_name, error_message }
```

Brand metadata for n8n bootstrapping:

```
GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_brand.list_brands?active_only=1
GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_brand.get_brand_config?brand=illumenate
```

## n8n workflow pattern

Each workflow accepts a `brand` URL parameter and:

1. **Set Brand** node — pin the brand code from the trigger.
2. **Get Brand Config** HTTP node — call `webflow_brand.get_brand_config`
   to retrieve site ID, collection IDs, n8n credential name, configurator
   flag, base URL.
3. **Brand-switch If** — route Webflow API calls through the matching n8n
   credential (`webflow-illumenate` vs `webflow-lighting_206`). Two parallel
   branches per Webflow call, both downstream nodes converging.
4. **Mark Synced/Error** — pass `brand` back to ERPNext so the per-brand row
   is updated.

## Configurator gating

`ilL-Webflow-Brand.include_configurator_payload` controls whether the
product export includes configurator metadata (`is_configurable`,
`configurator_options`, `kit_components`, `min_length_mm`, `max_length_mm`,
`length_increment_mm`, `configurator_intro_text`). For brands where the flag
is unset, those fields are zeroed on the way out — n8n maps them to empty
strings/zero in the brand's Webflow CMS.

## Migration patches (post-model-sync)

1. `create_webflow_brand_doctype_seed` — insert `illumenate` + `lighting_206`.
2. `migrate_webflow_settings_to_brand` — copy `ilL-Webflow-Settings.collection_id_*`
   into the `illumenate` brand's `collections` table.
3. `add_brand_sync_state_to_webflow_records` — backfill `target_brands` and
   `sync_targets` rows on every Product/Category from legacy scalars.
4. `migrate_attribute_sync_fields_to_brand_table` — add
   `webflow_sync_targets` Table custom field to each attribute DocType,
   backfill from scalars, hide legacy scalar custom fields.

Patches are idempotent.

## Dual-write window

For one release after enabling per-brand sync:

- Reads prefer per-brand rows when present, falling back to legacy scalars.
- Writes (`mark_webflow_synced`, `mark_webflow_error`, `mark_attribute_*`)
  always update the per-brand row, and additionally mirror the legacy scalar
  iff the brand is the default. This keeps existing single-site n8n
  workflows functional while the multi-site workflows roll out.

After the dual-write window, the legacy scalars can be safely removed in a
follow-up patch.
