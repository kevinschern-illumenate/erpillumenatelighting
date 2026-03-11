# Spec Sheet Download Button — Implementation Plan

## Overview

This feature adds a **"Download Spec Sheet"** button to the Webflow product pages. When a visitor configures a fixture using the part number builder, they can click this button to instantly download a pre-filled PDF spec sheet reflecting their exact configuration—same format as the spec submittals generated from fixture schedules.

---

## How It Works (Non-Technical)

```
Visitor configures fixture on Webflow product page
    → Clicks "Download Spec Sheet"
    → ERPNext generates a filled PDF with their selections
    → Browser downloads the PDF automatically
```

The PDF is the **same fillable spec submittal template** used internally on fixture schedules, filled with the visitor's specific selections (series, CCT, output, lens, finish, mounting, length, etc.).

---

## What Was Built (Dev Side — Done)

| File | What It Does |
|------|-------------|
| `api/spec_sheet_generator.py` | New module — takes configurator selections, creates a configured fixture in ERPNext, generates the filled spec submittal PDF, and returns a download link |
| `api/webflow_configurator.py` | New endpoint (`download_spec_sheet`) — guest-accessible API that Webflow calls |
| `public/js/webflow_spec_sheet_download.js` | JavaScript snippet for the Webflow product page |

---

## What Marketing Needs To Do (Webflow Side)

### Step 1: Add the Download Button

In the Webflow Designer, on each configurable product page template:

1. **Add a Button element** inside or near the configurator section
2. Set the button **ID** to: `ill-download-spec-sheet`
3. Set the button **text** to: `Download Spec Sheet`
4. Style it to match the product page design (e.g., secondary button style)

**Placement suggestion:** Below the part number preview, near the "Add to Project" or pricing area.

### Step 2: (Optional) Add Project Name / Location Fields

If you want visitors to personalize their spec sheet with a project name:

1. Add a **Text Input** element, set its ID to: `ill-project-name`
   - Placeholder: "Project Name (optional)"
2. Add another **Text Input**, set its ID to: `ill-project-location`
   - Placeholder: "Project Location (optional)"

These are optional — if they're not on the page, the spec sheet will just omit project info.

### Step 3: Add the JavaScript Snippet

1. Go to **Page Settings** for the product page (or the product template page)
2. Scroll to **Custom Code → Before `</body>` tag**
3. Paste this:

```html
<script src="https://illumenatelighting.v.frappe.cloud/assets/illumenate_lighting/js/webflow_spec_sheet_download.js"></script>
```

> **Note:** If the configurator JavaScript is already loaded on the page, this is the only script tag you need to add. The spec sheet script reads selections from the same configurator object.

### Step 4: Publish and Test

1. **Publish** the Webflow site
2. Open a product page, complete the configurator (select Environment, CCT, Output, Lens, Mounting, Finish, Length, and Feed Directions)
3. Click **Download Spec Sheet**
4. A PDF should download within a few seconds

---

## Testing Checklist

| Test | Expected Result |
|------|----------------|
| Click Download before completing configurator | Alert: "Please complete your fixture configuration..." |
| Complete all selections, click Download | PDF downloads with correct part number in filename |
| Open the downloaded PDF | All configured values (CCT, finish, mounting, etc.) are filled in correctly |
| Add project name + location, then download | Project info appears on the spec sheet |
| Click Download on a series without a submittal template | Falls back to static spec sheet PDF, or shows error if none exists |
| Mobile test | Button works, PDF downloads to device |

---

## Requirements for This to Work

1. **Spec submittal PDF templates** must be uploaded to ERPNext for each fixture template series (field: `spec_submittal_template` on the `ilL-Fixture-Template` doctype). These are the same fillable PDFs used for fixture schedule submittals.

2. **Field mappings** must be configured in `ilL-Spec-Submittal-Mapping` for each fixture template. These map PDF form fields to configured fixture data. This should already be done for any series that works with fixture schedule spec submittals.

3. **CORS** must allow requests from the Webflow domain to the ERPNext site. This should already be configured for the existing configurator.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  WEBFLOW PRODUCT PAGE                                       │
│                                                             │
│  ┌─────────────────────────┐  ┌───────────────────────────┐ │
│  │  Part Number Builder    │  │  Download Spec Sheet [btn] │ │
│  │  (existing configurator)│  │  Project Name: [________] │ │
│  │                         │  │  Location:     [________] │ │
│  │  ILL-RA01-FS-DR-27-...  │  └───────────┬───────────────┘ │
│  └─────────────────────────┘              │                 │
└───────────────────────────────────────────┼─────────────────┘
                                            │ POST (selections)
                                            ▼
┌─────────────────────────────────────────────────────────────┐
│  ERPNEXT                                                    │
│                                                             │
│  webflow_configurator.download_spec_sheet()                 │
│      │                                                      │
│      ▼                                                      │
│  spec_sheet_generator.generate_from_webflow_selections()    │
│      │                                                      │
│      ├─► Map selections → engine codes                      │
│      │   (resolve defaults for endcap, power feed, etc.)    │
│      │                                                      │
│      ├─► configurator_engine.validate_and_quote()           │
│      │   (creates ilL-Configured-Fixture with all computed  │
│      │    values: segments, runs, drivers, pricing)         │
│      │                                                      │
│      ├─► spec_submittal.generate_filled_submittal()         │
│      │   (fills the PDF template using field mappings)      │
│      │                                                      │
│      └─► Returns public file URL                            │
│                                    │                        │
└────────────────────────────────────┼────────────────────────┘
                                     │
                                     ▼
                              PDF downloads to
                              visitor's browser
```

---

## Timeline Estimate

| Task | Owner | Estimate |
|------|-------|----------|
| Backend code (spec_sheet_generator + endpoint) | Dev | ✅ Done |
| Webflow JS snippet | Dev | ✅ Done |
| Verify spec submittal templates are uploaded for all series | Dev / Product | 1–2 hours |
| Verify field mappings exist for all series | Dev / Product | 1–2 hours |
| Add button + inputs in Webflow Designer | Marketing | 30 min |
| Add script tag in Webflow page settings | Marketing | 5 min |
| End-to-end testing | Dev + Marketing | 1–2 hours |
| **Total remaining** | | **~4–5 hours** |

---

## FAQ

**Q: Does the visitor need to be logged in?**
No. The endpoint is guest-accessible. Anyone on the Webflow site can download a spec sheet.

**Q: What if a series doesn't have a fillable PDF template?**
The system falls back to the static spec sheet PDF attached to the fixture template. If neither exists, it shows an error message.

**Q: Will this create lots of configured fixtures in ERPNext?**
Yes — each spec sheet download creates a lightweight configured fixture record. These can be cleaned up periodically with a scheduled task if needed, or left as useful analytics data (which configurations are visitors interested in?).

**Q: Can we track how many spec sheets are downloaded?**
Yes. Each download creates a configured fixture record in ERPNext and a File record. You can report on these to see download volume and which configurations are most popular.

**Q: Does this work on mobile?**
Yes. The JavaScript works on all modern browsers. On mobile, the PDF will either open in the browser's PDF viewer or download to the device.
