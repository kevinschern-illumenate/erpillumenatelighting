# Phase 2 Sprint — Rules Engine v1 Implementation Notes

## Overview

This document describes the implementation of the Rules Engine v1 API, including:
- Task 1.1: Define request/response schema for the engine
- Epic 3: Computation layer (lengths, segments, runs)

## Epic 3 — Computation Layer Implementation

### Task 3.1: Length Math (Locked Rules)

**Implementation:**
- E = `endcap_style.allowance_mm_per_side` from ilL-Attribute-Endcap Style
- A_leader = `template.leader_allowance_mm_per_fixture` (default: 15mm)
- L_internal = L_req - 2E - A_leader
- L_tape_cut = floor(L_internal / cut_increment) * cut_increment
- L_mfg = L_tape_cut + 2E + A_leader
- difference = L_req - L_mfg

**Response Fields:** `endcap_allowance_mm_per_side`, `leader_allowance_mm_per_fixture`, `internal_length_mm`, `tape_cut_length_mm`, `manufacturable_overall_length_mm`, `difference_mm`, `requested_overall_length_mm`

### Task 3.2: Segmentation Plan (Profile + Lens)

**Implementation:**
- profile_stock_len_mm from ilL-Spec-Profile or template default
- segments_count = ceil(L_mfg / profile_stock_len_mm)
- segments[] with N-1 full stock segments + remainder segment
- Lens segmentation mirrors profile (stick type)

**Response Fields:** `profile_stock_len_mm`, `segments_count`, `segments[]`

### Task 3.3: Run Splitting (Voltage-Drop + 85W Limit)

**Implementation:**
- MAX_WATTS_PER_RUN = 85W constant
- total_ft = L_tape_cut_mm / 304.8
- max_run_ft_by_watts = 85 / watts_per_ft
- max_run_ft_by_voltage_drop from ilL-Spec-LED Tape (optional)
- max_run_ft_effective = min(max_run_ft_by_watts, max_run_ft_by_voltage_drop)
- runs_count = ceil(total_ft / max_run_ft_effective)
- runs[] using "full runs then remainder" strategy
- leader_qty = runs_count

**Response Fields:** `max_run_ft_by_watts`, `max_run_ft_by_voltage_drop`, `max_run_ft_effective`, `runs_count`, `leader_qty`, `runs[]`, `total_watts`

### Task 3.4: Assembly Mode Rule

**Implementation:**
- assembled_max_len_mm from template (default: 2590mm ~8.5ft)
- assembly_mode = "ASSEMBLED" if L_mfg <= assembled_max_len_mm, else "SHIP_PIECES"

**Response Fields:** `assembly_mode`, `assembled_max_len_mm`

## What Was Implemented

### 1. API Module Structure
- Created `/illumenate_lighting/illumenate_lighting/api/` directory
- Organized API code separate from DocTypes for clean architecture

### 2. Core API Endpoint (`validate_and_quote`)

**Location:** `illumenate_lighting/api/configurator_engine.py`

A single, comprehensive API endpoint that:
1. Validates fixture configurations against business rules
2. Computes manufacturable dimensions and outputs (Epic 3)
3. Resolves component items
4. Calculates pricing
5. Creates/updates ilL-Configured-Fixture documents

**Whitelisted:** Yes (`@frappe.whitelist()` decorator)

### 3. Request Schema (11 Fields)

All fields are required except `qty`:

| Field | Type | Description |
|-------|------|-------------|
| fixture_template_code | string | Fixture template identifier |
| finish_code | string | Finish option |
| lens_appearance_code | string | Lens appearance option |
| mounting_method_code | string | Mounting method option |
| endcap_style_code | string | Endcap style option |
| endcap_color_code | string | Endcap color option |
| power_feed_type_code | string | Power feed type option |
| environment_rating_code | string | Environment rating option |
| tape_offering_id | string | Tape offering identifier |
| requested_overall_length_mm | integer | Requested length in millimeters |
| qty | integer | Quantity (default: 1) |

### 4. Response Schema

Complete response structure includes:

- **is_valid** (boolean): Overall validation status
- **messages[]**: Array of validation/info/warning messages
  - Each with: severity, text, field
- **computed**: All computed/calculated values (Epic 3)
  - Task 3.1: endcap_allowance, leader_allowance, internal_length, tape_cut_length, L_mfg, difference
  - Task 3.2: segments_count, profile_stock_len_mm, segments[]
  - Task 3.3: runs_count, leader_qty, total_watts, max_run_ft_*, runs[]
  - Task 3.4: assembly_mode, assembled_max_len_mm
- **resolved_items**: Resolved component item codes
  - profile_item, lens_item, endcap_item, mounting_item, leader_item
  - driver_plan (Phase 2: suggested only)
- **pricing**: Complete pricing breakdown
  - msrp_unit, tier_unit
  - adder_breakdown[]: Itemized component pricing
- **configured_fixture_id**: Created/updated document name

### 5. Key Implementation Details

#### Configuration Hashing
- Uses SHA-256 hash (first 32 hex chars = 128 bits of entropy)
- Ensures identical configurations reuse same document
- Prevents duplication in database
- Hash becomes document name via `autoname: "field:config_hash"`

