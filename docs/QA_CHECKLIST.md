# End-to-End QA Checklist

This checklist provides repeatable test scenarios for validating the ilLumenate Lighting MVP.
Run through this checklist from a clean site to verify consistent, correct behavior.

## Version Information

- **Engine Version**: 1.0.0
- **Document Updated**: January 2026

---

## Prerequisites

Before running the checklist:

1. ✅ Fresh site with `illumenate_lighting` app installed
2. ✅ `bench migrate` completed successfully
3. ✅ Fixtures loaded (verify SH01 template exists)
4. ✅ Test users created:
   - `admin@example.com` (System Manager)
   - `dealer1@example.com` (Customer: "Dealer One", Can View Pricing role)
   - `dealer2@example.com` (Customer: "Dealer Two", no pricing role)
   - `collaborator@example.com` (Customer: "Dealer One")

---

## Section 1: Install and Migration

### Test 1.1: Fresh Install

**Steps:**
1. Create new bench site
2. Install `illumenate_lighting` app
3. Run `bench migrate`

**Expected:**
- [ ] No errors during install
- [ ] No errors during migrate
- [ ] All DocTypes created successfully

**Verify:**
```
bench --site [site] list-apps
# Should show illumenate_lighting

bench --site [site] console
>>> frappe.db.exists("DocType", "ilL-Fixture-Template")
True
>>> frappe.db.exists("DocType", "ilL-Configured-Fixture")
True
```

### Test 1.2: Fixtures Loaded

**Steps:**
1. Check fixture template exists
2. Check mapping tables have data

**Expected:**
- [ ] SH01 template exists and is active
- [ ] Endcap maps exist for SH01
- [ ] Mounting maps exist for SH01

**Verify:**
```python
>>> frappe.db.exists("ilL-Fixture-Template", "SH01")
True
>>> len(frappe.get_all("ilL-Rel-Endcap-Map", filters={"fixture_template": "SH01"}))
# Should be > 0
```

---

## Section 2: Company Visibility and Project Privacy

### Test 2.1: Company-Visible Project Collaboration

**Steps:**
1. Log in as `dealer1@example.com`
2. Create project "Test Project" (is_private = False)
3. Log out
4. Log in as `collaborator@example.com` (same company as dealer1)
5. Navigate to project list

**Expected:**
- [ ] Project "Test Project" is visible to collaborator
- [ ] Collaborator can open and view project details

### Test 2.2: Private Project Access

**Steps:**
1. Log in as `dealer1@example.com`
2. Edit "Test Project", set is_private = True
3. Log out
4. Log in as `collaborator@example.com`
5. Navigate to project list

**Expected:**
- [ ] Project "Test Project" is NOT visible
- [ ] No error message, project simply doesn't appear

### Test 2.3: Add Collaborator to Private Project

**Steps:**
1. Log in as `dealer1@example.com`
2. Add `collaborator@example.com` to project collaborators
3. Log out
4. Log in as `collaborator@example.com`

**Expected:**
- [ ] Project "Test Project" is now visible
- [ ] Collaborator can access project details

### Test 2.4: Cross-Company Isolation

**Steps:**
1. Log in as `dealer2@example.com` (different company)
2. Navigate to project list

**Expected:**
- [ ] "Test Project" is NOT visible
- [ ] Only projects from Dealer Two's company appear

---

## Section 3: Fixture Configuration

### Test 3.1: Valid SH01 Configuration

**Steps:**
1. Call `validate_and_quote` API with valid SH01 configuration:
   - Template: SH01
   - Finish: Silver
   - Lens: White
   - Mounting: Metal Clip
   - Endcap Style (start/end): Hole
   - Endcap Color: GRY
   - Power Feed: Wire
   - Environment: Dry
   - Tape Offering: (valid offering)
   - Length: 1000mm
   - Qty: 1

**Expected:**
- [ ] `is_valid` = True
- [ ] `computed` section populated with length math
- [ ] `resolved_items` section has all items
- [ ] `pricing` section has msrp_unit > 0
- [ ] `configured_fixture_id` is not None

### Test 3.2: Configuration Validation Errors

**Steps:**
1. Call `validate_and_quote` with non-existent template

**Expected:**
- [ ] `is_valid` = False
- [ ] Error message mentions "not found"
- [ ] No server traceback

### Test 3.3: Length Too Short

**Steps:**
1. Call `validate_and_quote` with length = 30mm

**Expected:**
- [ ] `is_valid` = False
- [ ] Error message explains minimum length requirement
- [ ] Message includes minimum manufacturable length

### Test 3.4: Missing Mapping Returns Error

**Steps:**
1. Call `validate_and_quote` with valid options except unmapped endcap color

**Expected:**
- [ ] `is_valid` = False
- [ ] Error message mentions "Missing map"
- [ ] Message identifies which map is missing

---

## Section 4: Schedule and Sales Order Flow

### Test 4.1: Create Schedule

