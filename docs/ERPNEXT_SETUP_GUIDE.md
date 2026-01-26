# ERPNext Setup Guide for Webflow Integration Testing

## Overview

This guide walks you through setting up test data in ERPNext so the Webflow developer can test:
1. **Product catalog sync** (n8n workflows)
2. **Real-time product API** (JavaScript calls)
3. **Fixture configurator** (interactive configuration)

---

## Quick Start Checklist

- [ ] Create base attributes (CCT, Output Level, Finish, etc.)
- [ ] Create LED Tape Specs
- [ ] Create Tape Offerings
- [ ] Create Fixture Template with allowed options
- [ ] Create Webflow Category
- [ ] Create Webflow Product linked to template
- [ ] Set up API user for n8n
- [ ] Test API endpoints
- [ ] Trigger first sync

---

## Part 1: Create Base Attributes

These are the foundational lookup tables that define available configuration options.

### 1.1 CCT (Color Temperature)

**Doctype:** `ilL-Attribute-CCT`

Create at least 3 test CCT values:

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `name` | 2700K | 3000K | 4000K |
| `code` | 27 | 30 | 40 |
| `kelvin` | 2700 | 3000 | 4000 |
| `label` | 2700K Warm White | 3000K Warm White | 4000K Neutral White |
| `description` | Warm, cozy tone | Warm, inviting | Neutral, crisp |

```
Desk > ilL-Attribute-CCT > + Add CCT
```

### 1.2 Output Level

**Doctype:** `ilL-Attribute-Output Level`

Create at least 3 output levels:

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `name` | 300 lm/ft | 450 lm/ft | 600 lm/ft |
| `sku_code` | 300 | 450 | 600 |
| `value` | 300 | 450 | 600 |

```
Desk > ilL-Attribute-Output Level > + Add Output Level
```

### 1.3 CRI (Color Rendering Index)

**Doctype:** `ilL-Attribute-CRI`

| Field | Value 1 | Value 2 |
|-------|---------|---------|
| `name` | CRI 90+ | CRI 95+ |
| `code` | 90 | 95 |
| `ra_value` | 90 | 95 |

```
Desk > ilL-Attribute-CRI > + Add CRI
```

### 1.4 LED Package

**Doctype:** `ilL-Attribute-LED Package`

| Field | Value 1 | Value 2 |
|-------|---------|---------|
| `name` | Full Spectrum 2835 | Standard 2835 |
| `code` | FS | ST |
| `spectrum_type` | Full Spectrum | Standard |

```
Desk > ilL-Attribute-LED Package > + Add LED Package
```

### 1.5 Environment Rating

**Doctype:** `ilL-Attribute-Environment Rating`

| Field | Value 1 | Value 2 |
|-------|---------|---------|
| `name` | Dry | Wet |
| `code` | D | W |
| `notes` | Indoor dry locations | Outdoor/wet locations |

```
Desk > ilL-Attribute-Environment Rating > + Add Environment Rating
```

### 1.6 SDCM (Color Consistency)

**Doctype:** `ilL-Attribute-SDCM`

| Field | Value 1 | Value 2 |
|-------|---------|---------|
| `name` | SDCM 2 | SDCM 3 |
| `code` | 2 | 3 |
| `value` | 2 | 3 |

```
Desk > ilL-Attribute-SDCM > + Add SDCM
```

### 1.7 Lens Appearance

**Doctype:** `ilL-Attribute-Lens Appearance`

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `name` | Clear | Frosted | Milky |
| `code` | CLR | FRO | MLK |
| `transmission_pct` | 95 | 85 | 70 |

```
Desk > ilL-Attribute-Lens Appearance > + Add Lens Appearance
```

### 1.8 Finish

**Doctype:** `ilL-Attribute-Finish`

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `name` | Black | White | Silver |
| `code` | BK | WH | SV |
| `finish_name` | Black | White | Silver |
| `type` | Powder Coat | Powder Coat | Anodized |

```
Desk > ilL-Attribute-Finish > + Add Finish
```

### 1.9 Mounting Method

**Doctype:** `ilL-Attribute-Mounting Method`

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `name` | Surface | Recessed | Suspended |
| `code` | SM | RC | SP |
| `label` | Surface Mount | Recessed Mount | Suspended |

```
Desk > ilL-Attribute-Mounting Method > + Add Mounting Method
```

### 1.10 Power Feed Type

**Doctype:** `ilL-Attribute-Power Feed Type`

| Field | Value 1 | Value 2 | Value 3 |
|-------|---------|---------|---------|
| `label` | Left End | Right End | Back Feed |
| `code` | L | R | B |
| `type` | Left | Right | Back |

