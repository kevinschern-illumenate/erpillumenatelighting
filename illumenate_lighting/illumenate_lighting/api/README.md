# Rules Engine v1 API Documentation

## Overview

The Rules Engine v1 API provides a server-side configurator engine for validating, computing, and pricing fixture configurations. This API serves as the single source of truth for the API contract used by both the portal and future Next.js applications.

## API Endpoint

### `validate_and_quote`

**Path:** `illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote`

**Method:** POST (Frappe Whitelisted API)

**Description:** Validates a fixture configuration, computes manufacturable outputs, calculates pricing, and creates/updates an ilL-Configured-Fixture document.

## Request Schema

The API accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fixture_template_code` | string | Yes | Code of the fixture template |
| `finish_code` | string | Yes | Finish option code |
| `lens_appearance_code` | string | Yes | Lens appearance option code |
| `mounting_method_code` | string | Yes | Mounting method option code |
| `endcap_style_code` | string | Yes | Endcap style option code |
| `endcap_color_code` | string | Yes | Endcap color option code |
| `power_feed_type_code` | string | Yes | Power feed type option code |
| `environment_rating_code` | string | Yes | Environment rating option code |
| `tape_offering_id` | string | Yes | Tape offering ID or code |
| `requested_overall_length_mm` | integer | Yes | Requested overall length in millimeters |
| `qty` | integer | No | Quantity (default: 1) |

### Example Request

```json
{
  "fixture_template_code": "TEMPLATE-001",
  "finish_code": "FINISH-ANODIZED",
  "lens_appearance_code": "LENS-CLEAR",
  "mounting_method_code": "MOUNT-SURFACE",
  "endcap_style_code": "ENDCAP-FLAT",
  "endcap_color_code": "ENDCAP-WHITE",
  "power_feed_type_code": "POWER-WIRE",
  "environment_rating_code": "ENV-DRY",
  "tape_offering_id": "TAPE-24V-3000K",
  "requested_overall_length_mm": 1000,
  "qty": 1
}
```

## Response Schema

The API returns a comprehensive response with the following structure:

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | boolean | Overall validation status (true if configuration is valid) |
| `messages` | array | Array of validation/info messages |
| `computed` | object | Computed/calculated values |
| `resolved_items` | object | Resolved item codes/IDs |
| `pricing` | object | Pricing information |
| `configured_fixture_id` | string | Name of the created/updated ilL-Configured-Fixture document |

### Messages Array

Each message in the `messages` array has:

| Field | Type | Description |
|-------|------|-------------|
| `severity` | string | Message severity: "error", "warning", or "info" |
| `text` | string | Human-readable message text |
| `field` | string | Optional: Name of the related field |

### Computed Object

The computed object contains all calculated values from the Epic 3 computation layer.

#### Task 3.1: Length Math (Locked Rules)

| Field | Type | Description |
|-------|------|-------------|
| `endcap_allowance_mm_per_side` | float | E = endcap_style.mm_per_side from Endcap Style attribute |
| `leader_allowance_mm_per_fixture` | float | A_leader = 15mm default or from template |
| `internal_length_mm` | integer | L_internal = L_req - 2E - A_leader |
| `tape_cut_length_mm` | integer | L_tape_cut = floor(L_internal / cut_increment) * cut_increment |
| `manufacturable_overall_length_mm` | integer | L_mfg = L_tape_cut + 2E + A_leader |
| `difference_mm` | integer | Difference = L_req - L_mfg |
| `requested_overall_length_mm` | integer | Original requested length |

#### Task 3.2: Segmentation Plan (Profile + Lens)

| Field | Type | Description |
|-------|------|-------------|
| `profile_stock_len_mm` | integer | Profile stock length from spec or template default |
| `segments_count` | integer | ceil(L_mfg / profile_stock_len_mm) |
| `segments` | array | Array of segment objects (cut plan) |

#### Task 3.3: Run Splitting (Voltage-Drop + 85W Limit)

| Field | Type | Description |
|-------|------|-------------|
| `runs_count` | integer | ceil(total_ft / max_run_ft_effective) |
| `leader_qty` | integer | Leader cable quantity (= runs_count) |
| `total_watts` | float | Total wattage of the fixture |
| `max_run_ft_by_watts` | float | 85W / watts_per_ft |
| `max_run_ft_by_voltage_drop` | float | From tape spec (null if not provided) |
| `max_run_ft_effective` | float | min(max_run_ft_by_watts, max_run_ft_by_voltage_drop) |
| `runs` | array | Array of run objects (run plan) |

#### Task 3.4: Assembly Mode Rule

| Field | Type | Description |
|-------|------|-------------|
| `assembly_mode` | string | "ASSEMBLED" if L_mfg <= assembled_max_len_mm, else "SHIP_PIECES" |
| `assembled_max_len_mm` | integer | Maximum length for assembled shipping |

#### Segment Object

| Field | Type | Description |
|-------|------|-------------|
| `segment_index` | integer | Sequential index of the segment |
| `profile_cut_len_mm` | integer | Profile cut length in millimeters |
| `lens_cut_len_mm` | integer | Lens cut length in millimeters |
| `notes` | string | Optional notes about the segment |

#### Run Object

| Field | Type | Description |
|-------|------|-------------|
| `run_index` | integer | Sequential index of the run |
| `run_len_mm` | integer | Run length in millimeters |
| `run_watts` | float | Wattage of this run |
| `leader_item` | string | Item code for the leader cable |
| `leader_len_mm` | integer | Leader cable length in millimeters |

### Resolved Items Object

| Field | Type | Description |
|-------|------|-------------|
| `profile_item` | string | Resolved profile item code |
| `lens_item` | string | Resolved lens item code |
| `endcap_item` | string | Resolved endcap item code |
| `mounting_item` | string | Resolved mounting accessory item code |
| `leader_item` | string | Resolved leader cable item code |
| `driver_plan` | object | Driver plan (Phase 2 v1: suggested only) |

#### Driver Plan Object

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "suggested" (Phase 2 v1 placeholder) |
| `drivers` | array | Array of suggested driver objects |

### Pricing Object

The pricing object contains Epic 4 Task 4.1 baseline pricing calculation results.

| Field | Type | Description |
|-------|------|-------------|
| `msrp_unit` | float | MSRP unit price (base + length adder + option adders) |
| `tier_unit` | float | Tier unit price (currently equals msrp_unit - placeholder for customer tier logic) |
| `adder_breakdown` | array | Itemized pricing adders |

#### Pricing Formula

The pricing formula is: `msrp_unit = base + ($/ft × length) + option_adders`

**Components:**
1. **Base Price** - From `ilL-Fixture-Template.base_price_msrp`
2. **Length Adder** - `(length_mm / 304.8) × template.price_per_ft_msrp`
   - Length basis is configurable via `template.pricing_length_basis`:
     - `L_tape_cut` (default): Uses tape cut length for pricing
     - `L_mfg`: Uses manufacturable overall length
3. **Option Adders** - From `ilL-Child-Template-Allowed-Option.msrp_adder` for each selected option:
   - Finish, Lens Appearance, Mounting Method, Endcap Style, Power Feed Type, Environment Rating
4. **Tape Offering Adder** - From `ilL-Attribute-Pricing Class.default_adder` if `tape_offering.pricing_class_override` is set

#### Adder Breakdown Item

| Field | Type | Description |
|-------|------|-------------|
| `component` | string | Component identifier (e.g., "base", "length", "finish") |
| `description` | string | Human-readable description |
| `amount` | float | Price amount for this component |

### Example Response (Success)

```json
{
  "is_valid": true,
  "messages": [
    {
      "severity": "info",
      "text": "Configuration validated successfully",
      "field": null
    }
  ],
  "computed": {
    "endcap_allowance_mm_per_side": 15.0,
    "leader_allowance_mm_per_fixture": 150.0,
    "internal_length_mm": 970,
    "tape_cut_length_mm": 820,
    "manufacturable_overall_length_mm": 1000,
    "difference_mm": 0,
    "segments": [
      {
        "segment_index": 1,
        "profile_cut_len_mm": 970,
        "lens_cut_len_mm": 970,
        "notes": "Single segment configuration"
      }
    ],
    "runs": [
      {
        "run_index": 1,
        "run_len_mm": 820,
        "run_watts": 8.2,
        "leader_item": "LEADER-POWER-WIRE",
        "leader_len_mm": 150
      }
    ],
    "runs_count": 1,
    "total_watts": 8.2,
    "assembly_mode": "ASSEMBLED"
  },
  "resolved_items": {
    "profile_item": "PROFILE-TEMPLATE-001-FINISH-ANODIZED",
    "lens_item": "LENS-LENS-CLEAR-ENV-DRY",
    "endcap_item": "ENDCAP-ENDCAP-FLAT-ENDCAP-WHITE",
    "mounting_item": "MOUNT-MOUNT-SURFACE",
    "leader_item": "LEADER-POWER-WIRE",
    "driver_plan": {
      "status": "suggested",
      "drivers": [
        {
          "item_code": "DRIVER-PLACEHOLDER",
          "qty": 1,
          "watts_capacity": 100.0
        }
      ]
    }
  },
  "pricing": {
    "msrp_unit": 145.0,
    "tier_unit": 101.5,
    "adder_breakdown": [
      {
        "component": "base",
        "description": "Base fixture price",
        "amount": 100.0
      },
      {
        "component": "length",
        "description": "Length adder (1000mm)",
        "amount": 50.0
      },
      {
        "component": "finish",
        "description": "Finish (FINISH-ANODIZED)",
        "amount": 20.0
      },
      {
        "component": "lens",
        "description": "Lens (LENS-CLEAR)",
        "amount": 15.0
      },
      {
        "component": "mounting",
        "description": "Mounting (MOUNT-SURFACE)",
        "amount": 10.0
      }
    ]
  },
  "configured_fixture_id": "a1b2c3d4e5f6g7h8"
}
```

### Example Response (Validation Error)

```json
{
  "is_valid": false,
  "messages": [
    {
      "severity": "error",
      "text": "Fixture template 'INVALID-TEMPLATE' not found",
      "field": "fixture_template_code"
    }
  ],
  "computed": null,
  "resolved_items": null,
  "pricing": null,
  "configured_fixture_id": null
}
```

## Usage Examples

### From Python/Frappe

```python
import frappe
from illumenate_lighting.illumenate_lighting.api.configurator_engine import validate_and_quote