#### Validation Logic
- Checks fixture template exists
- Validates all required fields are present
- Validates requested length > 0
- Returns detailed error messages with field references
- Placeholder for option validation against template constraints

#### Computation Logic (Placeholder v1)
- Fixed allowances (ready for dynamic lookup)
- Single segment/run assumption (ready for complex calculations)
- Placeholder wattage calculation
- Returns structured segment and run plans

#### Item Resolution (Placeholder v1)
- Returns formatted placeholder item codes
- Ready for mapping table lookups
- Driver plan marked as "suggested" status

#### Pricing Calculation (Placeholder v1)
- Simple base + adder formula
- Itemized breakdown for transparency
- Ready for price list integration

#### Document Management
- Creates ilL-Configured-Fixture documents
- Updates if configuration hash already exists
- Stores complete configuration, computed values, and pricing snapshot
- Properly handles segments, runs, drivers, and pricing child tables

### 6. Testing

**Test Suite:** `illumenate_lighting/api/test_configurator_engine.py`

7 comprehensive test cases:
1. Basic validate_and_quote functionality
2. Missing fixture template handling
3. Invalid length validation
4. Missing required field validation
5. Configuration reuse (deduplication)
6. Response schema completeness
7. Proper test data cleanup

All tests use FrappeTestCase and follow framework conventions.

### 7. Documentation

**API Documentation:** `illumenate_lighting/api/README.md`

Comprehensive documentation includes:
- Complete schema reference
- Field descriptions
- Example requests and responses
- Usage examples (Python, JavaScript, curl)
- Implementation notes
- Testing instructions

### 8. Code Quality

- ✅ Passes ruff linting (all checks)
- ✅ Formatted with ruff (consistent style)
- ✅ All code review issues addressed
- ✅ Security scan passed (0 vulnerabilities)
- ✅ Comprehensive inline documentation
- ✅ Type hints for all functions

## What's Ready for Future Phases

### Completed (Epic 3)

1. **Dimension Computation** ✅
   - Dynamic lookup from endcap style (`allowance_mm_per_side`)
   - Leader allowance from template (`leader_allowance_mm_per_fixture`)
   - Proper L_internal, L_tape_cut, L_mfg calculations

2. **Segment/Run Calculation** ✅
   - Multi-segment logic based on profile stock length
   - Run splitting based on min(voltage-drop limit, 85W limit)
   - Proper run count and leader_qty calculation

### Completed (Epic 4)

1. **Baseline Pricing Formula (Task 4.1)** ✅
   - Base price from template (`base_price_msrp`)
   - Price per foot calculation using configurable length basis
   - `pricing_length_basis` = "L_tape_cut" or "L_mfg"
   - $/ft × length calculation with proper mm to ft conversion
   - Option adders from `ilL-Child-Template-Allowed-Option.msrp_adder`
   - Tape offering pricing class adder support

2. **Pricing Snapshot Storage (Task 4.2)** ✅
   - `ilL-Child-Pricing-Snapshot` child table on Configured Fixture
   - Stores: msrp_unit, tier_unit, adder_breakdown_json, timestamp
   - Auditable snapshot of quoted prices

### Remaining Placeholders

1. **Lens Segmentation (Continuous)**
   - Current: Mirrors profile segmentation (works for stick lenses)
   - Ready for: Continuous lens max length support

2. **Customer Tier/Price List Logic**
   - Current: tier_unit = msrp_unit (MSRP only placeholder)
   - Ready for: Customer -> Price List -> apply discount/multiplier

### Completed (Epic 5)

1. **Driver Auto-Selection Algorithm (Task 5.1)** ✅
   - Query eligible drivers from ilL-Rel-Driver-Eligibility
   - Filter by tape voltage (driver.voltage_output == tape_spec.input_voltage)
   - Filter by dimming protocol (driver.dimming_protocol == tape_spec.dimming_protocol)
   - Constraints: sum(outputs) >= runs_count AND sum(W_usable) >= total_watts
   - W_usable = usable_load_factor × max_wattage (default 0.8 × W_rated = 80% capacity)
   - Selection policy: lowest cost if cost exists, else smallest rated wattage
   - Multi-driver support: adds multiples of same model until constraints met

2. **Driver Plan Persistence (Task 5.2)** ✅
   - Populate `drivers` child table on ilL-Configured-Fixture
   - Store: driver_item, driver_qty, outputs_used, mapping_notes
   - Sequential run→output mapping notes for MVP

### Integration Points

The API is ready for integration with:

1. **Frontend Applications**
   - Portal
   - Next.js application
   - Any REST API consumer

2. **ERP Workflows**
   - Sales Order creation
   - BOM generation
   - Work Order creation

3. **External Systems**
   - API tokens for authentication
   - Standard Frappe REST API patterns

## File Summary

| File | Lines | Purpose |
|------|-------|---------|
| configurator_engine.py | ~750 | Main API implementation (with Epic 3) |
| test_configurator_engine.py | ~750 | Test suite (with Epic 3 tests) |
| README.md | ~450 | API documentation |
| __init__.py | 6 | Module initialization |
| IMPLEMENTATION_NOTES.md | ~300 | Implementation notes |

