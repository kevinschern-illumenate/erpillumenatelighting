# Webflow Product-Attribute Multi-Reference Sync Guide

## Overview

This guide explains how product options are filtered on the Webflow website by syncing **multi-reference relationships** between ERPNext Products and Attribute collections in Webflow CMS.

### The Problem
Previously, attribute fields on Webflow products were plain text strings (e.g. `"2700K, 3000K, 3500K"`). This made it impossible for Webflow's CMS filtering and dynamic lists to cross-reference products against their attribute options.

### The Solution
Each attribute type (CCT, Finish, CRI, etc.) exists as a **separate Webflow collection**. Products link to these via **multi-reference fields**, enabling Webflow to:
- Filter products by any combination of attributes
- Show "available in these finishes / CCTs" on product pages
- Build dynamic category pages with attribute facets

---

## Architecture

```
ERPNext                          Webflow CMS
┌───────────────────┐            ┌───────────────────┐
│ ilL-Webflow-Product│           │ Products Collection│
│  ├─ attribute_links│           │                   │
│  │  ├─ CCT: 2700K │──────────►│  cct-options-5: [  │
│  │  ├─ CCT: 3000K │           │    "wf-id-2700k", │
│  │  ├─ Finish: BLK│           │    "wf-id-3000k"  │
│  │  └─ Finish: WHT│           │  ]                │
│  └─ webflow_item_id│           │  finishes-5: [    │
└───────────────────┘            │    "wf-id-blk",   │
                                 │    "wf-id-wht"    │
┌───────────────────┐            │  ]                │
│ ilL-Attribute-CCT  │           └───────────────────┘
│  ├─ 2700K          │                   ▲
│  │  webflow_item_id├───────────────────┘
│  └─ 3000K          │           ┌───────────────────┐
│     webflow_item_id├──────────►│ CCT Options Coll.  │
└───────────────────┘            │  ├─ 2700K (wf-id) │
                                 │  └─ 3000K (wf-id) │
                                 └───────────────────┘
```

---

## Sync Pipeline (3 Stages)

The sync runs in a specific order — each stage depends on the previous:

### Stage 1: Attribute Sync (existing)
**Workflow:** `webflow_attribute_sync.json`

Syncs all 24 attribute doctypes to their respective Webflow collections. Each attribute record gets a `webflow_item_id` stored in ERPNext after successful sync.

### Stage 2: Product Sync (existing)
**Workflow:** `webflow_product_sync.json`

Syncs product data (name, descriptions, images, specs). Each product gets a `webflow_item_id`. This workflow now also includes multi-reference data when available.

### Stage 3: Product-Attribute Reference Sync (NEW)
**Workflow:** `webflow_product_attribute_ref_sync.json`

Dedicated workflow that:
1. Fetches products already in Webflow (must have `webflow_item_id`)
2. Resolves each product's attribute links to Webflow Item IDs
3. PATCHes the product in Webflow with multi-reference arrays

**This workflow should run AFTER both attribute sync and product sync.**

---

## Attribute Types & Webflow Field Slugs

| Attribute Type     | ERPNext DocType                 | Webflow Product Field Slug | Webflow Collection |
|--------------------|---------------------------------|----------------------------|--------------------|
| CCT                | ilL-Attribute-CCT               | `cct-options-5`            | CCT Options        |
| CRI                | ilL-Attribute-CRI               | `cris-5`                   | CRI Options        |
| Finish             | ilL-Attribute-Finish            | `finishes-5`               | Finish Options     |
| Lens Appearance    | ilL-Attribute-Lens Appearance   | `lens-options-5`           | Lens Appearances   |
| Mounting Method    | ilL-Attribute-Mounting Method   | `mounting-methods-5`       | Mounting Methods   |
| Output Level       | ilL-Attribute-Output Level      | `output-levels-5`          | Output Levels      |
| Environment Rating | ilL-Attribute-Environment Rating| `environment-ratings-5`    | Environment Ratings|
| Feed Direction     | ilL-Attribute-Feed-Direction    | `feed-directions-5`        | Feed Directions    |
| LED Package        | ilL-Attribute-LED Package       | `fixture-types-5`          | LED Packages       |

---

## API Endpoints

### `get_product_attribute_references`

Returns products with their attribute links resolved to Webflow Item IDs.

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