result = validate_and_quote(
    fixture_template_code="TEMPLATE-001",
    finish_code="FINISH-ANODIZED",
    lens_appearance_code="LENS-CLEAR",
    mounting_method_code="MOUNT-SURFACE",
    endcap_style_code="ENDCAP-FLAT",
    endcap_color_code="ENDCAP-WHITE",
    power_feed_type_code="POWER-WIRE",
    environment_rating_code="ENV-DRY",
    tape_offering_id="TAPE-24V-3000K",
    requested_overall_length_mm=1000,
    qty=1
)

if result["is_valid"]:
    print(f"Configuration valid! ID: {result['configured_fixture_id']}")
    print(f"Price: ${result['pricing']['msrp_unit']:.2f}")
else:
    for msg in result["messages"]:
        if msg["severity"] == "error":
            print(f"Error: {msg['text']}")
```

### From JavaScript/REST API

```javascript
frappe.call({
    method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote',
    args: {
        fixture_template_code: 'TEMPLATE-001',
        finish_code: 'FINISH-ANODIZED',
        lens_appearance_code: 'LENS-CLEAR',
        mounting_method_code: 'MOUNT-SURFACE',
        endcap_style_code: 'ENDCAP-FLAT',
        endcap_color_code: 'ENDCAP-WHITE',
        power_feed_type_code: 'POWER-WIRE',
        environment_rating_code: 'ENV-DRY',
        tape_offering_id: 'TAPE-24V-3000K',
        requested_overall_length_mm: 1000,
        qty: 1
    },
    callback: function(r) {
        if (r.message.is_valid) {
            console.log('Configuration valid!', r.message);
        } else {
            console.error('Validation failed:', r.message.messages);
        }
    }
});
```

### From External API (curl)

```bash
curl -X POST \
  'https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: token YOUR_API_KEY:YOUR_API_SECRET' \
  -d '{
    "fixture_template_code": "TEMPLATE-001",
    "finish_code": "FINISH-ANODIZED",
    "lens_appearance_code": "LENS-CLEAR",
    "mounting_method_code": "MOUNT-SURFACE",
    "endcap_style_code": "ENDCAP-FLAT",
    "endcap_color_code": "ENDCAP-WHITE",
    "power_feed_type_code": "POWER-WIRE",
    "environment_rating_code": "ENV-DRY",
    "tape_offering_id": "TAPE-24V-3000K",
    "requested_overall_length_mm": 1000,
    "qty": 1
  }'