**Steps:**
1. Log in as dealer user
2. Create new Fixture Schedule linked to project
3. Add lines with configured fixtures

**Expected:**
- [ ] Schedule created successfully
- [ ] Lines saved with configured fixture references

### Test 4.2: Create Sales Order

**Steps:**
1. Ensure schedule has configured fixtures with configured_item set
2. Click "Create Sales Order" action

**Expected:**
- [ ] Sales Order created
- [ ] SO lines reference configured fixtures
- [ ] Schedule status updated to "ORDERED"

### Test 4.3: Generate Manufacturing Artifacts

**Steps:**
1. Call `generate_manufacturing_artifacts` for a configured fixture

**Expected:**
- [ ] Item created with ILL-{hash} code
- [ ] BOM created and submitted
- [ ] Work Order created in draft

### Test 4.4: Artifact Idempotency

**Steps:**
1. Call `generate_manufacturing_artifacts` again for same fixture

**Expected:**
- [ ] No duplicate Item created
- [ ] No duplicate BOM created
- [ ] No duplicate Work Order created
- [ ] Response indicates "skipped"

---

## Section 5: Exports and Pricing

### Test 5.1: Unpriced Export Works

**Steps:**
1. Log in as `dealer2@example.com` (no pricing permission)
2. Call `generate_schedule_pdf(schedule_id, priced=False)`

**Expected:**
- [ ] PDF generated successfully
- [ ] No pricing columns in PDF
- [ ] Download URL returned

### Test 5.2: Priced Export Blocked

**Steps:**
1. Log in as `dealer2@example.com` (no pricing permission)
2. Call `generate_schedule_pdf(schedule_id, priced=True)`

**Expected:**
- [ ] `success` = False
- [ ] Error message about pricing permission
- [ ] No PDF generated

### Test 5.3: Priced Export for Authorized User

**Steps:**
1. Log in as `dealer1@example.com` (has Can View Pricing role)
2. Call `generate_schedule_pdf(schedule_id, priced=True)`

**Expected:**
- [ ] PDF generated successfully
- [ ] Pricing columns included
- [ ] Schedule total displayed

### Test 5.4: CSV Export

**Steps:**
1. Call `generate_schedule_csv(schedule_id, priced=False)`

**Expected:**
- [ ] CSV generated successfully
- [ ] File downloadable
- [ ] Data matches schedule lines

---

## Section 6: Edge Cases

### Test 6.1: Very Long Fixture (SHIP_PIECES mode)

**Steps:**
1. Configure SH01 with length = 5000mm

**Expected:**
- [ ] Configuration valid
- [ ] `assembly_mode` = "SHIP_PIECES"
- [ ] Warning message about assembled shipping limit

### Test 6.2: Multiple Runs Required

**Steps:**
1. Configure fixture requiring multiple tape runs (>17ft with 5W/ft tape)

**Expected:**
- [ ] `runs_count` > 1
- [ ] Each run has separate entry in runs array
- [ ] Total watts calculated correctly

### Test 6.3: Guardrail Coverage Audit

**Steps:**
1. Call `run_coverage_audit()` API

**Expected:**
- [ ] Returns audit results for all active templates
- [ ] Identifies any missing mappings
- [ ] No server errors

---

## Section 7: Security Validation

### Test 7.1: Cross-Customer Record Access

**Steps:**
1. Log in as `dealer2@example.com`
2. Attempt to access project owned by Dealer One via direct URL

**Expected:**
- [ ] Access denied
- [ ] Permission error returned
- [ ] No data leakage

### Test 7.2: Schedule Inherits Project Privacy

**Steps:**
1. Create private project
2. Create schedule linked to private project
3. Log in as different user without collaborator access

**Expected:**
- [ ] Schedule not visible in list
- [ ] Direct URL access denied

### Test 7.3: Export Job Access

**Steps:**
1. Create export as dealer1
2. Log in as dealer2
3. Attempt to access export history

**Expected:**
- [ ] Only own exports visible
- [ ] Cross-customer exports hidden

---

## Section 8: Performance Sanity

### Test 8.1: Configuration Response Time

**Steps:**
1. Time `validate_and_quote` API call for standard configuration

**Expected:**
- [ ] Response < 2 seconds
- [ ] No N+1 query warnings in logs

### Test 8.2: Schedule with 50 Lines

**Steps:**
1. Create schedule with 50 fixture lines
2. Generate PDF export

**Expected:**
- [ ] Export completes within 30 seconds
- [ ] No timeout errors

---

## Sign-off

| Section | Tester | Date | Pass/Fail | Notes |
|---------|--------|------|-----------|-------|
| 1. Install | | | | |
| 2. Privacy | | | | |
| 3. Configuration | | | | |
| 4. SO Flow | | | | |
| 5. Exports | | | | |
| 6. Edge Cases | | | | |
| 7. Security | | | | |
| 8. Performance | | | | |

---

*Last Updated: January 2026*
