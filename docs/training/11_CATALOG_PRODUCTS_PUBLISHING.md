# Module 11: Catalog, products & publishing

**Audience:** catalog publisher, engineering, marketing & web. **Length:** 2 sessions of 75 minutes (catalog; publishing).
**Roles used:** ilL Catalog Publisher, ilL Engineering, ilL Product Finder Manager, System Manager.

## Purpose

Trainees can add a new product with the Catalog Builder, maintain templates, generate spec sheets, publish to the Webflow websites (both brands), and keep the Product Finder accurate.

> **Status:** Catalog Builder code is built; staging and production acceptance are still pending (Rolling out) (run the smoke test in `docs/CATALOG_BUILDER_ROLLOUT.md` first). Webflow auto-push is off unless the site config enables it. Gallery sync is waiting on a staging run.

## Where to go

| What | Where |
|---|---|
| Catalog Builder (full screen) | `/catalog-builder` |
| Catalog Builder (in the Command Center) | `/command-center#catalog` (Restricted) |
| Workspace: Product Catalog, New Product Setup Guide, Publishing & Website | `/app/illumenate-lighting` |
| Catalog import receipts | `/app/ill-catalog-import` |
| Webflow products | `/app/ill-webflow-product` |
| Publish jobs | `/app/ill-publish-job` |
| Webflow approvals | `/app/ill-webflow-approval` |
| Brands | `/app/ill-webflow-brand` |
| Product Finder questions | `/app/ill-finder-question` |
| New Product Wizard | `/app/new-product-wizard` |
| Product Readiness (CMS preflight, incomplete products) | `/app/product-readiness` |
| Design Readiness (records missing fields, weighted by schedule use) | `/app/design-readiness` |

---

### Lesson 11.1: The product model in one picture

- **Templates** (six ilL-*-Template doctypes: linear fixture, tape / neon, LED sheet, extrusion kit, controller, accessory) hold the product family's rules.
- **Specs, attributes and maps** feed the configurators, spec sheets and submittals.
- **Items**: catalog items come from the Catalog Builder; configured items are created by the configurators automatically.
- **Webflow Product**: the website listing, per brand.
- Template status: Draft, Active, Active + Live, Internal Only, Discontinued, Archived.
- The **New Product Setup Guide** cards on the workspace list the steps for each family in order.

**SS-11-01** · Workspace Product Catalog and New Product Setup Guide cards
**URL:** `/app/illumenate-lighting`
**SS-11-02** · A linear fixture template form with its buttons
**Highlight:** Duplicate as new product; Generate Spec; Readiness and Publication

---

### Lesson 11.2: Adding a product with the Catalog Builder (Rolling out)

1. Open `/catalog-builder` (or the Catalog tab). Pick a family: linear fixture, tape, neon, LED sheet, extrusion kit, driver, controller.
2. Build the draft in the grid. "Copy as new record" starts from an existing one (drops prices, supplier rows and Webflow state). Use "Refresh ERPNext records" after desk changes.
3. **Check in ERPNext**: a full dry run that rolls back.
4. **Import to ERPNext**: same draft, same user, Check less than 30 minutes old. All or nothing. Never updates existing records. Max 500 parent records.
5. Inspect the created records and the receipt (`ilL-Catalog-Import`: Passed, Failed, Imported, Rolled Back, Refused, Error). Test the product in the configurator.
6. Upload attachments by hand. Publish separately (Lesson 11.4).

- Drafts live in your browser. Use **Save YAML / Open YAML** to move them.
- Publishers can't undo an import; an admin deletes.
- If a response is lost, check "Recent checks and imports" before retrying.
- In the Command Center, an amber dot on the Catalog tab means unsaved changes.
- Offline: the same builder as a standalone app (`tools/yaml_builder_ui`), and a CLI that writes import CSVs (`tools/fixture_builder`).

**Readiness pages (desk):**
- **New Product Wizard** (`/app/new-product-wizard`): choose a product family and a starting point; flags issues before you build. The capture bot should confirm in the UI how it hands off to the Catalog Builder.
- **Product Readiness** (`/app/product-readiness`): products that fail the website channel preflight, with "Only incomplete" filter and links to fix each one.
- **Design Readiness** (`/app/design-readiness`): records with fields still to fill, by product type, with volume from recent schedule lines so the most-used products get fixed first.