```

## Implementation Notes

### Phase 2 v1 Scope

This is the Phase 2 v1 implementation which provides:
- Complete API contract definition
- Request/response schema validation
- Placeholder logic for computation and pricing
- Document creation/update functionality

The following are implemented with placeholder logic and will be enhanced in future phases:
- Dimension computation (currently uses fixed allowances)
- Segment/run calculation (currently assumes single segment)
- Item resolution (currently returns placeholder item codes)
- Pricing calculation (currently uses simple formulas)
- Driver plan (currently returns suggested drivers only)

### Configuration Hashing

The API uses SHA-256 hashing of the configuration parameters to generate a unique identifier (`config_hash`) for each configuration. This ensures that identical configurations reuse the same ilL-Configured-Fixture document, preventing duplication.

### Future Enhancements

Phase 3 and beyond will add:
- Advanced validation against allowed options
- Complex segment and run calculations
- Real item resolution from mapping tables
- Dynamic pricing from price lists
- Driver allocation logic
- ~~BOM generation~~ ✅ Implemented via manufacturing_generator.py
- ~~Work order creation~~ ✅ Implemented via manufacturing_generator.py

## Manufacturing Artifacts Generator

### `generate_manufacturing_artifacts`

**Path:** `illumenate_lighting.illumenate_lighting.api.manufacturing_generator.generate_manufacturing_artifacts`

**Method:** POST (Frappe Whitelisted API)

**Description:** Generates manufacturing artifacts (Item, BOM, Work Order) from a Configured Fixture.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `configured_fixture_id` | string | Yes | Name of the ilL-Configured-Fixture document |
| `qty` | integer | No | Quantity to manufacture (default: 1) |
| `skip_if_exists` | boolean | No | Skip creation if artifacts exist (default: true) |

#### Response

```json
{
  "success": true,
  "messages": [...],
  "item_code": "ILL-ABCD1234",
  "bom_name": "BOM-ILL-ABCD1234-001",
  "work_order_name": "MFG-WO-00001",
  "created": {"item": true, "bom": true, "work_order": true},
  "skipped": {"item": false, "bom": false, "work_order": false}
}
```

### `generate_from_sales_order`

**Path:** `illumenate_lighting.illumenate_lighting.api.manufacturing_generator.generate_from_sales_order`

**Method:** POST (Frappe Whitelisted API)

**Description:** Generates manufacturing artifacts for all configured fixtures on a Sales Order. Can be triggered via the "Generate Item/BOM/WO" button on submitted Sales Orders.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sales_order` | string | Yes | Name of the Sales Order document |

