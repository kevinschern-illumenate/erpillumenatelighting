# Demo Script (10-15 minutes)

This demo script walks through the core functionality of ilLumenate Lighting MVP.
It can be performed with no manual database edits, using only the UI and available actions.

## Version Information

- **Engine Version**: 1.0.0
- **Demo Duration**: 10-15 minutes
- **Last Updated**: January 2026

---

## Prerequisites

Before starting the demo:

1. ✅ Fresh site with `illumenate_lighting` app installed and migrated
2. ✅ Fixtures loaded (SH01 template + mappings)
3. ✅ Two users prepared:
   - **Demo User 1**: `owner@demo.com` - Main demonstrator (has "Can View Pricing" role)
   - **Demo User 2**: `coworker@demo.com` - Coworker for collaboration demo
4. ✅ Both users linked to same Customer ("Demo Company")

---

## Part 1: Project Creation and Company Visibility (3 minutes)

### Step 1.1: Create Public Project

1. Log in as **Demo User 1** (`owner@demo.com`)
2. Navigate to: **ilL-Project** list
3. Click **+ New**
4. Fill in:
   - Project Name: "Demo Retail Store Lighting"
   - Customer: "Demo Company"
   - Leave **is_private** unchecked (public to company)
5. Click **Save**

**Talking Point:** 
> "When I create a project, my coworkers at the same company can automatically see it. This enables team collaboration without manual sharing."

### Step 1.2: Verify Coworker Can See Project

1. Open an incognito/private browser window
2. Log in as **Demo User 2** (`coworker@demo.com`)
3. Navigate to: **ilL-Project** list

**Expected:** 
- "Demo Retail Store Lighting" project is visible
- Coworker can open and view project details

**Talking Point:**
> "See how my coworker can already see this project? Company-wide visibility is the default for easy collaboration."

---

## Part 2: Toggle Private and Add Collaborator (2 minutes)

### Step 2.1: Make Project Private

1. Switch back to **Demo User 1** window
2. Open "Demo Retail Store Lighting" project
3. Check **is_private** checkbox
4. Click **Save**

### Step 2.2: Verify Coworker Lost Access

1. Switch to **Demo User 2** window
2. Refresh the project list
3. Note: Project is no longer visible

**Talking Point:**
> "By making the project private, only I can see it now. This is useful for confidential projects or internal work."

### Step 2.3: Add Collaborator

1. Switch to **Demo User 1** window
2. Open project
3. Scroll to **Collaborators** section
4. Add row:
   - User: `coworker@demo.com`
   - Access Level: "VIEW"
   - Is Active: checked
5. Click **Save**

### Step 2.4: Verify Collaborator Access Restored

1. Switch to **Demo User 2** window
2. Refresh project list
3. Project is now visible again

**Talking Point:**
> "I've added my coworker as a collaborator. They now have view access to this private project. I control exactly who can see sensitive work."

---

## Part 3: Configure SH01 Fixture (3 minutes)

### Step 3.1: Create Fixture Schedule

1. In **Demo User 1** window
2. Navigate to **ilL-Project-Fixture-Schedule**
3. Click **+ New**
4. Fill in:
   - Schedule Name: "Main Floor Fixtures"
   - ilL-Project: "Demo Retail Store Lighting"
   - Customer: (auto-fills from project)
5. Click **Save**

### Step 3.2: Configure a Fixture via API (or Portal)

For this demo, use the Desk console or a pre-built portal interface:

```python
from illumenate_lighting.illumenate_lighting.api.configurator_engine import validate_and_quote

result = validate_and_quote(
    fixture_template_code="SH01",
    finish_code="Silver",
    lens_appearance_code="White",
    mounting_method_code="Metal Clip",
    endcap_style_start_code="Hole",
    endcap_style_end_code="Hole",
    endcap_color_code="GRY",
    power_feed_type_code="Wire",
    environment_rating_code="Dry",
    tape_offering_id="[valid-tape-offering]",
    requested_overall_length_mm=1500,
    qty=2
)

print(f"Valid: {result['is_valid']}")
print(f"Manufacturable Length: {result['computed']['manufacturable_overall_length_mm']}mm")
print(f"Price: ${result['pricing']['msrp_unit']}")
print(f"Configured Fixture: {result['configured_fixture_id']}")
```

**Talking Point:**
> "The configurator validates my selections, calculates the manufacturable length based on tape cut increments, and provides an instant price quote."

### Step 3.3: Add to Schedule

1. Add schedule line with:
   - Line ID: "1"
   - Qty: 2
   - Configured Fixture: (from result above)
   - Location: "Display Cases"
   - Notes: "High CRI for merchandise"
2. Save schedule

**Talking Point:**
> "I've added this fixture to our schedule. The configuration is saved and can be reused or modified later."

---

## Part 4: Create Sales Order and Generate Work Order (3 minutes)

### Step 4.1: Ensure Configured Item Exists

Before creating SO, we need to generate the configured item:

```python
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

result = generate_manufacturing_artifacts(
    configured_fixture_id="[configured-fixture-id]",
    qty=2
)

print(f"Item: {result['item_code']}")
print(f"BOM: {result['bom_name']}")
print(f"Work Order: {result['work_order_name']}")
```

**Talking Point:**
> "Behind the scenes, we've created the manufactured item, its Bill of Materials, and a Work Order - all automatically from the configuration."

### Step 4.2: Create Sales Order

1. Open the fixture schedule
2. Click **Create Sales Order** button (or use API)
3. Sales Order is created with line items

**Expected:**
- SO created with customer from schedule
- Line items reference configured fixtures
- Schedule status changes to "ORDERED"

**Talking Point:**
> "One click creates a Sales Order. Each line item links back to the exact configuration the customer approved."

### Step 4.3: View Work Order

1. Navigate to **Work Order** list
2. Open the Work Order created above
3. Show the **Remarks** field with traveler notes

**Talking Point:**
> "The Work Order includes detailed traveler notes: cut lengths, run breakdowns, driver selection, and assembly instructions. Our production team has everything they need."

---

## Part 5: Generate Unpriced PDF Export (2 minutes)

### Step 5.1: Generate PDF

```python
from illumenate_lighting.illumenate_lighting.api.exports import generate_schedule_pdf

result = generate_schedule_pdf(
    schedule_id="[schedule-name]",
    priced=False
)

print(f"Download: {result['download_url']}")
```

Or use the UI export button if available.

### Step 5.2: View PDF

1. Download and open the PDF
2. Show:
   - Schedule header with project name
   - Line items with fixture details
   - No pricing columns (unpriced export)

**Talking Point:**
> "We can generate professional PDF exports for customers or internal review. Notice there's no pricing shown - perfect for sharing with end customers when the dealer wants to add their own markup."

---

## Part 6: Wrap-Up and Summary (2 minutes)

### Key Points to Highlight

1. **Company-wide collaboration** with private project option
2. **Real-time configuration validation** with instant pricing
3. **End-to-end workflow**: Configure → Quote → Schedule → Order → Manufacture
4. **Role-based pricing visibility** protects sensitive data
5. **Automated artifact generation** eliminates manual data entry

### Future Enhancements (if time permits)

- Joiner system for longer fixtures
- Customer tier pricing
- Real-time collaboration features
- CAD integration

---

## Demo Environment Cleanup

After demo, optionally clean up:

```python
# Delete demo project and related records
frappe.delete_doc("ilL-Project", "Demo Retail Store Lighting", force=True)
```

---

*Demo script version 1.0 - January 2026*