```
Desk > ilL-Attribute-Power Feed Type > + Add Power Feed Type
```

### 1.11 Output Voltage

**Doctype:** `ilL-Attribute-Output Voltage`

| Field | Value 1 | Value 2 |
|-------|---------|---------|
| `name` | 24VDC | 12VDC |
| `voltage` | 24 | 12 |

```
Desk > ilL-Attribute-Output Voltage > + Add Output Voltage
```

---

## Part 2: Create LED Tape Specs

**Doctype:** `ilL-Spec-LED Tape`

First, create an Item in ERPNext for the tape, then link it.

### 2.1 Create Item

```
Stock > Item > + Add Item
```

| Field | Value |
|-------|-------|
| Item Code | TAPE-FS-24V-300 |
| Item Name | Full Spectrum LED Tape 24V 300lm |
| Item Group | LED Tape |
| Stock UOM | Feet |
| Is Stock Item | Yes |
| Is Sales Item | Yes |

### 2.2 Create LED Tape Spec

```
Desk > ilL-Spec-LED Tape > + Add LED Tape Spec
```

| Field | Value |
|-------|-------|
| `item` | TAPE-FS-24V-300 |
| `input_voltage` | 24VDC |
| `watts_per_foot` | 4.5 |
| `voltage_drop_max_run_length_ft` | 30 |
| `lumens_per_foot` | 300 |
| `cri_typical` | 90 |
| `cut_increment_mm` | 50 |

Create additional tape specs for different output levels (450 lm/ft, 600 lm/ft).

---

## Part 3: Create Tape Offerings

**Doctype:** `ilL-Rel-Tape Offering`

Tape Offerings combine a tape spec with specific attributes (CCT, CRI, LED Package, Output Level).

```
Desk > ilL-Rel-Tape Offering > + Add Tape Offering
```

### Create Multiple Offerings for Cascading Test

| tape_spec | cct | cri | sdcm | led_package | output_level | is_active |
|-----------|-----|-----|------|-------------|--------------|-----------|
| TAPE-FS-24V-300 | 2700K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 300 lm/ft | ✓ |
| TAPE-FS-24V-300 | 3000K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 300 lm/ft | ✓ |
| TAPE-FS-24V-300 | 4000K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 300 lm/ft | ✓ |
| TAPE-FS-24V-450 | 2700K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 450 lm/ft | ✓ |
| TAPE-FS-24V-450 | 3000K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 450 lm/ft | ✓ |
| TAPE-FS-24V-600 | 3000K | CRI 90+ | SDCM 2 | Full Spectrum 2835 | 600 lm/ft | ✓ |

This creates cascading test data:
- All CCTs available for 300 lm/ft
- Only 2700K and 3000K for 450 lm/ft
- Only 3000K for 600 lm/ft

---

## Part 4: Create Fixture Template

**Doctype:** `ilL-Fixture-Template`

```
Desk > ilL-Fixture-Template > + Add Fixture Template
```

### 4.1 Basic Info

| Field | Value |
|-------|-------|
| `template_code` | RA01 |
| `template_name` | RA01 Linear |
| `is_active` | ✓ |
| `default_profile_family` | RA01 |
| `default_profile_stock_len_mm` | 2000 |
| `assembled_max_len_mm` | 2590 |

### 4.2 Allowed Tape Offerings (Child Table)

Add entries to the `allowed_tape_offerings` table:

| tape_offering | is_default | environment_rating | lens_appearance |
|---------------|------------|-------------------|-----------------|
| TAPE-FS-24V-300-2700K | ✓ | Dry | Clear |
| TAPE-FS-24V-300-3000K | | Dry | Clear |
| TAPE-FS-24V-300-4000K | | Dry | Clear |
| TAPE-FS-24V-450-2700K | | Dry | Clear |
| TAPE-FS-24V-450-3000K | | Dry | Frosted |
| TAPE-FS-24V-600-3000K | | Dry | Frosted |
| TAPE-FS-24V-300-3000K | | Wet | Frosted |

**Important:** The `environment_rating` field in this child table is used for cascading filters.

### 4.3 Allowed Options (Child Table)

Add entries to the `allowed_options` table for non-tape options:

| option_type | finish/lens_appearance/mounting_method | is_default | is_active |
|-------------|----------------------------------------|------------|-----------|
| Finish | Black | ✓ | ✓ |
| Finish | White | | ✓ |
| Finish | Silver | | ✓ |
| Lens Appearance | Clear | ✓ | ✓ |
| Lens Appearance | Frosted | | ✓ |
| Lens Appearance | Milky | | ✓ |
| Mounting Method | Surface | ✓ | ✓ |
| Mounting Method | Recessed | | ✓ |
| Mounting Method | Suspended | | ✓ |

