# Webflow Product-Attribute Filter Sync Guide

## Overview

This guide explains how product attributes are synced to Webflow for filtering on the website. Each attribute type gets two fields on the Webflow Products collection:

1. **Display fields** (`cct-options-5`, `finishes-5`, etc.) — pipe-separated `name, code` pairs for display
2. **Filter fields** (`finish-filter`, `output-levels-filter`, etc.) — comma-separated attribute names for CMS filtering

### Display Field Format (e.g. `cct-options-5`)
```
2700K, 27K | 3000K, 30K | 3500K, 35K
```

### Filter Field Format (e.g. `finish-filter`)
```
Black Anodized,White,Custom
```

---

## Architecture

```
ERPNext                          Webflow CMS
┌───────────────────┐            ┌───────────────────┐
│ ilL-Webflow-Product│           │ Products Collection│
│  ├─ attribute_links│           │                   │
│  │  ├─ Output: 100│──────────►│  output-options-5: │
│  │  ├─ Output: 200│           │    "100lm/ft, 1 |  │
│  │  ├─ Finish: BLK│           │     200lm/ft, 2"   │
│  │  └─ Finish: WHT│           │                   │
│  └─ webflow_item_id│           │  output-levels-    │
└───────────────────┘            │    filter:         │
                                 │    "100lm/ft,      │
                                 │     200lm/ft"      │
                                 │                   │
                                 │  finish-filter:    │
                                 │    "Black,White"   │
                                 └───────────────────┘
```

---

## Sync Pipeline (2 Stages)

### Stage 1: Attribute Sync (existing)
**Workflow:** `webflow_attribute_sync.json`

Syncs all attribute doctypes to their respective Webflow collections. Each attribute record gets a `webflow_item_id` stored in ERPNext after successful sync.

### Stage 2: Product Sync
**Workflow:** `webflow_product_sync.json`

Syncs product data including both display fields (`-5`) and filter fields (`-filter`). Both field types are populated during the main product sync.

### Optional: Dedicated Filter Sync
**Workflow:** `webflow_product_attribute_filter_sync.json`

A lightweight workflow that only updates the filter fields (and display fields are untouched). Useful for re-syncing filters without a full product sync.

1. Fetches products already in Webflow (must have `webflow_item_id`)
2. Builds comma-separated attribute names for each filter field
3. PATCHes the product in Webflow with plain-text filter values

---

## Attribute Types & Webflow Field Slugs

### Display Fields (pipe-separated name/code pairs)

| Attribute Type     | ERPNext DocType                 | Display Field Slug      |
|--------------------|---------------------------------|-------------------------|
| CCT                | ilL-Attribute-CCT               | `cct-options-5`         |
| CRI                | ilL-Attribute-CRI               | `cris-5`                |
| Finish             | ilL-Attribute-Finish            | `finishes-5`            |
| Lens Appearance    | ilL-Attribute-Lens Appearance   | `lens-options-5`        |
| Mounting Method    | ilL-Attribute-Mounting Method   | `mounting-methods-5`    |
| Output Level       | ilL-Attribute-Output Level      | `output-levels-5`       |
| Environment Rating | ilL-Attribute-Environment Rating| `environment-ratings-5` |
| Feed Direction     | ilL-Attribute-Feed-Direction    | `feed-directions-5`     |
| LED Package        | ilL-Attribute-LED Package       | `fixture-types-5`       |

### Filter Fields (comma-separated names)

| Attribute Type     | Filter Field Slug           |
|--------------------|----------------------------|
| CRI                | `cri-filter`               |
| Finish             | `finish-filter`            |
| Lens Appearance    | `lens-filter`              |
| Mounting Method    | `mounting-filter`          |
| Output Level       | `output-levels-filter`     |
| Environment Rating | `environment-ratings-filter`|
| Feed Direction     | `feed-direction-filter`    |
| LED Package        | `led-package-filter`       |
| Dimming Protocol   | `dimming-filter`           |

---

## API Endpoints

### `get_product_attribute_references`

Returns products with their attribute links resolved to plain-text filter data.

```
GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.get_product_attribute_references
```

**Parameters:**
| Parameter       | Type    | Description                              |
|-----------------|---------|------------------------------------------|
| `product_slugs` | list    | Optional – specific products to fetch    |
| `sync_status`   | string  | Optional – filter by sync status         |
| `limit`         | int     | Max results (default: 100)               |
| `offset`        | int     | Pagination offset                        |
| `brand`         | string  | Optional – brand code (defaults to the configured default brand). Filters to products targeted at the brand and prefers the per-brand Webflow Item ID / sync status. |