**SS-11-03a** · New Product Wizard, family chosen
**URL:** `/app/new-product-wizard` · **Role:** ilL Catalog Publisher
**SS-11-03b** · Product Readiness with "Only incomplete" on
**URL:** `/app/product-readiness`
**SS-11-03c** · Design Readiness showing fields to fill and volume
**URL:** `/app/design-readiness`

**SS-11-03** · Catalog Builder grid with a draft linear fixture
**URL:** `/catalog-builder` · **Role:** ilL Catalog Publisher
**SS-11-04** · Check in ERPNext result (passed)
**SS-11-05** · Import result and the receipt record
**SS-11-06** · Catalog tab inside the Command Center with the amber dirty dot
**SS-11-07** · Save YAML / Open YAML menu

---

### Lesson 11.3: Spec sheets and pricing

- **Generate Spec** on a template: n8n renders the PDF, attaches it, and the stable link `/spec-sheets/<brand>_<template>.pdf` points to it. Generating doesn't publish to the website; "Generate Spec & Sync to Webflow" does both.
- **Export Spec Sheet CSV**, **Apply Calculations**, **Populate Part Number Builder** on the template.
- Photometry and colorimetry specs are copied onto the template for spec sheets and submittals.
- **Prices:** MSRP is the Standard Selling Item Price (Catalog Publisher can edit Item Price). Tiers are customer-group pricing rules (Module 03).

**SS-11-08** · Generate Spec in progress and the attached PDF
**SS-11-09** · Stable spec sheet URL opened in a browser

---

### Lesson 11.4: Publishing to Webflow

**Objective:** publish, update and retire products on both brand sites safely.

- **Brands:** ilLumenate and 206 Lighting. Each product chooses its target brands.
- **Standard path:**
  1. Product → **Readiness and Publication** (engineering preflight on templates, channel preflight on products).
  2. **Approve and Stage**: creates a publish job.
  3. **Publish Live**: a separate job.
- **One-click:** **Sync to Webflow** on the product, or **Generate Spec & Sync to Webflow** on the template. Published and Discontinued products publish; Webflow Draft products are staged only.
- **Auto push** (when enabled): saving an already-synced product queues a push 2 minutes after the last save.
- **Retiring:** deactivate first; retiring unpublishes and archives, never deletes.
- **Approvals:** restoring an archived product, or archiving one that was ever published, needs an approval on the Webflow Product. While pending, nothing for that product goes to Webflow.
- **Failures** notify the configured users; Portal Operations → Publication failures. Jobs retry with backoff up to 8 times.

**SS-11-10** · Readiness and Publication panel with preflight results
**SS-11-11** · Approve and Stage, then Publish Live (pair)
**SS-11-12** · Publish job list with statuses
**SS-11-13** · Pending Webflow approval on a product
**SS-11-14** · Webflow Product: target brands and sync status per brand

**DATA-11-01** · Webflow products by sync status
**API:** `GET /api/resource/ilL-Webflow-Product?fields=["sync_status","count(name) as n"]&group_by=sync_status`

---

### Lesson 11.5: Product Finder

- Role: **ilL Product Finder Manager**.
- Finder questions (`/app/ill-finder-question`, Preview matches), Product Finder Coverage report, catalog configurability preview / apply.
- **Verification queue:** "Verify with our team" results, due in 2 business days (Portal Operations → Product verification). The gate setting decides whether verification is needed before the quote, before the order, or warning only.
- The public finder is enabled per brand.

**SS-11-15** · Finder question with Preview matches
**SS-11-16** · Product Finder Coverage report

---

## Slide deck beats

1. Templates, items and website listings
2. The New Product Setup Guide
3. Catalog Builder: draft → Check → Import
4. Spec sheets and stable links
5. Publishing: preflight, stage, live
6. Approvals and retiring
7. Product Finder and verification

## Check yourself

1. Your import failed halfway. What state is ERPNext in?
2. Does Generate Spec update the website?
3. How do you take a product off the website without deleting it?
4. Why isn't your edit showing on Webflow? (Name two possible reasons.)