## Acceptance Criteria Met

✅ One JSON schema (documented in code) used by portal and future Next.js
✅ Request fields include all minimum requirements
✅ Response fields include all minimum requirements  
✅ validate_and_quote endpoint implemented
✅ create_or_update_configured_fixture functionality (merged into validate_and_quote)
✅ Comprehensive documentation
✅ Test coverage
✅ Code quality standards met

## Next Steps

## Phase 3 — Manufacturing Artifacts Implementation

### What Was Implemented

#### Epic 2 — Configured Item Generation (ILL-... code + reuse rules)

**Task 2.1: Implement configured Item code generator** ✅

- Item naming convention: `ILL-{config_hash[:8].upper()}`
- Friendly item name: `{template_name} - {finish} - {lens} - {length}mm`
- Item group: "Configured Fixtures"
- UOM: "Nos" (Each)
- Flags: `is_stock_item=1`, `has_serial_no=1` (for finished goods)
- Reuse policy: If config_hash already has a configured_item, reuse it

#### Epic 3 — BOM Generation from Configured Fixture

**Task 3.1: Define BOM "roles" and deterministic BOM builder** ✅

BOM roles implemented:
- Profile (stock sticks, qty = segments_count)
- Lens (sticks, qty = segments_count)
- Endcaps (2 + extra pair = 4 total)
- Mounting accessories (qty from mapping rule)
- LED tape (total length in feet)
- Leader cables (qty = runs_count)
- Drivers (from driver plan)

**Task 3.2: LED tape quantity modeling** ✅

Implemented Option A (recommended MVP):
- One BOM line with total length (UOM = Foot)
- Cut/run plan in BOM remarks

**Task 3.3: Endcap "extra pair" rule** ✅

- Base: 2 endcaps for the fixture
- Extra pair: +2 more for contingency
- Total: 4 endcaps per BOM

#### Epic 5 — Work Order Creation with Operations + Traveler Notes

**Task 5.1: Define routing/operations template** ✅

Operations defined (MVP):
1. Cut Profile
2. Cut Lens
3. Cut Tape
4. Solder/Terminate
5. Assemble
6. Test
7. Label
8. Pack
9. Ship

**Task 5.2: Traveler content generation** ✅

Traveler includes:
- Requested vs manufacturable length
- Segment cut list (profile + lens)
- Tape cut length and run breakdown
- Runs count and leader qty
- Driver model(s) + qty and mapping
- Endcap selection and "extra pair included"
- QC: Functional test pass/fail field prompt
- Serial number capture prompt

#### Epic 6 — Workflow Trigger Points

**Task 6.1: Add button on Sales Order** ✅

- Button: "Generate Item/BOM/WO" under Actions menu
- Only shows for submitted Sales Orders with configured fixtures
- Processes all line items with ill_configured_fixture
- Updates fixture with links to created artifacts

**Task 6.2: Idempotency + "already generated" protections** ✅

- Skip if artifact already exists (configurable)
- Validate Work Order qty matches
- Store engine_version on configured fixture

#### Epic 7 — Serial/Batch MVP Wiring

**Task 7.1: Finished good serial capture plan** ✅

Custom fields on Work Order:
- `ill_functional_test_result`: Select (Pass/Fail)
- `ill_serial_no`: Data field
- `ill_test_notes`: Small Text
- `ill_configured_fixture`: Link to configured fixture

Custom field on Item:
- `custom_ill_configured_fixture`: Link back to fixture

### File Summary

| File | Purpose |
|------|---------|
| manufacturing_generator.py | Manufacturing artifacts generator (Item/BOM/WO) |
| test_manufacturing_generator.py | Test suite for manufacturing generator |
| custom_field.json (updated) | Added Work Order and Item custom fields |
| sales_order.js | Button for generating artifacts from SO |
| hooks.py (updated) | Added Sales Order doctype_js hook |

### Acceptance Criteria Met

✅ Submitting the workflow does not create duplicate Items for the same config_hash
✅ A single BOM is generated per configured item with all required component Items
✅ BOM always reflects correct total tape length and is consistent with run plan
✅ Every BOM includes the contingency endcaps (4 total)
✅ Engine generates a driver plan deterministically for any valid configuration
✅ Configured Fixture always carries the driver plan used to generate BOM/WO
✅ Every WO includes operations in correct sequence
✅ Production can build from the WO without opening the configurator
✅ A user can run the automation on-demand, safely re-run without duplicating artifacts
✅ No duplicate WOs or BOMs from repeated clicks
✅ Production has a clear place to record functional test + serial number

## Support

For questions about this implementation:
- Review the API documentation: `illumenate_lighting/api/README.md`
- Check the test suite: `illumenate_lighting/api/test_configurator_engine.py`
- Check the manufacturing generator tests: `illumenate_lighting/api/test_manufacturing_generator.py`
- Examine the code comments in `configurator_engine.py` and `manufacturing_generator.py`