#### Features Implemented

- **Epic 2**: Configured Item generation with ILL-{hash} naming convention
- **Epic 3**: BOM generation with all component roles including endcap extra pair rule
- **Epic 5**: Work Order with traveler notes
- **Epic 6**: Idempotency and reuse policies
- **Epic 7**: Custom fields for functional test and serial number on Work Order

## Testing

A comprehensive test suite is available at `illumenate_lighting/api/test_configurator_engine.py` covering:
- Basic validation and quote functionality
- Missing fixture template handling
- Invalid length validation
- Missing required field validation
- Configuration reuse (deduplication)
- Response schema completeness

Manufacturing generator tests at `illumenate_lighting/api/test_manufacturing_generator.py` covering:
- Basic artifact generation
- Item code naming convention (ILL-{hash})
- Configuration reuse policy
- Endcap extra pair rule (4 total)
- Work Order traveler notes
- Fixture link updates
- Idempotency

Run tests with:
```bash
bench --site your-site run-tests --app illumenate_lighting --module illumenate_lighting.api.test_configurator_engine
bench --site your-site run-tests --app illumenate_lighting --module illumenate_lighting.api.test_manufacturing_generator
```

## Support

For questions or issues with this API, please contact the ilLumenate Lighting development team or create an issue in the repository.