---

## Part 5: Create Webflow Category

**Doctype:** `ilL-Webflow-Category`

```
Desk > ilL-Webflow-Category > + Add Webflow Category
```

| Field | Value |
|-------|-------|
| `name` | Linear Fixtures |
| `slug` | linear-fixtures |
| `description` | Linear LED fixtures for architectural lighting |
| `sort_order` | 1 |
| `is_active` | ✓ |
| `parent_category` | (leave empty for top-level) |

---

## Part 6: Create Webflow Product

**Doctype:** `ilL-Webflow-Product`

```
Desk > ilL-Webflow-Product > + Add Webflow Product
```

### 6.1 Basic Info

| Field | Value |
|-------|-------|
| `product_name` | RA01 Linear |
| `product_slug` | ra01-linear |
| `product_type` | Fixture Template |
| `product_category` | Linear Fixtures |
| `is_active` | ✓ |
| `is_configurable` | ✓ |

### 6.2 Source Linkage

| Field | Value |
|-------|-------|
| `fixture_template` | RA01 |

### 6.3 Descriptions

| Field | Value |
|-------|-------|
| `short_description` | Sleek linear fixture with customizable options |
| `long_description` | (Rich text description of the product) |
| `configurator_intro_text` | Configure your RA01 Linear fixture below |

### 6.4 Length Constraints

| Field | Value |
|-------|-------|
| `min_length_mm` | 305 |
| `max_length_mm` | 3048 |
| `length_increment_mm` | 25 |

### 6.5 Auto-Calculate

| Field | Value |
|-------|-------|
| `auto_calculate_specs` | ✓ |

When you save with `auto_calculate_specs` checked, the system will:
- Populate the `specifications` table from the template
- Populate the `configurator_options` table from the template

### 6.6 Sync Status

| Field | Value |
|-------|-------|
| `sync_status` | Never Synced |

---

## Part 7: Set Up API User for n8n

### 7.1 Create API User

```
Setup > User > + Add User
```

| Field | Value |
|-------|-------|
| Email | n8n-sync@illumenatelighting.com |
| First Name | n8n |
| Last Name | Sync Bot |
| User Type | System User |
| Roles | Add "System Manager" or create custom role |

### 7.2 Generate API Keys

```
Setup > User > [n8n-sync@illumenatelighting.com] > API Access > Generate Keys
```

Save the generated:
- **API Key:** `abc123...`
- **API Secret:** `xyz789...`

### 7.3 Configure n8n Credentials

In n8n, create an "HTTP Header Auth" credential:

| Field | Value |
|-------|-------|
| Name | ERPNext API Key |
| Header Name | Authorization |
| Header Value | `token abc123...:xyz789...` |

---

## Part 8: Test API Endpoints

### 8.1 Test Product Detail API (Public)

```bash
curl -X GET "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_product_detail?sku=ra01-linear"
```

Expected response:
```json
{
  "message": {
    "success": true,
    "product": {
      "item_code": "ra01-linear",
      ...
    }
  }
}
```

### 8.2 Test Configurator Init API (Public)

```bash
curl -X GET "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init?product_slug=ra01-linear"
```

Expected response:
```json
{
  "message": {
    "success": true,
    "product": {
      "slug": "ra01-linear",
      "name": "RA01 Linear",
      "template_code": "RA01"
    },
    "series": {
      "series_code": "RA01",
      "led_package_code": "FS",
      ...
    },
    "options": {
      "environment_ratings": [...],
      "lens_appearances": [...],
      ...
    }
  }
}
```

### 8.3 Test Webflow Export API (Authenticated)

```bash
curl -X GET "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_export.get_webflow_products?sync_status=needs_sync" \
  -H "Authorization: token abc123...:xyz789..."
```

Expected response:
```json
{
  "message": {
    "products": [...],
    "total": 1,
    "limit": 100,
    "offset": 0
  }
}
```

### 8.4 Test Cascading Options

```bash
curl -X GET "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options?product_slug=ra01-linear&step_name=environment_rating&selections=%7B%22environment_rating%22%3A%22Dry%22%7D"
```

---

## Part 9: Verify Data Relationships

### Check Tape Offering Links

```sql
-- Run in Frappe Console or DB
SELECT 
  name,
  tape_spec,
  cct,
  cri,
  led_package,
  output_level,
  is_active
FROM `tabilL-Rel-Tape Offering`
WHERE is_active = 1;
```

### Check Template Tape Offerings

```sql
SELECT 
  parent,
  tape_offering,
  environment_rating,
  is_default
FROM `tabilL-Child-Template-Allowed-TapeOffering`
WHERE parent = 'RA01';
```