**Response:**
```json
{
  "message": {
    "products": [
      {
        "product_slug": "luminaire-pro",
        "product_name": "Luminaire Pro",
        "webflow_item_id": "696fc3c5c42c86528e97f414",
        "brand": "illumenate",
        "filter_field_data": {
          "output-levels-filter": "100lm/ft,200lm/ft,300lm/ft",
          "finish-filter": "Black Anodized,White",
          "lens-filter": "Frosted,Clear"
        },
        "attribute_count": 8
      }
    ],
    "total": 15,
    "brand": "illumenate",
    "filter_field_slugs": {
      "Output Level": "output-levels-filter",
      "Finish": "finish-filter",
      "Lens Appearance": "lens-filter"
    }
  }
}
```

### `mark_filter_synced`

Records that a product's Webflow **filter fields** were synced for a brand, without overwriting the product's `webflow_item_id` / `webflow_collection_slug`. The filter sync workflow calls this instead of `mark_webflow_synced` so a filter PATCH cannot clobber the main product sync state.

```
POST /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.mark_filter_synced
```

**Parameters:**
| Parameter      | Type   | Description                                  |
|----------------|--------|----------------------------------------------|
| `product_slug` | string | Required – the product to mark               |
| `brand`        | string | Optional – brand code (defaults to default)  |

### `build_product_filter_field_data` (internal helper)

Converts attribute links grouped by type into a dict of comma-separated attribute names keyed by Webflow filter field slugs.

---

## Webflow Setup Requirements

### 1. Create Attribute Collections

Each attribute type needs its own Webflow CMS collection:
- CCT Options, Finish Options, CRI Options, etc.
- These are created by the existing attribute sync workflow

### 2. Add Filter Fields to Products Collection

In Webflow Designer, add **Plain Text** fields for filtering. These are **separate from** the existing display fields:

| Field Name                 | Field Slug                  | Type       |
|----------------------------|-----------------------------|------------|
| CRI Filter                 | `cri-filter`                | Plain Text |
| Finish Filter              | `finish-filter`             | Plain Text |
| Lens Filter                | `lens-filter`               | Plain Text |
| Mounting Filter            | `mounting-filter`           | Plain Text |
| Output Level Filter        | `output-levels-filter`      | Plain Text |
| Environment Rating Filter  | `environment-ratings-filter`| Plain Text |
| Feed Direction Filter      | `feed-direction-filter`     | Plain Text |
| LED Package Filter         | `led-package-filter`        | Plain Text |
| Dimming Filter             | `dimming-filter`            | Plain Text |

> **Important:** Do NOT delete or modify the existing display fields. The `-filter` fields sit alongside them.

---

## How to Run

### Recommended Order:
1. **Sync Attributes** → ensures attribute collections are up to date
2. **Sync Products** → syncs display fields and filter fields together

### Manual Trigger:
- Use the Manual Trigger in each n8n workflow
- Or call the API endpoints directly

### Scheduled:
Workflows run on a 6-hour schedule by default.

---

## Troubleshooting

### Filter fields are empty
Check that the product has attribute links in ERPNext. Open the Webflow Product document and verify the `attribute_links` child table is populated.

### Webflow returns 400 error on PATCH
- Check that the filter fields are configured as **Plain Text** (not Multi-Reference)
- Check the field slug matches exactly

### Product not appearing in filter sync
Products must have a `webflow_item_id` (i.e., been synced at least once). Run the product sync workflow first.

### Adding new attribute types
1. Add the attribute type to `ATTRIBUTE_FILTER_FIELD_SLUGS` in `webflow_attributes.py`
2. Create the corresponding Plain Text field in Webflow's Products collection
3. Ensure the attribute type name matches what's used in the `attribute_links` child table

---

## Code Reference

| File | Purpose |
|------|---------|
| `webflow_attributes.py` | Attribute export API + filter field data builder |
| `webflow_export.py` | Product export API (includes filter field data) |
| `webflow_product_sync.json` | n8n workflow: full product sync (includes filter fields) |
| `webflow_product_attribute_filter_sync.json` | n8n workflow: dedicated filter field sync |
| `webflow_attribute_sync.json` | n8n workflow: attribute collection sync |