**Response:**
```json
{
  "message": {
    "products": [
      {
        "product_slug": "luminaire-pro",
        "product_name": "Luminaire Pro",
        "webflow_item_id": "696fc3c5c42c86528e97f414",
        "attribute_webflow_ids": {
          "CCT": ["65a1b2c3d4e5f6a7b8c9d0e1", "65a1b2c3d4e5f6a7b8c9d0e2"],
          "Finish": ["65a1b2c3d4e5f6a7b8c9d0e3"],
          "Lens Appearance": ["65a1b2c3d4e5f6a7b8c9d0e4"]
        },
        "multiref_field_data": {
          "cct-options-5": ["65a1b2c3d4e5f6a7b8c9d0e1", "65a1b2c3d4e5f6a7b8c9d0e2"],
          "finishes-5": ["65a1b2c3d4e5f6a7b8c9d0e3"],
          "lens-options-5": ["65a1b2c3d4e5f6a7b8c9d0e4"]
        },
        "attribute_count": 4,
        "unresolved_count": 1
      }
    ],
    "total": 15,
    "multiref_field_slugs": {
      "CCT": "cct-options-5",
      "Finish": "finishes-5"
    }
  }
}
```

### `resolve_attribute_webflow_ids` (internal helper)

Given a list of attribute links, resolves each to its Webflow Item ID.

### `build_product_multiref_field_data` (internal helper)

Converts resolved IDs into a dict keyed by Webflow field slugs, ready for the Webflow API.

---

## Webflow Setup Requirements

### 1. Create Attribute Collections

Each attribute type needs its own Webflow CMS collection:
- CCT Options, Finish Options, CRI Options, etc.
- These are created by the existing attribute sync workflow

### 2. Add Multi-Reference Fields to Products Collection

In Webflow Designer, add a **Multi-Reference** field for each attribute type on the Products collection:

| Field Name         | Field Slug           | References Collection |
|--------------------|----------------------|-----------------------|
| CCT Options        | `cct-options-5`      | CCT Options           |
| CRI Options        | `cris-5`             | CRI Options           |
| Finishes           | `finishes-5`         | Finish Options        |
| Lens Options       | `lens-options-5`     | Lens Appearances      |
| Mounting Methods   | `mounting-methods-5` | Mounting Methods      |
| Output Levels      | `output-levels-5`    | Output Levels         |
| Environment Ratings| `environment-ratings-5`| Environment Ratings |
| Feed Directions    | `feed-directions-5`  | Feed Directions       |
| LED Packages       | `fixture-types-5`    | LED Packages          |

> **Note:** The `-5` suffix on field slugs may vary. Check your actual Webflow collection schema.

### 3. Convert Plain Text Fields to Multi-Reference

If you currently have plain text fields with these slugs, you'll need to:
1. Delete the plain text field
2. Create a new Multi-Reference field with the same slug
3. Re-sync all attributes first
4. Then run the product-attribute reference sync

---

## How to Run

### Recommended Order:
1. **Sync Attributes** → ensures all attribute records have `webflow_item_id`
2. **Sync Products** → ensures all products have `webflow_item_id`
3. **Sync Product-Attribute References** → links products to attributes via multi-reference

### Manual Trigger:
- Use the Manual Trigger in each n8n workflow
- Or call the API endpoints directly

### Scheduled:
All three workflows run on a 6-hour schedule by default.

---

## Troubleshooting

### "unresolved_count" is high
Attributes haven't been synced to Webflow yet. Run the attribute sync workflow first.

### Webflow returns 400 error on PATCH
- Check that the product fields are configured as **Multi-Reference** (not Plain Text)
- Verify the Webflow Item IDs are valid 24-character hex strings
- Check the field slug matches exactly

### Product not appearing in reference sync
Products must have a `webflow_item_id` (i.e., been synced at least once). Run the product sync workflow first.

### Adding new attribute types
1. Add the attribute type to `ATTRIBUTE_MULTIREF_FIELD_SLUGS` in `webflow_attributes.py`
2. Create the corresponding multi-reference field in Webflow's Products collection
3. Ensure the attribute type name matches what's used in the `attribute_links` child table

---

## Code Reference

| File | Purpose |
|------|---------|
| `webflow_attributes.py` | Attribute export API + multi-reference resolution |
| `webflow_export.py` | Product export API (includes multiref data) |
| `webflow_product_sync.json` | n8n workflow: full product sync |
| `webflow_product_attribute_ref_sync.json` | n8n workflow: dedicated reference sync |
| `webflow_attribute_sync.json` | n8n workflow: attribute sync |