### Check Webflow Product

```sql
SELECT 
  name,
  product_name,
  product_slug,
  fixture_template,
  is_configurable,
  sync_status
FROM `tabilL-Webflow-Product`
WHERE is_active = 1;
```

---

## Part 10: Trigger First Sync

### Option 1: Via n8n

1. Open n8n
2. Import the workflow from `n8n_workflows/webflow_product_sync.json`
3. Configure credentials
4. Click "Execute Workflow"

### Option 2: Via API

```bash
curl -X POST "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_export.trigger_sync" \
  -H "Authorization: token abc123...:xyz789..." \
  -H "Content-Type: application/json" \
  -d '{"product_slugs": ["ra01-linear"]}'
```

---

## Part 11: Troubleshooting

### Common Issues

#### 1. "Unknown column" errors

These occur when the code references a field that doesn't exist on the doctype.
- Check the doctype JSON for actual field names
- Common fixes already applied:
  - `tape_item` → `tape_spec` (in ilL-Rel-Tape Offering)
  - `code` → `sku_code` (in ilL-Attribute-Output Level)
  - `display_name` → `finish_name` (in ilL-Attribute-Finish)

#### 2. Empty configurator options

- Verify `allowed_tape_offerings` has entries in the Fixture Template
- Verify each tape offering's `is_active` is checked
- Verify `environment_rating` is set on tape offering rows

#### 3. Cascading not filtering correctly

- Check that `environment_rating` on `allowed_tape_offerings` matches the attribute name exactly
- Verify CCT values on tape offerings match attribute names

#### 4. Sync status stuck on "Never Synced"

- Check n8n workflow is calling `mark_product_synced` after successful Webflow push
- Verify the `webflow_item_id` is being passed back

#### 5. API returns 403 Forbidden

- For authenticated endpoints, verify API key format: `token KEY:SECRET`
- Verify user has correct role permissions
- Check if endpoint requires `allow_guest=False` but no auth provided

---

## Part 12: Minimum Test Data Summary

| Doctype | Minimum Records |
|---------|-----------------|
| ilL-Attribute-CCT | 3 |
| ilL-Attribute-Output Level | 3 |
| ilL-Attribute-CRI | 2 |
| ilL-Attribute-LED Package | 1 |
| ilL-Attribute-Environment Rating | 2 |
| ilL-Attribute-SDCM | 1 |
| ilL-Attribute-Lens Appearance | 3 |
| ilL-Attribute-Finish | 3 |
| ilL-Attribute-Mounting Method | 3 |
| ilL-Attribute-Power Feed Type | 3 |
| ilL-Attribute-Output Voltage | 1 |
| Item (Tape) | 3 |
| ilL-Spec-LED Tape | 3 |
| ilL-Rel-Tape Offering | 7 |
| ilL-Fixture-Template | 1 |
| ilL-Webflow-Category | 1 |
| ilL-Webflow-Product | 1 |

---

## Part 13: Data Entry Order

Follow this exact order to avoid dependency issues:

1. **Output Voltage** (no dependencies)
2. **CCT** (no dependencies)
3. **CRI** (no dependencies)
4. **SDCM** (no dependencies)
5. **LED Package** (no dependencies)
6. **Output Level** (no dependencies)
7. **Environment Rating** (no dependencies)
8. **Lens Appearance** (no dependencies)
9. **Finish** (no dependencies)
10. **Mounting Method** (no dependencies)
11. **Power Feed Type** (no dependencies)
12. **Item (Tape products)** (no dependencies)
13. **LED Tape Spec** (depends on: Item, Output Voltage)
14. **Tape Offering** (depends on: LED Tape Spec, CCT, CRI, SDCM, LED Package, Output Level)
15. **Fixture Template** (depends on: Tape Offering, Environment Rating, Lens Appearance)
16. **Webflow Category** (no dependencies)
17. **Webflow Product** (depends on: Fixture Template, Webflow Category)

---

## Handoff Checklist

Before handing off to the Webflow developer, confirm:

- [ ] All base attributes created with test data
- [ ] At least 3 tape specs created
- [ ] At least 7 tape offerings created (for cascading test)
- [ ] Fixture template created with:
  - [ ] Multiple tape offerings assigned
  - [ ] Multiple environment ratings represented
  - [ ] Allowed options for Finish, Lens, Mounting
- [ ] Webflow Product created and linked to template
- [ ] API user created with keys
- [ ] Public endpoints tested and returning data
- [ ] n8n credentials configured
- [ ] First sync attempted (even if errors, provides useful debugging info)

---

## Contact

For questions about this setup, contact the ERPNext development team.

**ERPNext Instance:** https://illumenatelighting.v.frappe.cloud
