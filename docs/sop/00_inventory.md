# 00 — System Inventory (Phase 0)

| | |
|---|---|
| **Purpose** | Evidence base for all later SOPs: what exists in the custom app, where it is wired in, who can touch it, and what it talks to. |
| **Audience** | Systems Integration & Development, department leads, whoever maintains these SOPs. Not written for end users. |
| **Scope** | Repository `kevinschern-illumenate/erpillumenatelighting` only, plus read-only upstream source of the framework versions production runs. No live-site data. |
| **Date** | 2026-09-30 |
| **Commit inspected** | `413171321bf87d6220f948222ed6d48697d0069f` (`main`, merge of PR #270, 2026-09-29) |
| **Confidence** | **High** for anything labelled OBSERVED (read directly from code/config at this commit). **Medium** for INFERRED items. **None** for anything about the live site's data, configuration or user assignments; those are UNKNOWN and listed in §12. |

Labels used throughout: **OBSERVED** (read in code/config/docs), **INFERRED** (reasoned from observed facts; reasoning given), **UNKNOWN / ASK** (not determinable here; goes to the gaps register). Citations use `[src: path → symbol]`. Paths are relative to the repo root; `app/` below means `illumenate_lighting/illumenate_lighting/` (the module folder).

---

## 0. Access statement

### What I could see

| Source | Access | Notes |
|---|---|---|
| This repository at the commit above | Full, read-only | All Python, JS, HTML/Jinja, DocType JSON, patches, fixtures, n8n exports, tools, tests, docs. |
| Frappe **16.35.0** @ `012667b9c4e7…` | Upstream source, read-only | Exact production commit, as recorded in `docs/DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md` §0.3 and `docs/B2B_MIGRATION_REPAIR_2026_09_28.md`. Fetched from GitHub into a scratch folder; version string confirmed in `frappe/__init__.py`. |
| ERPNext **16.36.1** @ `fb78e58b8c03…` | Upstream source, read-only | Same source of truth for the commit. |
| Frappe CRM **1.85.1** @ `a6dfe8bf39e7…` | Upstream source, read-only | Same. CRM is a separate app on the site; its source is **not** in this repo. |
| Local test suites | Executed in an isolated scratch copy | `tests/portal_unit`: **288 tests OK**. `tools/fixture_builder/tests`: **124 tests OK**. Both use framework/database doubles; they prove local contracts only, not live-site behavior. |

### What I could not see (and what I would need)

| Not accessible | Why it matters | What I would need |
|---|---|---|
| Live site `illumenatelighting.v.frappe.cloud` (also `app.illumenate.lighting` per `app/utils.py → ALLOWED_ORIGINS`) | Real data, which users hold which roles, site-level Custom DocPerm, UI-created Custom Fields, Property Setters, Server/Client Scripts, Notification records, Webhook records, Assignment Rules, Email Accounts, Print settings, workspace customizations, ERPNext CRM Settings, Selling/Accounts/Stock/Manufacturing Settings. | Read-only System Manager login, or exports: `Custom DocPerm`, `Custom Field`, `Property Setter`, `Server Script`, `Client Script`, `Notification`, `Webhook`, `Assignment Rule`, `Workflow`, `Role` + `Has Role` (users → roles), `ERPNext CRM Settings`, `ilL-QBO-Settings` (without secret), `ilL-Webflow-Brand`, site config key list. |
| HRMS 16.20.0 and Print Designer 1.6.7 source | Both are installed on production (recovery plan §4.1). Not fetched; no app code references them. | Only needed if any SOP depends on HR or Print Designer formats. |
| n8n Cloud instance | The checked-in workflows may differ from what is deployed. The **ERPNext → QBO invoice/customer push** workflow is **not in the repo** (`docs/QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md` §0). The Postmark campaign workflow behind `n8n_campaign_webhook_url` is not in the repo. | Exports of every active n8n workflow, their schedules/activation state, and credential names (not values). |
| QuickBooks Online | Needed to confirm system of record for invoicing, payments, GL, tax. | Accounting lead's confirmation plus QBO chart-of-accounts/settings summary. |
| Webflow sites (`illumenate`, `lighting_206` brands) | CMS collections, field types, custom code embeds, form webhooks. | Collection schema export and list of pages carrying ERP embeds. |
| Frappe Cloud dashboard | Bench groups, deploy history, backups, site config, staging site. | Screenshots or a read-only dashboard walk-through. |
| Postmark, Slack, Vercel (`configurator-ui-olive.vercel.app`) | External services referenced by code/config. | Confirmation of whether they are in use and who owns them. |
| Repowise MCP server | Failed to connect in this session (executable not found). Not required; all findings here come from direct reads. | — |

---

## 1. Documents read

All 40 files in `docs/` plus the five READMEs were read. "Full" means read end to end; "Decisions" means headings plus status, decision and conclusion sections (these are long historical implementation plans whose step-by-step content is superseded by code). Status is my classification.

| Document | Read | Status / how to treat it |
|---|---|---|
| `README.md` | Full | Install/CI summary. |
| `docs/B2B_STAFF_OPERATIONS.md` | Full | **Current** staff runbook (Sept 2026). Primary source for staff roles/queues. |
| `docs/B2B_QUOTE_OPERATIONS.md` | Full | **Current** quote → offer → draft SO runbook. |
| `docs/B2B_PUBLICATION_RUNBOOK.md` | Full | **Current** product publication (stage/publish/retire) runbook. |
| `docs/B2B_AUTHORING_FIELD_REGISTER.md` | Full | **Current** product-authoring register and import order. |
| `docs/B2B_CONFIGURATOR_COMPATIBILITY.md` | Full | **Current** configurator surfaces and rollout flags. |
| `docs/B2B_SHEET_BUILD_NOTES.md` | Full | **Current** LED Sheet bundle policy. |
| `docs/B2B_CLOUD_ACCEPTANCE.md` | Full | **Current** release/acceptance pack; lists what is still unverified on Cloud. |
| `docs/B2B_PORTAL_IMPLEMENTATION_STATUS.md` | Full | **Current** status register (Sept 25); release "not certified". |
| `docs/B2B_MIGRATION_REPAIR_2026_09_28.md` | Full | Repair log; source for exact production app commits. |
| `docs/B2B_PORTAL_SCHEMA_REPAIR_2026_09_28.md` | Full | Repair log. |
| `docs/B2B_PORTAL_STOCK_REPAIR_2026_09_28.md` | Full | Repair log; stock scope = company "ilLumenate Lighting", warehouse "ilL-Stores". |
| `docs/B2B_CONFIGURATOR_REQUEST_REPAIR_2026_09_28.md` | Full | Repair log. |
| `docs/FRAPPE_CLOUD_BACKUP_REPAIR_2026_09_28.md` | Full | Repair log; `bypass_unlink.so` paragraph corrected by the recovery plan §3.4. |
| `docs/DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md` | Full | **Current** deployment state, open owner decisions, Phase 3/4 backlog. |
| `docs/DEALER_ROLE.md` | Full | **Outdated in parts** — see §11 conflicts. |
| `docs/MVP_CONSTRAINTS.md` | Full | **Jan 2026, outdated in parts** — see §11. |
| `docs/DEMO_SCRIPT.md` | Full | **Jan 2026, outdated** (pre-B2B order flow). |
| `docs/QA_CHECKLIST.md` | Full | Jan 2026 base + later §9 (QBO) and §10 (Desk configurator). Mixed currency. |
| `docs/ERPNEXT_SETUP_GUIDE.md` | Full | Test-data setup for Webflow integration; field names partly verified by later repairs. |
| `docs/QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md` | Full | ERPNext side implemented 2026-09-17; n8n/Intuit rollout steps unchecked. |
| `docs/WEBFLOW_LEAD_INTEGRATION_GUIDE.md` | Full | Lead capture guide; CRM conversion steps describe stock CRM behavior. |
| `docs/WEBFLOW_PORTAL_INTEGRATION_GUIDE.md` | Full | Webflow ↔ portal auth/pricing guide. |
| `docs/MULTI_BRAND_WEBFLOW.md` | Full | Multi-brand model. |
| `docs/SPEC_SHEET_DOWNLOAD_PLAN.md` | Full | Public spec-sheet download (built). |
| `docs/job_title_master.md` | Full | Job Title Master usage. |
| `docs/B2B_PORTAL_PRODUCT_AUDIT_AND_ROADMAP.md` | Full | Product audit (Sept 25); findings F01–F32, many since addressed. |
| `docs/WEBFLOW_INTEGRATION_GUIDE.md` | Decisions + CORS/sync/endpoint sections | Designer guide; sync schedule table conflicts with current publication workflow (§11). |
| `docs/WEBFLOW_ATTRIBUTE_SYNC_GUIDE.md` | Decisions + architecture | Attribute sync guide (6-hour n8n schedule). |
| `docs/WEBFLOW_PRODUCT_ATTRIBUTE_SYNC_GUIDE.md` | Decisions + run order | Filter-field sync guide. |
| `docs/WEBFLOW_SPEC_SHEET_EMBED_SCRIPT.txt` | Scanned for API calls | Embed script copy for Webflow. |
| `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md` | Decisions (§14 owner answers) + findings headings | Historical (Sept 17). §14 records **owner decisions** that remain relevant. |
| `docs/B2B_PORTAL_TECHNICAL_IMPLEMENTATION_PLAN.md` | Decisions + headings | Historical plan, largely implemented. |
| `docs/CONFIGURATOR_GROUPING_ALIGNMENT_PLAN.md` | Decisions (§1) + headings | Historical; grouping decisions carried into code. |
| `docs/QUOTE_ORDER_CONFIGURATOR_PLAN.md` | Decisions (§7) + headings | Historical; Desk configurator implemented. |
| `docs/CONFIGURATOR_UI_IMPROVEMENTS_PLAN.md` | Headings | React tool UI plan; no process content. |
| `docs/GENERATED_SPEC_SHEETS_PLAN.md` | Headings + status | In progress (Phase 0 done locally, Cloud probe pending). |
| `app/api/README.md` | Full | Rules Engine v1 API; describes early placeholder behavior, partly superseded. |
| `app/api/IMPLEMENTATION_NOTES.md` | Full | Phase 2/3 notes; manufacturing generator epics. |
| `app/api/WEBFLOW_API_DOCUMENTATION.md` | Headings + endpoint list | Webflow endpoint reference. |
| `tools/fixture_builder/README.md`, `tools/fixture_builder/CATALOG.md` | Full | Catalog/YAML builder and CSV import order. |

---

## 2. Platform and deployment facts

| Fact | Label | Source |
|---|---|---|
| Production stack: Frappe 16.35.0, ERPNext 16.36.1, HRMS 16.20.0, CRM 1.85.1, Print Designer 1.6.7, Python 3.14, on Frappe Cloud bench group "ilLumenate Production - V16". | OBSERVED (doc) | `docs/DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md` → "Current status", §0.3 |
| Installed-app order on production: `frappe, illumenate_lighting, erpnext, hrms, crm, print_designer` — this app's patches and `after_migrate` run **before** ERPNext's. | OBSERVED (doc) | same, §4.1 |
| `pyproject.toml` still comments `frappe~=15.0.0`; CI now targets version-16 only. | OBSERVED | `pyproject.toml`; `.github/workflows/ci.yml` (`FRAPPE_BRANCH: version-16`) |
| Staging site `stagingillumenatelighting.v.frappe.cloud` is referenced as an allowed CORS origin; whether it exists on its own bench group is unknown. | OBSERVED / UNKNOWN | `app/utils.py → ALLOWED_ORIGINS`; recovery plan §4.1 |
| One custom module: `ilLumenate Lighting`. All 146 app DocTypes belong to it. None are submittable (docstatus-based); lifecycle is carried in `status`/`state` Select fields. | OBSERVED | `illumenate_lighting/modules.txt`; DocType JSON scan |
| Only `illumenate_lighting/fixtures/` (app level) is imported by Frappe on migrate. It contains **only** `number_card.json`. The 20 files in `app/fixtures/` (the module-level folder: Dealer role, Document Request workflow, custom fields, request types, job titles, print formats, seed product data) are **not** loaded. | OBSERVED | `frappe/utils/fixtures.py → import_fixtures` uses `frappe.get_app_path(app, "fixtures")`; confirmed by `docs/B2B_MIGRATION_REPAIR_2026_09_28.md` |

---

## 3. Custom DocTypes (146)

Audience key: **Portal** = end customers/dealers reach it through `/portal` pages or portal APIs (normally via server-side services, not direct Desk access). **Desk** = staff work queue or generated record viewed in Desk. **Config** = master/configuration data maintained by staff. Purposes are OBSERVED where they come from a docstring/description, otherwise INFERRED from the DocType name and fields (marked "I").

### 3.1 Portal and commercial workflow records

| DocType | Purpose | Audience | Status field (values) |
|---|---|---|---|
| ilL-Project | A customer project that groups fixture schedules; owned by a Customer (`owner_customer`), optionally private, with collaborators. | Portal + Desk | `status`: ACTIVE, ON_HOLD, COMPLETED, ARCHIVED |
| ilL-Project-Fixture-Schedule | A versioned list of fixture lines for a project; the unit that is quoted and ordered. | Portal + Desk | `status`: DRAFT, READY, QUOTED, ORDER_REQUESTED, ORDERED, ISSUE, CLOSED |
| ilL-Quote-Request | Unpriced quote intake from a schedule snapshot ("durable quote intake, separate from issuance") [src: `app/portal/quotes.py` docstring]. Naming `QR-#####`. | Portal (via service) + Desk | `state`: DRAFT, REQUESTED, UNDER_REVIEW, INFORMATION_NEEDED, ISSUED, CLOSED |
| ilL-Quote-Offer | Immutable issued offer created when a linked Quotation is submitted; holds snapshot hash and private PDF. Naming `OFFER-#####`. | Portal (projection) + Desk | `state`: ISSUED, ACCEPTED, DECLINED, REVISION_REQUESTED, SUPERSEDED, CANCELLED |
| ilL-Order-Intake | Reviewed PO context wrapped around a draft Sales Order (buyer acknowledgment, approval snapshot, decisions). Naming `OI-#####`. | Portal (via service) + Desk | `state`: SUBMITTED, UNDER_REVIEW, INFORMATION_NEEDED, CHANGES_PROPOSED, APPROVED, REJECTED, WITHDRAWN |
| ilL-Order-Change | Customer request to change, cancel, reorder or replace an order. Naming `OC-#####`. | Portal + Desk | `state`: SUBMITTED, UNDER_REVIEW, INFORMATION_NEEDED, COMPLETED, REJECTED |
| ilL-Document-Request | Drawing/resource/technical request with assignment, SLA, deliverables and portal conversation. Naming `ILL-REQ-.YYYY.-#####`. | Portal + Desk | `status`: Draft, Submitted, In Progress, Waiting on Customer, Completed, Closed, Cancelled; plus custom `ill_review_state` |
| ilL-Drawing-Review | A reviewer's decision on one published drawing revision (file hash + build hash). Naming `DR-#####`. | Desk (written by portal action) | `decision`: APPROVED, CHANGES_REQUESTED |
| ilL-Account-Request | Account/company requests from portal users (dealer application, company linkage, profile change, …). | Portal + Desk | `state`: Pending, Information needed, Approved, Rejected, Resolved |
| ilL-Portal-Invitation | Expiring, token-hashed invitation for a company member or project collaborator. | Portal + Desk | `state`: Pending, Accepted, Revoked |
| ilL-Portal-Message | Conversation message on a Document Request or Issue; `visibility` Customer or Internal. | Portal + Desk | `action`: REPLY, REQUEST_INFO, RESOLVE, REOPEN |
| ilL-Portal-Upload | Verified upload staging/finalization record (SHA-256, size, MIME). | Desk (system) | `state`: STAGING, FINALIZED, FAILED, GENERATED_PUBLIC, GENERATED_PRIVATE |
| ilL-Line-Document | A document attached to a specific schedule line (e.g. other-manufacturer spec sheet). | Portal + Desk | `active` flag |
| ilL-Portal-Event | Durable notification event (one per business event) [src: `app/portal/outbox.py` docstring]. | Desk (system) | — |
| ilL-Portal-Delivery | Per-recipient delivery record for a Portal Event, linked to native Email Queue. | Desk (Integration) | `state`: PENDING, SUPPRESSED, SKIPPED, QUEUED, FAILED, DELIVERED |
| ilL-Portal-User-Settings | Per-user notification preferences and display settings (OBSERVED docstring). | Portal | — |
| ilL-Configuration-Receipt | Idempotent retry receipt for a configurator save (request key/hash → response). | Desk (system) | — |
| ilL-Configurator-Session | Hand-off record from the React configurator tool (quiz answers → recommended template). | Portal (React UI) | `status`: Active, Used, Expired |
| ilL-Export-Job | Schedule export/packet job (priced/unpriced PDF/CSV, spec submittal packets) with manifest and private output. | Portal + Desk | `status`: QUEUED, RUNNING, COMPLETE, FAILED, INCOMPLETE |
| ilL-Webflow-Session | Anonymous Webflow configurator session that can be converted into a portal project/schedule (OBSERVED docstring). | Webflow/Portal | `status`: Active, Expired, Converted, Abandoned |

### 3.2 Configured product records (generated by configurators)

| DocType | Purpose | Audience |
|---|---|---|
| ilL-Configured-Fixture | One configured linear fixture: selections, computed lengths/segments/runs, drivers, pricing snapshot, links to generated Item/BOM. Named by config hash (I, per `api/IMPLEMENTATION_NOTES.md`). 102 fields. | Desk (generated) |
| ilL-Configured-Tape-Neon | "A fully configured LED Tape or LED Neon product" (OBSERVED docstring). | Desk (generated) |
| ilL-Configured-LED-Sheet | Configured LED sheet system: coverage, sheets needed, groups, power. `status`: Draft, Configured, Quoted, Ordered. | Desk (generated) |
| ilL-Configured-Group | Independent fixture group with shared family/spec/power; one parent Item and BOM; named by config hash. | Desk (generated), Dealer read |

### 3.3 Product templates, mappings and literature (Product Development config)

| DocType | Purpose | Audience |
|---|---|---|
| ilL-Fixture-Template | Linear fixture family: allowed tape offerings/options, lengths, pricing base, part-number builder, submittal template. | Config |
| ilL-Tape-Neon-Template | "Template/family for LED Tape and LED Neon products" (OBSERVED docstring). | Config |
| ilL-LED-Sheet-Template | LED sheet family: allowed specs/options, price per sheet, jumper/leader Items, submittal template, certifications. | Config |
| ilL-Driver-Template | Driver product family with variants and options (I). | Config |
| ilL-Controller-Template | Controller product family with variants and options (I). | Config |
| ilL-Extrusion-Kit-Template | Extrusion kit family: profile/lens lengths, endcap/mounting quantities, base MSRP. | Config (Dealer has rwc in JSON — see §7) |
| ilL-Spec-Submittal-Mapping | PDF form-field → source-field mapping for linear fixture submittals. | Config |
| ilL-Neon-Submittal-Mapping | Same for tape/neon. | Config |
| ilL-LED-Sheet-Submittal-Mapping | Same for LED sheets. | Config |
| ilL-Driver-Submittal-Mapping | Same for drivers. | Config |
| ilL-Controller-Submittal-Mapping | Same for controllers. | Config |
| ilL-Item-Literature | Approved static literature (PDF) per ERPNext Item, with SHA-256 and approver, or an explicit "no document required" exclusion. | Config |
| ilL-Product-Publication | Per product × brand publication state with current/approved/staged/live hashes. | Desk (Catalog/Integration) — `state`: NEEDS_REVIEW, READY, QUEUED, STAGED, LIVE, FAILED, RETIRED |
| ilL-Publish-Job | Immutable stage/publish/retire job claimed by the n8n worker, with lease and retry. | Desk (Catalog/Integration) — `state`: QUEUED, RUNNING, COMPLETE, FAILED, SUPERSEDED |

### 3.4 Specifications (`ilL-Spec-*`) — Config

| DocType | Purpose (I unless noted) |
|---|---|
| ilL-Spec-Profile | Aluminium profile (extrusion) spec: dimensions, stock length, environments. |
| ilL-Spec-Lens | Lens spec per profile family/appearance. |
| ilL-Spec-LED Tape | LED tape electrical/optical spec: voltage, W/ft, lm/ft, cut increment, max run (fields per `docs/ERPNEXT_SETUP_GUIDE.md` Part 2). |
| ilL-Spec-LED-Sheet | LED sheet panel spec (dimensions, full-panel watts, input protocol). |
| ilL-Spec-Driver | Driver (power supply) spec: outputs, per-output/total limits, load factor, protocols. |
| ilL-Spec-Controller | Controller spec: channels/zones, protocols. |
| ilL-Spec-Accessory | Accessory spec (mounting, joiner, endcap, leader) with quantity rules (OBSERVED fields `qty_rule_type`, `qty_rule_value`). |

### 3.5 Relationship maps (`ilL-Rel-*`) — Config

| DocType | Purpose |
|---|---|
| ilL-Rel-Tape Offering | A sellable tape variant = tape spec × CCT × CRI × SDCM × LED package × output level, with overrides (OBSERVED fields). |
| ilL-Rel-Profile Lens | Which lenses fit which profiles. |
| ilL-Rel-Endcap-Map | Endcap Item per (template, style, color) (I; coverage rule in `docs/MVP_CONSTRAINTS.md`). |
| ilL-Rel-Finish Endcap Color | Default endcap colour for each finish (OBSERVED fields). |
| ilL-Rel-Mounting-Accessory-Map | Mounting accessory Item and quantity per mounting method. |
| ilL-Rel-Leader-Cable-Map | Leader cable Item per tape spec × power feed type × environment (OBSERVED fields). |
| ilL-Rel-Driver-Eligibility | Which driver specs are allowed for which template (fixture/tape-neon/sheet), with priority (OBSERVED fields). |
| ilL-Rel-Kit-Profile-Map / Kit-Lens-Map / Kit-Mounting-Map / Kit-Endcap-Map | Component Item maps for extrusion kits (4 DocTypes). |

### 3.6 Attributes (`ilL-Attribute-*`, 28 DocTypes) — Config

Lookup lists used as selectable options, part-number codes and Webflow filter values. Typical fields: label/name, code, active flag, sort order. 24 of them receive per-brand Webflow sync state through the custom field `webflow_sync_targets` (§6.2) and fire Webflow sync hooks (§4.7). Mounting Type and Controller Type carry `webflow_sync_targets` in their own schema but have no sync hook. PCB Finish and PCB Mounting have neither.

CCT · CRI · SDCM · Certification (body, badge, applies-to types) · Controller Type · Dimming Protocol · Endcap Color · Endcap Style · Environment Rating · Feed-Direction ("power feed location End/Back", OBSERVED docstring) · Finish (has lifecycle `status`: Active, End of Life, Discontinued, Prototype) · IP Rating · Joiner Angle · Joiner System · Lead Time Class (`days_min`/`days_max`) · Leader Cable (conductors, AWG, jacket, default length) · LED Package · Lens Appearance · Lens Interface Type · Mounting Method · Mounting Type · Output Level · Output Voltage · PCB Finish · PCB Mounting · Power Feed Type · Pricing Class (`default_adder`, `multiplier`) · Series.

### 3.7 Integration, settings and masters

| DocType | Purpose | Audience |
|---|---|---|
| ilL-Webflow-Brand | Brand master (site ID, n8n credential name, configurator payload flag, ERP base URL, collections). | Config (SysMgr) |
| ilL-Webflow-Product | Product content for portal catalog and Webflow CMS (73 fields; controller 3,113 lines). | Config (Catalog) |
| ilL-Webflow-Category | Product category for CMS, with brand targets and sync state. | Config (Catalog) |
| ilL-Webflow-Settings (Single) | Legacy single-site Webflow settings (collection IDs); superseded by Brand per `docs/MULTI_BRAND_WEBFLOW.md`. | Config (SysMgr) |
| ilL-Webflow-Configurator-Cache | Cache of cascading configurator options (OBSERVED docstring). | System |
| ilL-QBO-Settings (Single) | QBO payment reverse-sync: enable flag, webhook secret (Password), paid-to account, mode of payment. | Config (SysMgr, Accounts Manager) |
| ilL-QBO-Sync-Log | One row per inbound QBO payment event with outcome and links. | Desk (Accounts) |
| ilL-Request-Type | Document request types with portal label, SLA hours by priority, default assignee, optional Task creation, per-type custom fields. | Config |
| ilL-Job-Title-Master | Standard job titles linked from CRM Lead `job_title` (OBSERVED docstring). | Config (Marketing) |
| Email Campaign Benchmark Settings (Single) | Open/click/CTR benchmark percentages used by the Email Campaign Activity Summary report. | Config (Marketing) |

### 3.8 Child tables (52) — grouped

| Parent area | Child DocTypes |
|---|---|
| Schedules/projects | ilL-Child-Fixture-Schedule-Line (44 fields: line key, manufacturer, product type, configured links, qty, location, notes, documents), ilL-Child-Project-Collaborator (user, VIEW/EDIT, active), ilL-Child-Schedule-Collaborator (user, Viewer/Editor/Admin), ilL-Child-User-Segment |
| Configured products | ilL-Child-Configured-Segment, ilL-Child-Configured-Run, ilL-Child-Driver-Allocation, ilL-Child-Pricing-Snapshot, ilL-Child-Tape-Neon-Segment, ilL-Child-LED-Sheet-Group, ilL-Child-Group-Member, ilL-Child-Group-Allocation |
| Templates/options | ilL-Child-Template-Allowed-Option, ilL-Child-Template-Allowed-TapeOffering, ilL-Child-Tape-Neon-Allowed-Option, ilL-Child-Tape-Neon-Allowed-Spec, ilL-Child-LED-Sheet-Allowed-Option, ilL-Child-LED-Sheet-Allowed-Spec, ilL-Child-Kit-Allowed-Option, ilL-Child-Driver-Allowed-Option, ilL-Child-Driver-Template-Variant, ilL-Child-Controller-Allowed-Option, ilL-Child-Controller-Template-Variant, ilL-Child-PN-Builder-Row |
| Specs/compatibility | ilL-Child-Compatible Lens, ilL-Child-Compatible-Driver, ilL-Child-Controller-Protocol, ilL-Child-Driver-Input-Protocol, ilL-Child-Tape-Dimming-Protocol, ilL-Child-Wireless-Protocol, ilL-Child-Lens Environments, ilL-Child-Profile Environment, ilL-Child-LED Package CCT, ilL-Child-Spec-Certification, ilL-Child-Certification-Applies-To |
| Webflow | ilL-Child-Webflow-Attribute-Link, ilL-Child-Webflow-Brand-Target, ilL-Child-Webflow-Certification-Link, ilL-Child-Webflow-Compatibility, ilL-Child-Webflow-Configurator-Option, ilL-Child-Webflow-Document, ilL-Child-Webflow-Feed-Length, ilL-Child-Webflow-Gallery-Image, ilL-Child-Webflow-Kit-Component, ilL-Child-Webflow-Specification, ilL-Child-Webflow-Specification-Option, ilL-Child-Webflow-Sync-State, ilL-Webflow-Brand-Collection |
| Requests/orders | ilL-Request-Deliverable (file, version, published flag/by/on, build hash), ilL-Request-Field-Value, ilL-Request-Type-Field, ilL-Order-Decision (action, actor, time, revision hash, note) |

---

## 4. `hooks.py` inventory

All OBSERVED from `illumenate_lighting/hooks.py` at the inspected commit (line numbers in brackets).

### 4.1 Assets and UI injection

| Hook | Value | Effect |
|---|---|---|
| `app_include_css` / `app_include_js` [31, 34] | `illumenate_desk.bundle.css/js` | Desk bundle: shared configurator + "Configure & Add Fixture" dialog for Quotation / Sales Order. |
| `web_include_css` / `web_include_js` [37, 42] | Font Awesome 4.7 (CDN) + `illumenate_web.bundle.css/js` | Portal/website bundle. |
| `doctype_js` [55–61] | ilL-Portal-Delivery → `portal_delivery.js`; Issue, ilL-Document-Request → `desk_conversation.js`; ilL-Quote-Request → `quote_request.js`; Sales Order → `sales_order.js`; Quotation → `quotation.js`; ilL-Webflow-Product, ilL-Publish-Job → `product_publication.js`; the five templates (Fixture, Tape-Neon, LED-Sheet, Driver, Controller) → `authoring_readiness.js` | Adds custom buttons/panels to those Desk forms. |
| `doctype_list_js` [57] | Item → `item_list.js` | Item list customization. |
| `brand_html` [77] | Nav logo image | Website navbar branding. |
| `role_home_page` [80] | Dealer, Website User, Customer → `portal` | These roles land on `/portal` after login. |

### 4.2 Website routes and redirects

`website_route_rules` [88–146]:

| Route | Page controller (`illumenate_lighting/templates/pages/`) |
|---|---|
| `/portal`, `/portal/` | `portal` |
| `/portal/projects`, `/portal/projects/<project>`, `/portal/projects/<project>/collaborators`, `/portal/projects/<project>/schedules/new` | `ill_projects`, `project`, `collaborators`, `schedule` |
| `/portal/schedules/<schedule>` | `schedule` |
| `/portal/configure`, `/portal/configure/<template>` | `configure` |
| `/portal/request-dealer-access` | `request_dealer_access` |
| `/portal/configure-tape`, `/portal/configure-neon` | `configure_tape` (server redirect to `/portal/configure`, per `docs/B2B_CONFIGURATOR_COMPATIBILITY.md`) |
| `/portal/configure-sheet`, `/configure-sheet` | `configure_sheet` (controller only, no template) |
| `/portal/configure-kit`, `/portal/configure-kit/<template>` [110–111] | `configure_kit` — **page does not exist in the repo** (dead route; recovery plan §7.8, still present) |
| `/portal/edit_fixture` | `edit_fixture` |
| `/portal/products`, `/portal/products/<slug>` | `products_catalog`, `product_detail` (hooks comment says "System Manager only"; controller calls `portal.access.require_catalog_access` and its docstring says "Dealers and internal users" — see §11) |
| `/portal/quotes`, `/portal/quotes/<offer>`, `/portal/quote-requests/<request>` | `quotes`, `quote_detail`, `quote_request_detail` |
| `/portal/orders`, `/portal/orders/<order>` | `orders`, `order_detail` |
| `/portal/drawings`, `/portal/drawings/<request>` | `drawings`, `drawing_detail` |
| `/portal/resources` | `resources` (public spec sheets from active Webflow products; no login check in controller) |
| `/portal/support`, `/portal/support/faq`, `/portal/support/<ticket_name>` | `ill_support`, `support_detail` |
| `/portal/account`, `/portal/account/notifications`, `/portal/accept-invitation` | `account`, `accept_invitation` |

Page controllers that exist without a route rule (reachable at `/<name>` by Frappe convention — INFERRED): `configure_multisegment`, `configure_old` (legacy), `configuration_routes` (helper module).

`website_redirects` [150–153]: `/portal/configure-webflow[/<x>]` → `/portal/configure?…&mode=wizard` (retired page).

### 4.3 Install / migrate

| Hook | Handler | What it does |
|---|---|---|
| `after_install` [174] | `app/install.py → after_install` | Creates Dealer role (desk_access 0), applies Dealer permission matrix, then runs the B2B patches: `b2b_portal_foundations`, `b2b_conversations`, `b2b_configurator_receipts`, `b2b_fixture_groups`, `b2b_accounts`, `b2b_order_service`, `b2b_commercial_lineage`, `add_company_invoice_payment_instructions`. |
| `before_migrate` [175] | `illumenate_lighting/portal_workspace.py → before_migrate` | Snapshots the workspace to `private/ill-workspace`; relocates legacy `private/backups/ill-workspace`. |
| `after_migrate` [176] | `portal_workspace.after_migrate` | Merges shipped workspace shortcuts into the site's workspace, preserving site blocks. |

### 4.4 Fixtures [181–206]

| Entry | Loaded on migrate? | Why |
|---|---|---|
| Role `Dealer` | **No** | File is in the unloaded module-level folder; Dealer role is created by `install.py` instead. |
| Workflow `ILL Document Request Workflow` | **No** | Unloaded folder, **and** the fixture file's record is named `ilL Document Request Workflow` (different case), so the hook filter would not match on export either. |
| `ILL Request Type` | **No** | No DocType has this name (actual: `ilL-Request-Type`). |
| ilL-Attribute-Certification, ilL-Webflow-Category, ilL-Attribute-Feed-Direction, ilL-Spec-Driver (2 Snowfield drivers), ilL-Rel-Driver-Eligibility (sheet), ilL-Spec-LED-Sheet, ilL-LED-Sheet-Template, Item (4 Snowfield Items), ilL-Job-Title-Master (active), Workspace (module) | **No** (except where the site already has them) | Seed files live in the unloaded folder. |
| `Custom Field` (unfiltered) | **No** on import (unloaded folder) | **Risk on export:** `bench export-fixtures` would write every app's custom fields into the loaded `fixtures/` folder (recovery plan §7.7, still unfiltered). |
| `Number Card` (module = ilLumenate Lighting) | **Yes** | `illumenate_lighting/fixtures/number_card.json` — six cards (§6.6). |

Consequence (INFERRED): whether the Document Request workflow, the 13 initial job titles, request types, the Dealer role's fixture form, the two legacy print formats and the Snowfield seed products exist on production depends on how the site was set up historically. **UNKNOWN / ASK (G-004).**

### 4.5 Permission hooks

`permission_query_conditions` [241–255] (list filtering) and `has_permission` [257–273] (per-document check):

| DocType | List filter | Document check |
|---|---|---|
| ilL-Order-Change | `portal/order_changes.get_permission_query_conditions` | `portal/order_changes.has_permission` |
| ilL-Account-Request | `portal/accounts.query_conditions` | `portal/accounts.has_permission` |
| ilL-Line-Document | `portal/line_documents.query_conditions` | `portal/line_documents.has_permission` |
| ilL-Configured-Group | `doctype/ill_configured_group.get_permission_query_conditions` | `…has_permission` |
| ilL-Portal-Message | `portal/conversations.get_permission_query_conditions` | `portal/conversations.has_permission` |
| ilL-Quote-Offer | `portal/offers.get_permission_query_conditions` | `portal/offers.has_permission` |
| ilL-Quote-Request | `portal/quotes.get_permission_query_conditions` | `portal/quotes.has_permission` |
| ilL-Export-Job | `doctype/ill_export_job.get_permission_query_conditions` | `…has_permission` |
| ilL-Project | `doctype/ill_project.get_permission_query_conditions` | `…has_permission` |
| ilL-Project-Fixture-Schedule | `doctype/ill_project_fixture_schedule.get_permission_query_conditions` | `…has_permission` |
| ilL-Document-Request | `doctype/ill_document_request.get_permission_query_conditions` | `…has_permission` |
| ilL-Portal-User-Settings | `doctype/ill_portal_user_settings.get_permission_query_conditions` | `…has_permission` |
| Sales Order | `app/dealer_permissions.sales_order_query_conditions` | `app/dealer_permissions.sales_order_has_permission` |
| File | — | `portal/private_file.portal_file_permission` |
| ilL-Portal-Upload | — | `portal/files.has_permission` |

`has_website_permission` [276]: ilL-Project → `doctype/ill_project.has_website_permission`.

v16 note (OBSERVED in Frappe source): a `has_permission` hook returning a falsy value **denies**; this is why the File hook was rewritten in PR #259 (`db06599`) [src: `frappe/permissions.py → has_controller_permissions`; recovery plan §6.1].

### 4.6 Class overrides [284–287]

| DocType | Override class | Purpose (docstring) |
|---|---|---|
| File | `portal/private_file.PortalFile` | "Narrow native-download guard for portal-owned artifacts and request files." |
| Email Queue | `portal/email_queue.PortalEmailQueue` | "Limit portal emails at native send time; unrelated email keeps native behavior." Re-checks recipient preference and current access immediately before send. |

### 4.7 Document events [293–438]

| DocType | Event | Handler | What it does (OBSERVED from handler docstrings/names; detail in Phase 1) |
|---|---|---|---|
| Issue | validate | `portal/support.validate_owner` | Portal ownership checks on support tickets. |
| ilL-Project-Fixture-Schedule | on_update | `portal/drawing_impact.on_build_update` | Creates drawing reapproval Task when the physical build changes. |
| Work Order | before_submit | `portal/drawing_review.before_work_order_submit` | **Manufacturing gate**: blocks submit without a current approved drawing when a request requires it. |
| Quotation | before_submit, on_submit | `portal/offers.before_submit`, `portal/offers.on_submit` | A submitted Quotation linked to a Quote Request creates the immutable portal offer + private PDF and marks the schedule QUOTED. |
| Quotation | on_cancel | `portal/offers.on_cancel`; `api/desk_configurator.on_quotation_cancel` | Cancels the offer; Desk-configurator bookkeeping. |
| Sales Order | validate, before_update_after_submit | `portal/order_review.validate_order` | Stamps delivery confirmation; applies intake-only review rules. |
| Sales Order | on_update, on_update_after_submit | `portal/drawing_impact.on_build_update` | Drawing impact on physical changes. |
| Sales Order | before_submit | `portal/order_review.before_submit` | **Approval gate** for portal-originated orders (only when an ilL-Order-Intake exists — `_portal_governed`). |
| Sales Order | on_submit | `portal/order_review.on_submit`; `api/manufacturing_generator.on_sales_order_submit`; `doctype/ill_project_fixture_schedule.on_sales_order_submit` | Intake → approved; auto-generate Items/BOMs/Work Orders for configured lines; schedule → ORDERED. |
| Sales Order | on_cancel, on_trash | `doctype/ill_project_fixture_schedule.on_sales_order_cancel` / `on_sales_order_trash` | Revert schedule linkage/status. |
| Delivery Note | validate | `portal/commercial_lineage.validate` | Copies build-lineage fields from the exact source SO row; throws if customer/company/Item differ or source not submitted. Runs on **every** DN/SI row that has a source row (recovery plan §7.6 not applied). |
| Delivery Note | on_submit | `portal/notifications.on_delivery_note_submit` | Shipment notification to portal recipients. |
| Sales Invoice | validate | `portal/commercial_lineage.validate` | Same lineage copy/check as DN. |
| Purchase Order | before_validate | `api/purchase_order.allow_blank_schedule_date` | Allows PO without schedule date (paired with property setters §6.3). |
| 24 × ilL-Attribute-* (CCT, CRI, Certification, Dimming Protocol, Endcap Color, Endcap Style, Environment Rating, Feed-Direction, Finish, IP Rating, Joiner Angle, Joiner System, Lead Time Class, Leader Cable, LED Package, Lens Appearance, Lens Interface Type, Mounting Method, Output Level, Output Voltage, Power Feed Type, Pricing Class, SDCM, Series) | after_insert, on_update | `api/webflow_sync_events.on_attribute_insert` / `on_attribute_update` | Marks the attribute pending for Webflow sync. |
| ilL-Webflow-Product | on_update | `api/webflow_sync_events.on_product_update` | Marks product pending / cache invalidation. |
| ilL-Webflow-Category | on_update | `api/webflow_sync_events.on_category_update` | Same for categories. |
| ilL-Webflow-Brand | on_update, on_trash | `api/webflow_sync_events.on_brand_update` | Per-brand cache invalidation. |

### 4.8 Scheduler, request hooks

| Hook | Value | Purpose |
|---|---|---|
| `scheduler_events.cron["*/5 * * * *"]` [442] | `portal/outbox.dispatch`; `portal/packet_jobs.recover` | Every 5 minutes: create native Email Queue entries for pending portal deliveries and reconcile results; re-enqueue queued packet jobs after broker failure and expose abandoned attempts. |
| `after_request` [475] | `app/utils.after_request` | Adds CORS headers for 10 hard-coded origins in `app/utils.py → ALLOWED_ORIGINS` (Webflow production/staging, illumenate.lighting domains, staging ERP, `app.illumenate.lighting`, `configurator-ui-olive.vercel.app`). |

Not present (OBSERVED absent): `override_whitelisted_methods`, `override_doctype_dashboards`, `jinja`, `website_generators`, `auth_hooks`, `before_request`, `on_session_creation`, `daily`/`hourly` scheduler entries. `email_campaign_scheduler.run_scheduled_campaigns` exists but **has no scheduler entry** (removed in commit `1e99926`, per recovery plan §4.1).

Background jobs (`frappe.enqueue`, OBSERVED): `portal/packet_jobs.request` and `.recover` → `packet_jobs.run` (spec packet generation); `api/spec_sheets/probe.py` (renderer probe).

---

## 5. Whitelisted API endpoints

290 whitelisted callables: 282 module-level functions and 8 DocType methods. **27 allow Guest** (no login). Callers were found by static search of this repo's JS, HTML, n8n JSON, tools and the Webflow embed script copy. A caller marked "(name match)" was matched by function name within a file that references the module, not by full dotted path. **"none found"** means no in-repo caller; the endpoint may be called from the live Webflow site's custom code, an n8n workflow not in the repo, `bench execute`, Python page controllers, or nothing at all. That distinction is **UNKNOWN (G-010)** until n8n and Webflow exports are compared.

### 5.1 Guest (unauthenticated) endpoints

| Endpoint | Purpose (from name/docstring) | Protection other than login |
|---|---|---|
| `api.qbo_sync.receive_payment_event` | QBO payment → Payment Entry | HMAC `X-QBO-Signature` over raw body; secret from site config `qbo_webhook_secret` or ilL-QBO-Settings (OBSERVED `_get_webhook_secret`). |
| `api.webflow_leads.create_lead_from_webflow` (POST) | Create CRM Lead from a web form | **None beyond POST-only**; inserts with `ignore_permissions=True`. n8n sends an API token, but the endpoint does not require one. Dedupe: same `webflow_submission_id`, or same email within 24 h (OBSERVED `webflow_leads.py` ~L117–L144). |
| `api.webflow_leads.create_lead_from_webflow_webhook`, `api.webflow_leads.health_check` | Raw webhook variant; health ping | Same. |
| `api.webflow_auth.get_user_context` | Returns login state, dealer/internal flags and linked Customer to the Webflow widget | Returns identity data only for a logged-in session cookie; deliberately **does not** return API keys (code comment). Reflects credentialed CORS to any `*.webflow.io` or `*.vercel.app` origin (OBSERVED), so any site on those domains can read a logged-in user's customer name — see §11 and G-012. |
| `api.webflow_configurator.*` (9: init, cascading options, validate, part number preview, download spec sheet, sheet configurator data, tape/neon mounting options, create complex fixture session, get session) | Public Webflow configurator and spec-sheet download | Catalog/rollout controls; public output has no customer data per `docs/B2B_AUTHORING_FIELD_REGISTER.md`. `download_spec_sheet` creates a configured-fixture record per call (per `docs/SPEC_SHEET_DOWNLOAD_PLAN.md` FAQ). |
| `api.webflow_integration.get_product_detail`, `.get_related_products` | Product data for Webflow pages | — |
| `api.webflow_portal.get_msrp`, `.get_stock_status` | Public MSRP and stock status | — |
| `api.driver_controller_configurator.*` (6) | Driver/controller configurator | — |
| `api.driver_catalog.input_protocols`, `api.tape_neon_configurator.get_mounting_accessories`, `api.public_sheet.preview` | Public configurator helpers | — |

Guest also has **read/write/create on ilL-Webflow-Session** through DocType permissions (§7) — any visitor with REST access to `/api/resource/ilL-Webflow-Session` could create or edit sessions (INFERRED from DocPerm; needs a live test, G-011).

### 5.2 Full endpoint list

| # | Endpoint (`illumenate_lighting.illumenate_lighting.` omitted) | Guest | In-repo callers found | Source |
|---|---|---|---|---|
| 1 | `api.configurator_engine.auto_select_tape_for_configuration` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal page /portal/edit_fixture | `api/configurator_engine.py:4771` |
| 2 | `api.configurator_engine.debug_template_data` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_engine.py:545` |
| 3 | `api.configurator_engine.get_cascading_options_for_template` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal include `configurator_fixture_form.html` (name match); Portal page /portal/edit_fixture | `api/configurator_engine.py:4989` |
| 4 | `api.configurator_engine.get_ccts_for_template` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal page /portal/edit_fixture | `api/configurator_engine.py:4299` |
| 5 | `api.configurator_engine.get_delivered_outputs_for_template` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal page /portal/edit_fixture | `api/configurator_engine.py:4529` |
| 6 | `api.configurator_engine.get_environment_ratings_for_template` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_engine.py:4245` |
| 7 | `api.configurator_engine.get_led_packages_for_template` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_engine.py:4171` |
| 8 | `api.configurator_engine.validate_and_quote` |  | Configurator JS `coordinator.js`; Portal page /configure_multisegment; Portal page /configure_old; Portal page /portal/edit_fixture; server: `api/quote_order_configurator.py` | `api/configurator_engine.py:596` |
| 9 | `api.configurator_engine.validate_and_quote_inches` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_engine.py:925` |
| 10 | `api.configurator_engine.validate_and_quote_multisegment` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal page /configure_multisegment; Portal page /portal/edit_fixture; server: `api/quote_order_configurator.py` | `api/configurator_engine.py:1344` |
| 11 | `api.configurator_engine.validate_and_quote_multisegment_with_output` |  | Configurator JS `coordinator.js`; Configurator JS `fixture_steps.js` (name match); Portal include `configurator_fixture_form.html` (name match); Portal page /portal/edit_fixture | `api/configurator_engine.py:1199` |
| 12 | `api.configurator_engine.validate_and_quote_with_output` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_engine.py:1034` |
| 13 | `api.configurator_session.get_latest_session` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configurator_session.py:23` |
| 14 | `api.configurator_session.save_session` |  | React configurator UI (`tools/configurator_ui`) | `api/configurator_session.py:8` |
| 15 | `api.configured_product_builder.allowed_tape_offerings_for_template` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configured_product_builder.py:681` |
| 16 | `api.configured_product_builder.calculate_and_lookup` |  | server: `api/quote_order_configurator.py` | `api/configured_product_builder.py:105` |
| 17 | `api.configured_product_builder.preview_bom` |  | server: `api/quote_order_configurator.py` | `api/configured_product_builder.py:201` |
| 18 | `api.configured_product_builder.preview_prospective_bom` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configured_product_builder.py:256` |
| 19 | `api.configured_product_builder.save_and_apply` |  | server: `api/quote_order_configurator.py` | `api/configured_product_builder.py:305` |
| 20 | `api.configured_product_builder.save_and_apply_from_portal` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/configured_product_builder.py:411` |
| 21 | `api.desk_configurator.build_configured_line` |  | Configurator JS `fixture_steps.js` (name match); Configurator JS `led_sheet_steps.js` (name match); Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:471` |
| 22 | `api.desk_configurator.create_schedule_version` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:433` |
| 23 | `api.desk_configurator.ensure_project_and_schedule` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:344` |
| 24 | `api.desk_configurator.get_desk_context` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:212` |
| 25 | `api.desk_configurator.get_next_fixture_type` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:327` |
| 26 | `api.desk_configurator.get_schedule_picker_data` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:257` |
| 27 | `api.desk_configurator.reopen_row` |  | Desk dialog (Configure & Add Fixture) (name match) | `api/desk_configurator.py:967` |
| 28 | `api.document_requests.add_deliverable` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:653` |
| 29 | `api.document_requests.add_request_attachment` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:621` |
| 30 | `api.document_requests.create_request` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:266` |
| 31 | `api.document_requests.get_request_counts` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:765` |
| 32 | `api.document_requests.get_request_detail` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:511` |
| 33 | `api.document_requests.get_request_type_fields` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:218` |
| 34 | `api.document_requests.get_request_types` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:157` |
| 35 | `api.document_requests.list_requests` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:387` |
| 36 | `api.document_requests.publish_deliverable` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:704` |
| 37 | `api.document_requests.submit_request` |  | Portal page /portal/drawings | `api/document_requests.py:355` |
| 38 | `api.document_requests.update_request_status` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/document_requests.py:732` |
| 39 | `api.driver_catalog.input_protocols` | **Yes** | Configurator JS `shared_configurator.js` | `api/driver_catalog.py:20` |
| 40 | `api.driver_controller_configurator.get_controller_cascading_options` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:109` |
| 41 | `api.driver_controller_configurator.get_controller_configurator_init` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:93` |
| 42 | `api.driver_controller_configurator.get_driver_cascading_options` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:99` |
| 43 | `api.driver_controller_configurator.get_driver_configurator_init` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:87` |
| 44 | `api.driver_controller_configurator.validate_controller_configuration` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:125` |
| 45 | `api.driver_controller_configurator.validate_driver_configuration` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/driver_controller_configurator.py:119` |
| 46 | `api.exports.check_pricing_permission` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/exports.py:1535` |
| 47 | `api.exports.debug_schedule_lines` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/exports.py:1172` |
| 48 | `api.exports.download_export_file` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/exports.py:1546` |
| 49 | `api.exports.generate_schedule_csv` |  | Portal page /portal/projects/<project>/schedules/new | `api/exports.py:1287` |
| 50 | `api.exports.generate_schedule_pdf` |  | Portal page /portal/projects/<project>/schedules/new | `api/exports.py:1208` |
| 51 | `api.exports.get_export_history` |  | Portal page /portal/projects/<project>/schedules/new | `api/exports.py:1361` |
| 52 | `api.exports.get_project_export_files` |  | Portal page /portal/projects/<project> | `api/exports.py:1432` |
| 53 | `api.exports.serve_export_file` |  | Portal page /portal/projects/<project>/schedules/new | `api/exports.py:1650` |
| 54 | `api.exports.validate_file_access` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/exports.py:1597` |
| 55 | `api.extrusion_kit_configurator.get_kit_cascading_options` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/extrusion_kit_configurator.py:190` |
| 56 | `api.extrusion_kit_configurator.get_kit_component_stock` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/extrusion_kit_configurator.py:770` |
| 57 | `api.extrusion_kit_configurator.get_kit_configurator_init` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/extrusion_kit_configurator.py:82` |
| 58 | `api.extrusion_kit_configurator.get_kit_spec_data` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/extrusion_kit_configurator.py:724` |
| 59 | `api.extrusion_kit_configurator.save_kit_to_schedule` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/extrusion_kit_configurator.py:556` |
| 60 | `api.extrusion_kit_configurator.validate_kit_configuration` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/extrusion_kit_configurator.py:303` |
| 61 | `api.fixture_group_configurator.preview` |  | Configurator JS `fixture_group_editor.js` | `api/fixture_group_configurator.py:214` |
| 62 | `api.guardrail_audits.get_coverage_summary` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/guardrail_audits.py:392` |
| 63 | `api.guardrail_audits.run_coverage_audit` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/guardrail_audits.py:21` |
| 64 | `api.led_sheet_configurator.save_sheet_configuration` |  | Configurator JS `led_sheet_steps.js` (name match); Portal include `configurator_led_sheet_form.html` (name match) | `api/led_sheet_configurator.py:464` |
| 65 | `api.led_sheet_configurator.validate_sheet_configuration` |  | Configurator JS `led_sheet_steps.js` (name match); Portal include `configurator_led_sheet_form.html` (name match); server: `api/quote_order_configurator.py` | `api/led_sheet_configurator.py:191` |
| 66 | `api.manufacturing_generator.generate_from_sales_order` |  | Desk Sales Order form JS | `api/manufacturing_generator.py:176` |
| 67 | `api.manufacturing_generator.generate_manufacturing_artifacts` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/manufacturing_generator.py:65` |
| 68 | `api.portal.add_schedule_line` |  | Configurator JS `led_sheet_steps.js` (name match); Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1411` |
| 69 | `api.portal.archive_project` |  | Portal page /portal/projects; Portal page /portal/projects/<project> | `api/portal.py:2136` |
| 70 | `api.portal.create_contact` |  | Portal page /portal/projects/<project> | `api/portal.py:3249` |
| 71 | `api.portal.create_customer` |  | Portal page /portal/projects/<project> | `api/portal.py:2549` |
| 72 | `api.portal.create_drawing_request` |  | Portal page /portal/drawings | `api/portal.py:2622` |
| 73 | `api.portal.create_project` |  | Portal page /portal/projects/<project> | `api/portal.py:2001` |
| 74 | `api.portal.create_schedule` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:2205` |
| 75 | `api.portal.create_schedule_sales_order` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:2506` |
| 76 | `api.portal.create_schedule_version` |  | Desk dialog (Configure & Add Fixture) (name match); Portal page /portal/projects/<project>/schedules/new | `api/portal.py:3831` |
| 77 | `api.portal.create_support_ticket` |  | Portal page /portal/support | `api/portal.py:2698` |
| 78 | `api.portal.create_website_user` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/portal.py:4108` |
| 79 | `api.portal.delete_schedule` |  | Portal page /portal/projects/<project>; Portal page /portal/projects/<project>/schedules/new | `api/portal.py:2293` |
| 80 | `api.portal.delete_schedule_line` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1506` |
| 81 | `api.portal.download_order_document` |  | Portal page controller `order_detail.py` | `api/portal.py:2999` |
| 82 | `api.portal.duplicate_schedule_line` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1557` |
| 83 | `api.portal.find_matching_variant` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1203` |
| 84 | `api.portal.get_account_settings` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:2850` |
| 85 | `api.portal.get_allowed_customers_for_project` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:80` |
| 86 | `api.portal.get_company_contacts` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:3192` |
| 87 | `api.portal.get_company_customers` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:3340` |
| 88 | `api.portal.get_company_website_users` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/portal.py:4051` |
| 89 | `api.portal.get_company_website_users_query` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/portal.py:3990` |
| 90 | `api.portal.get_configured_fixture_details` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:1767` |
| 91 | `api.portal.get_configured_fixture_for_editing` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:3507` |
| 92 | `api.portal.get_configured_sheet_for_line` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:4175` |
| 93 | `api.portal.get_contacts_for_project` |  | Portal page /portal/projects/<project> | `api/portal.py:3404` |
| 94 | `api.portal.get_filtered_variant_attributes` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1047` |
| 95 | `api.portal.get_fixture_templates` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1276` |
| 96 | `api.portal.get_item_variant_attributes` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:943` |
| 97 | `api.portal.get_item_variants` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:1139` |
| 98 | `api.portal.get_items_by_product_type` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:843` |
| 99 | `api.portal.get_led_sheet_templates` |  | Configurator JS `led_sheet_steps.js` (name match); Portal include `configurator_led_sheet_form.html` (name match); Portal page /portal/projects/<project>/schedules/new | `api/portal.py:4116` |
| 100 | `api.portal.get_order_details` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:2952` |
| 101 | `api.portal.get_portal_notifications` |  | `portal.js` | `api/portal.py:3010` |
| 102 | `api.portal.get_product_types` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:631` |
| 103 | `api.portal.get_schedule_dealer_pricing` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:4201` |
| 104 | `api.portal.get_schedule_lines_for_configurator` |  | Configurator JS `coordinator.js`; Configurator JS `shared_configurator.js` | `api/portal.py:339` |
| 105 | `api.portal.get_schedule_version_history` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:3867` |
| 106 | `api.portal.get_schedules_for_project` |  | Configurator JS `coordinator.js`; Configurator JS `shared_configurator.js` | `api/portal.py:298` |
| 107 | `api.portal.get_tape_neon_templates_for_schedule` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1342` |
| 108 | `api.portal.get_template_options` |  | Portal page /configure_multisegment; Portal page /configure_old | `api/portal.py:468` |
| 109 | `api.portal.get_user_projects_for_configurator` |  | Configurator JS `coordinator.js`; Configurator JS `shared_configurator.js` | `api/portal.py:223` |
| 110 | `api.portal.get_user_role_info` |  | Desk form JS `ill_project_fixture_schedule.js` | `api/portal.py:3064` |
| 111 | `api.portal.invite_project_collaborator` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:3099` |
| 112 | `api.portal.move_schedule_line` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1603` |
| 113 | `api.portal.remove_project_collaborator` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:3149` |
| 114 | `api.portal.rename_schedule` |  | Portal page /portal/projects/<project> | `api/portal.py:2255` |
| 115 | `api.portal.request_schedule_quote` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:2433` |
| 116 | `api.portal.save_configured_fixture_to_schedule` |  | Configurator JS `fixture_steps.js` (name match); Portal page /configure_multisegment; Portal page /configure_old; Portal page /portal/configure (name match) | `api/portal.py:1900` |
| 117 | `api.portal.save_notification_preferences` |  | Portal page /portal/account | `api/portal.py:2881` |
| 118 | `api.portal.save_portal_preferences` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/portal.py:2918` |
| 119 | `api.portal.set_order_request_po_number` |  | Portal page /portal/orders/<order> | `api/portal.py:2984` |
| 120 | `api.portal.toggle_project_privacy` |  | Portal page /portal/projects/<project>/collaborators | `api/portal.py:2396` |
| 121 | `api.portal.unarchive_project` |  | Portal page /portal/projects; Portal page /portal/projects/<project> | `api/portal.py:2170` |
| 122 | `api.portal.update_configured_fixture_on_schedule` |  | Portal page /portal/edit_fixture | `api/portal.py:3725` |
| 123 | `api.portal.update_project` |  | Portal page /portal/projects/<project>; Portal page /portal/projects/<project>/collaborators | `api/portal.py:2069` |
| 124 | `api.portal.update_project_collaborators` |  | Portal page /portal/projects/<project>/collaborators | `api/portal.py:2330` |
| 125 | `api.portal.update_schedule_line` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:1657` |
| 126 | `api.portal.update_schedule_status` |  | Portal page /portal/projects/<project>/schedules/new | `api/portal.py:2463` |
| 127 | `api.portal.update_user_profile` |  | Portal page /portal/account | `api/portal.py:2774` |
| 128 | `api.pricing_utils.get_bom_stock_for_items_api` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/pricing_utils.py:595` |
| 129 | `api.product_catalog.get_catalog_filter_options` |  | `product_catalog.js` | `api/product_catalog.py:277` |
| 130 | `api.product_catalog.get_catalog_product_detail` |  | `product_detail.js` | `api/product_catalog.py:230` |
| 131 | `api.product_catalog.get_catalog_products` |  | `product_catalog.js` | `api/product_catalog.py:67` |
| 132 | `api.product_readiness.affected_products` |  | `authoring_readiness.js` | `api/product_readiness.py:371` |
| 133 | `api.product_readiness.authoring_preview` |  | `authoring_readiness.js` | `api/product_readiness.py:24` |
| 134 | `api.product_readiness.preview` |  | `product_publication.js` | `api/product_readiness.py:365` |
| 135 | `api.public_sheet.preview` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/public_sheet.py:137` |
| 136 | `api.publication.acknowledge` |  | n8n `webflow_product_sync.json` | `api/publication.py:283` |
| 137 | `api.publication.claim` |  | n8n `webflow_product_sync.json` | `api/publication.py:230` |
| 138 | `api.publication.inspect` |  | `product_publication.js`; n8n `webflow_product_sync.json` (name match) | `api/publication.py:158` |
| 139 | `api.publication.reconcile_local` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/publication.py:378` |
| 140 | `api.publication.reconciliation_batch` |  | CLI `tools/reconcile_webflow.cjs` | `api/publication.py:416` |
| 141 | `api.publication.request` |  | CLI `tools/reconcile_webflow.cjs` (name match); `product_publication.js` | `api/publication.py:166` |
| 142 | `api.publication.retry` |  | CLI `tools/reconcile_webflow.cjs` (name match); `product_publication.js`; n8n `webflow_product_sync.json` (name match) | `api/publication.py:351` |
| 143 | `api.qbo_sync.receive_payment_event` | **Yes** | `ill_qbo_settings.json` (reference in JSON); n8n `quickbooks_payment_sync.json` | `api/qbo_sync.py:65` |
| 144 | `api.quote_from_schedule.add_schedule_to_quotation` |  | Desk Quotation form JS | `api/quote_from_schedule.py:54` |
| 145 | `api.quote_from_schedule.add_schedule_to_transaction` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_from_schedule.py:76` |
| 146 | `api.quote_from_schedule.get_schedule_summary` |  | Desk Quotation form JS | `api/quote_from_schedule.py:31` |
| 147 | `api.quote_order_configurator.add_configured_sheet_to_quote_order` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:761` |
| 148 | `api.quote_order_configurator.apply_configured_product` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:241` |
| 149 | `api.quote_order_configurator.apply_existing_configured_product` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:176` |
| 150 | `api.quote_order_configurator.get_bom_preview` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:112` |
| 151 | `api.quote_order_configurator.get_product_types` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:39` |
| 152 | `api.quote_order_configurator.qoc_get_product_types` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/quote_order_configurator.py:50` |
| 153 | `api.reconciliation.check_artifact_sync` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/reconciliation.py:22` |
| 154 | `api.reconciliation.get_sync_status_batch` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/reconciliation.py:409` |
| 155 | `api.reconciliation.regenerate_artifacts` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/reconciliation.py:307` |
| 156 | `api.spec_sheet_export.export_spec_sheet_csv` |  | Desk form JS `ill_webflow_product.js` | `api/spec_sheet_export.py:1912` |
| 157 | `api.spec_sheets.probe.run` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/spec_sheets/probe.py:98` |
| 158 | `api.spec_submittal.generate_spec_submittal_packet` |  | Portal page /portal/projects/<project>/schedules/new | `api/spec_submittal.py:1036` |
| 159 | `api.tape_neon_configurator.get_mounting_accessories` | **Yes** | Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:3852` |
| 160 | `api.tape_neon_configurator.get_neon_configurator_init` |  | Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:877` |
| 161 | `api.tape_neon_configurator.get_tape_cascading_options` |  | Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:332` |
| 162 | `api.tape_neon_configurator.get_tape_configurator_init` |  | Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:250` |
| 163 | `api.tape_neon_configurator.get_tape_neon_spec_cascading` |  | Configurator JS `coordinator.js` | `api/tape_neon_configurator.py:1792` |
| 164 | `api.tape_neon_configurator.get_tape_neon_spec_init` |  | Configurator JS `coordinator.js` | `api/tape_neon_configurator.py:1677` |
| 165 | `api.tape_neon_configurator.get_tape_neon_template_cascading` |  | Configurator JS `coordinator.js`; Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:2019` |
| 166 | `api.tape_neon_configurator.get_tape_neon_template_init` |  | Configurator JS `coordinator.js`; Configurator JS `tape_neon_steps.js` | `api/tape_neon_configurator.py:1862` |
| 167 | `api.tape_neon_configurator.save_tape_neon_template_to_schedule` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/tape_neon_configurator.py:2304` |
| 168 | `api.tape_neon_configurator.save_tape_to_schedule` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/tape_neon_configurator.py:1469` |
| 169 | `api.tape_neon_configurator.select_driver_plan_for_tape_neon` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/tape_neon_configurator.py:2685` |
| 170 | `api.tape_neon_configurator.validate_neon_configuration` |  | Configurator JS `coordinator.js`; Configurator JS `tape_neon_steps.js`; server: `api/quote_order_configurator.py` | `api/tape_neon_configurator.py:961` |
| 171 | `api.tape_neon_configurator.validate_tape_configuration` |  | Configurator JS `coordinator.js`; Configurator JS `tape_neon_steps.js`; server: `api/quote_order_configurator.py` | `api/tape_neon_configurator.py:401` |
| 172 | `api.tape_neon_configurator.validate_tape_neon_template_config` |  | Configurator JS `coordinator.js` | `api/tape_neon_configurator.py:2163` |
| 173 | `api.webflow_attributes.get_all_attributes_for_sync` |  | n8n `webflow_attribute_sync.json` | `api/webflow_attributes.py:953` |
| 174 | `api.webflow_attributes.get_attribute_dependencies` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_attributes.py:1404` |
| 175 | `api.webflow_attributes.get_attribute_sync_statistics` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_attributes.py:1223` |
| 176 | `api.webflow_attributes.get_attribute_type_mapping` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_attributes.py:581` |
| 177 | `api.webflow_attributes.get_product_attribute_references` |  | n8n `webflow_product_attribute_filter_sync.json` | `api/webflow_attributes.py:1713` |
| 178 | `api.webflow_attributes.get_webflow_attributes` |  | n8n `webflow_attribute_sync.json` | `api/webflow_attributes.py:700` |
| 179 | `api.webflow_attributes.mark_attribute_error` |  | n8n `webflow_attribute_sync.json` | `api/webflow_attributes.py:1092` |
| 180 | `api.webflow_attributes.mark_attribute_synced` |  | n8n `webflow_attribute_sync.json` | `api/webflow_attributes.py:1022` |
| 181 | `api.webflow_attributes.mark_filter_synced` |  | n8n `webflow_product_attribute_filter_sync.json` | `api/webflow_attributes.py:1926` |
| 182 | `api.webflow_attributes.reset_all_webflow_sync_status` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_attributes.py:1359` |
| 183 | `api.webflow_attributes.trigger_attribute_sync` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_attributes.py:1150` |
| 184 | `api.webflow_auth.get_user_context` | **Yes** | React configurator UI (`tools/configurator_ui`); Webflow embed `webflow_portal.js` | `api/webflow_auth.py:21` |
| 185 | `api.webflow_brand.get_brand_config` |  | n8n `webflow_attribute_sync.json` (name match); n8n `webflow_category_sync.json`; n8n `webflow_product_attribute_filter_sync.json` | `api/webflow_brand.py:236` |
| 186 | `api.webflow_brand.list_brands` |  | Desk form JS `ill_webflow_category_list.js`; Desk form JS `ill_webflow_product_list.js` | `api/webflow_brand.py:213` |
| 187 | `api.webflow_configurator.create_complex_fixture_session` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:472` |
| 188 | `api.webflow_configurator.download_spec_sheet` | **Yes** | Webflow embed `webflow_spec_sheet_download.js`; Webflow embed script (docs copy) | `api/webflow_configurator.py:531` |
| 189 | `api.webflow_configurator.get_cascading_options` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:214` |
| 190 | `api.webflow_configurator.get_configurator_init` | **Yes** | server: `api/quote_order_configurator.py` | `api/webflow_configurator.py:55` |
| 191 | `api.webflow_configurator.get_configurator_init_by_template` |  | server: `api/quote_order_configurator.py` | `api/webflow_configurator.py:132` |
| 192 | `api.webflow_configurator.get_part_number_preview` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:440` |
| 193 | `api.webflow_configurator.get_session` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:626` |
| 194 | `api.webflow_configurator.get_sheet_configurator_data` | **Yes** | Webflow embed `webflow_spec_sheet_download.js` | `api/webflow_configurator.py:2136` |
| 195 | `api.webflow_configurator.get_tape_neon_mounting_options` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:2073` |
| 196 | `api.webflow_configurator.validate_configuration` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_configurator.py:307` |
| 197 | `api.webflow_export.get_sync_statistics` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:917` |
| 198 | `api.webflow_export.get_webflow_categories` |  | n8n `webflow_category_sync.json` | `api/webflow_export.py:629` |
| 199 | `api.webflow_export.get_webflow_products` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:187` |
| 200 | `api.webflow_export.mark_category_error` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:781` |
| 201 | `api.webflow_export.mark_category_synced` |  | n8n `webflow_category_sync.json` | `api/webflow_export.py:735` |
| 202 | `api.webflow_export.mark_webflow_error` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:615` |
| 203 | `api.webflow_export.mark_webflow_synced` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:600` |
| 204 | `api.webflow_export.preview_specifications` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_export.py:1064` |
| 205 | `api.webflow_export.trigger_sync` |  | Desk form JS `ill_webflow_product.js` | `api/webflow_export.py:824` |
| 206 | `api.webflow_integration.get_active_products_for_webflow` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_integration.py:630` |
| 207 | `api.webflow_integration.get_product_detail` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_integration.py:22` |
| 208 | `api.webflow_integration.get_products_by_codes` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_integration.py:718` |
| 209 | `api.webflow_integration.get_related_products` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_integration.py:565` |
| 210 | `api.webflow_leads.create_lead_from_webflow` | **Yes** | n8n `webflow_lead_form.json`; n8n `webflow_lead_form_206.json` | `api/webflow_leads.py:45` |
| 211 | `api.webflow_leads.create_lead_from_webflow_webhook` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_leads.py:247` |
| 212 | `api.webflow_leads.get_lead_sources` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_leads.py:478` |
| 213 | `api.webflow_leads.health_check` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_leads.py:463` |
| 214 | `api.webflow_portal.add_fixture_to_schedule` |  | Webflow embed `webflow_portal.js` | `api/webflow_portal.py:291` |
| 215 | `api.webflow_portal.get_fixture_schedules` |  | Webflow embed `webflow_portal.js` | `api/webflow_portal.py:155` |
| 216 | `api.webflow_portal.get_line_ids` |  | Webflow embed `webflow_portal.js` | `api/webflow_portal.py:210` |
| 217 | `api.webflow_portal.get_msrp` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_portal.py:680` |
| 218 | `api.webflow_portal.get_pricing` |  | Webflow embed `webflow_portal.js` | `api/webflow_portal.py:392` |
| 219 | `api.webflow_portal.get_projects` |  | Webflow embed `webflow_portal.js` | `api/webflow_portal.py:95` |
| 220 | `api.webflow_portal.get_schedule_kit_stock` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_portal.py:540` |
| 221 | `api.webflow_portal.get_stock_status` | **Yes** | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_portal.py:474` |
| 222 | `api.webflow_schedule.add_from_session` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_schedule.py:212` |
| 223 | `api.webflow_schedule.add_to_schedule` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_schedule.py:24` |
| 224 | `api.webflow_schedule.create_quick_project_and_schedule` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_schedule.py:316` |
| 225 | `api.webflow_schedule.get_user_schedules` |  | Configurator JS `shared_configurator.js` | `api/webflow_schedule.py:272` |
| 226 | `api.webflow_schedule.remove_line` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_schedule.py:634` |
| 227 | `api.webflow_schedule.update_line_quantity` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `api/webflow_schedule.py:581` |
| 228 | `doctype.ill_controller_submittal_mapping.ill_controller_submittal_mapping.get_doctype_fields` |  | Desk form JS `ill_controller_submittal_mapping.js` | `doctype/ill_controller_submittal_mapping/ill_controller_submittal_mapping.py:21` |
| 229 | `doctype.ill_document_request.ill_document_request.ilLDocumentRequest.publish_deliverable (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_document_request/ill_document_request.py:287` |
| 230 | `doctype.ill_document_request.ill_document_request.ilLDocumentRequest.submit_request (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_document_request/ill_document_request.py:277` |
| 231 | `doctype.ill_driver_submittal_mapping.ill_driver_submittal_mapping.get_doctype_fields` |  | Desk form JS `ill_driver_submittal_mapping.js` | `doctype/ill_driver_submittal_mapping/ill_driver_submittal_mapping.py:21` |
| 232 | `doctype.ill_fixture_template.ill_fixture_template.populate_part_number_builder` |  | Desk form JS `ill_fixture_template.js` | `doctype/ill_fixture_template/ill_fixture_template.py:117` |
| 233 | `doctype.ill_led_sheet_submittal_mapping.ill_led_sheet_submittal_mapping.get_doctype_fields` |  | Desk form JS `ill_led_sheet_submittal_mapping.js` | `doctype/ill_led_sheet_submittal_mapping/ill_led_sheet_submittal_mapping.py:14` |
| 234 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.create_new_version (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:163` |
| 235 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.create_sales_order (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:237` |
| 236 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.create_sales_order_result (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:281` |
| 237 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.duplicate_line (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:1238` |
| 238 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.move_line (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:1272` |
| 239 | `doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.ilLProjectFixtureSchedule.request_quote (doc method)` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py:1231` |
| 240 | `doctype.ill_spec_submittal_mapping.ill_spec_submittal_mapping.get_doctype_fields` |  | Desk form JS `ill_neon_submittal_mapping.js`; Desk form JS `ill_spec_submittal_mapping.js` | `doctype/ill_spec_submittal_mapping/ill_spec_submittal_mapping.py:14` |
| 241 | `portal.accounts.accept_invitation` |  | Portal page /portal/accept-invitation | `portal/accounts.py:360` |
| 242 | `portal.accounts.archive_record` |  | `portal_accounts.js` (name match) | `portal/accounts.py:273` |
| 243 | `portal.accounts.disable_member` |  | `portal_accounts.js` (name match) | `portal/accounts.py:439` |
| 244 | `portal.accounts.invite` |  | `portal_accounts.js` (name match) | `portal/accounts.py:314` |
| 245 | `portal.accounts.overview` |  | `portal_accounts.js` (name match) | `portal/accounts.py:101` |
| 246 | `portal.accounts.reply` |  | `portal_accounts.js` (name match) | `portal/accounts.py:547` |
| 247 | `portal.accounts.request_change` |  | Portal page /portal/account; `portal_accounts.js` (name match) | `portal/accounts.py:189` |
| 248 | `portal.accounts.review` |  | Desk form JS `ill_account_request.js`; Portal page /portal/account (name match); `portal_accounts.js` (name match) | `portal/accounts.py:462` |
| 249 | `portal.accounts.revoke_invitation` |  | `portal_accounts.js` (name match) | `portal/accounts.py:426` |
| 250 | `portal.accounts.save_record` |  | `portal_accounts.js` (name match) | `portal/accounts.py:237` |
| 251 | `portal.accounts.set_purchasing_contact` |  | `portal_accounts.js` (name match) | `portal/accounts.py:293` |
| 252 | `portal.commercial_tasks.assign` |  | `commercial_tasks.js` | `portal/commercial_tasks.py:13` |
| 253 | `portal.configuration.calculate` |  | Configurator JS `coordinator.js` (name match); Configurator JS `fixture_steps.js` (name match); Configurator JS `led_sheet_steps.js` (name match); Configurator JS `tape_neon_steps.js` (name match); Portal page /portal/edit_fixture (name match) | `portal/configuration.py:114` |
| 254 | `portal.configuration.save` |  | Configurator JS `coordinator.js` (name match); Configurator JS `fixture_steps.js` (name match); Configurator JS `led_sheet_steps.js` (name match); Configurator JS `shared_configurator.js`; Configurator JS `tape_neon_steps.js` (name match); Desk dialog (Configure & Add Fixture) (name match); Portal include `configurator_tape_neon_form.html` (name match); Portal page /configure_old (name match); Portal page /portal/configure (name match); Portal page /portal/configure-tape (name match); Portal page /portal/edit_fixture (name match); Portal page /portal/orders/<order> (name match); Portal page /portal/projects/<project>/schedules/new (name match); `product_detail.js` (name match) | `portal/configuration.py:207` |
| 255 | `portal.configuration_reopen.load` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `portal/configuration_reopen.py:105` |
| 256 | `portal.conversations.list_messages` |  | `portal_conversation.js` (name match) | `portal/conversations.py:81` |
| 257 | `portal.conversations.reply` |  | `portal_conversation.js` (name match) | `portal/conversations.py:163` |
| 258 | `portal.drawing_review.decide` |  | Portal page /portal/drawings/<request> | `portal/drawing_review.py:64` |
| 259 | `portal.files.upload` |  | Portal page /portal/projects/<project>/schedules/new (name match); `portal_line_documents.js` (name match); `portal_uploads.js` | `portal/files.py:87` |
| 260 | `portal.line_documents.attach` |  | `portal_line_documents.js` (name match) | `portal/line_documents.py:36` |
| 261 | `portal.line_documents.download` |  | `portal_line_documents.js` (name match) | `portal/line_documents.py:140` |
| 262 | `portal.line_documents.list_documents` |  | `portal_line_documents.js` (name match) | `portal/line_documents.py:23` |
| 263 | `portal.line_documents.remove` |  | `portal_line_documents.js` (name match) | `portal/line_documents.py:100` |
| 264 | `portal.offers.detail` |  | Portal page /portal/quotes/<offer> (name match) | `portal/offers.py:376` |
| 265 | `portal.offers.list_offers` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `portal/offers.py:422` |
| 266 | `portal.offers.prepare_quotation` |  | `quote_request.js` | `portal/offers.py:202` |
| 267 | `portal.offers.respond` |  | Portal page /portal/quotes/<offer> | `portal/offers.py:287` |
| 268 | `portal.order_acknowledgment.download` |  | Portal page /portal/orders/<order> | `portal/order_acknowledgment.py:74` |
| 269 | `portal.order_changes.decide` |  | `commercial_tasks.js` | `portal/order_changes.py:222` |
| 270 | `portal.order_changes.review_context` |  | `commercial_tasks.js` | `portal/order_changes.py:201` |
| 271 | `portal.order_changes.submit` |  | `portal_commercial.js` (name match) | `portal/order_changes.py:138` |
| 272 | `portal.order_intake.complete` |  | `portal_order_intake.js` (name match) | `portal/order_intake.py:261` |
| 273 | `portal.order_intake.prepare` |  | `portal_order_intake.js` (name match) | `portal/order_intake.py:111` |
| 274 | `portal.order_intake.submit` |  | `portal_order_intake.js` (name match) | `portal/order_intake.py:219` |
| 275 | `portal.order_review.acknowledge` |  | Desk Sales Order form JS (name match); Portal page /portal/orders/<order> | `portal/order_review.py:350` |
| 276 | `portal.order_review.review` |  | Desk Sales Order form JS; Portal page /portal/orders/<order> (name match); `portal_commercial.js` (name match) | `portal/order_review.py:260` |
| 277 | `portal.order_review.withdraw` |  | `portal_commercial.js` (name match) | `portal/order_review.py:315` |
| 278 | `portal.orders.search_orders` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `portal/orders.py:297` |
| 279 | `portal.outbox.retry` |  | `portal_delivery.js` | `portal/outbox.py:213` |
| 280 | `portal.packet_jobs.issue` |  | Portal page /portal/projects/<project>/schedules/new | `portal/packet_jobs.py:189` |
| 281 | `portal.packet_jobs.retry` |  | Portal page /portal/projects/<project>/schedules/new | `portal/packet_jobs.py:174` |
| 282 | `portal.packet_jobs.status` |  | Portal page /portal/projects/<project>/schedules/new | `portal/packet_jobs.py:156` |
| 283 | `portal.queues.items` |  | Desk page Portal Operations | `portal/queues.py:164` |
| 284 | `portal.queues.summary` |  | Desk page Portal Operations | `portal/queues.py:185` |
| 285 | `portal.quotes.request_quote` |  | `portal_commercial.js` (name match) | `portal/quotes.py:62` |
| 286 | `portal.standard_products.add` |  | `product_detail.js` (name match) | `portal/standard_products.py:103` |
| 287 | `portal.standard_products.prepare` |  | `product_detail.js` (name match) | `portal/standard_products.py:79` |
| 288 | `portal.support.detail` |  | Portal page /portal/drawings/<request> (name match); Portal page /portal/orders/<order> (name match); Portal page /portal/support (name match); `ill_request_type.json` (reference in JSON) (name match); `product_detail.js` (name match) | `portal/support.py:71` |
| 289 | `portal.support.list_tickets` |  | **none found** — external (Webflow site / n8n instance / bench) or unused: UNKNOWN | `portal/support.py:48` |
| 290 | `templates.pages.configure.get_configurator_markup` |  | Desk dialog (Configure & Add Fixture); Portal include `configurator_fixture_form.html` (name match); Portal include `configurator_form.html`; Portal include `configurator_led_sheet_form.html` (name match); Portal include `configurator_tape_neon_form.html` (name match) | `illumenate_lighting/templates/pages/configure.py:324` |

---

## 6. Customizations shipped by the app

### 6.1 Workflows

| Workflow | DocType | Installed by code? | Notes |
|---|---|---|---|
| `ilL Document Request Workflow` (states Draft → Submitted → In Progress ⇄ Waiting on Customer → Completed → Closed; Cancel from Draft/Submitted/In Progress; Reopen from Completed; staff transitions allowed to **System Manager** only; state field `status`) | ilL-Document-Request | **No.** Only in the unloaded `app/fixtures/ill_document_request_workflow.json`; no code creates it; hook filter name does not match (§4.4). | Whether it is active on production is **UNKNOWN (G-004)**. The DocType's own controller and portal services also set `status` directly (Phase 1 will map which path governs). |

No other Workflow records are defined in the repo. ERPNext's native docstatus lifecycle (Draft/Submitted/Cancelled) governs Quotation, Sales Order, Work Order, Delivery Note, Sales Invoice, Payment Entry, Purchase Order.

### 6.2 Custom Fields (created by patches via `create_custom_fields`)

Captured by executing every entry in `patches.txt` against a stubbed `frappe` and recording the calls (OBSERVED). Layout fields excluded.

| DocType | Fields (count) | Created by |
|---|---|---|
| Quotation | `ill_fixture_schedule` (Link schedule), `ill_quote_request` (Link Quote Request) — 2 | `consolidate_section_label_field`, `b2b_portal_foundations` |
| Sales Order | `ill_fixture_schedule`, `ill_quote_offer` (RO), `ill_requested_delivery_date` (RO), `ill_confirmed_delivery_date`, `ill_delivery_confirmed_by`, `ill_delivery_confirmed_on`, `ill_receiving_instructions`, `ill_shipping_instructions` — 8 | `consolidate_section_label_field`, `b2b_portal_foundations`, `b2b_order_service` |
| Quotation Item / Sales Order Item | 28 each: section label, fixture type, product type (Linear Fixture / LED Tape / LED Neon / LED Sheet), configured fixture / tape-neon / LED sheet / group links, dynamic configured product, configured Item, BOM, configuration JSON, BOM override JSON, template code, requested/mfg length, runs, watts, finish, lens, engine version, power-supply line flags, schedule + line ID, configurator request, save key | `add_quote_order_configurator_fields`, `add_configured_variant_fields`, `add_sales_order_section_label`, `consolidate_section_label_field`, `b2b_configurator_receipts`, `b2b_fixture_groups`, `b2b_commercial_lineage` |
| Delivery Note Item / Sales Invoice Item | 24 each: same lineage set (no power-supply or save-key fields) | `consolidate_section_label_field`, `b2b_commercial_lineage` |
| Purchase Order Item | `ill_section_label` — 1 | `consolidate_section_label_field` |
| Item | `custom_ill_configured_fixture`, `custom_ill_configured_tape_neon`, `ill_cable_assembly_length_mm` — 3 | `add_quote_order_configurator_fields`, `b2b_portal_foundations` |
| Work Order | `ill_configured_group` — 1 | `b2b_fixture_groups` |
| Customer | `custom_qbo_id`, `custom_synced_from`, `ill_purchasing_contact` — 3 | `add_qbo_sync_fields`, `b2b_accounts` |
| Supplier, Sales Invoice, Purchase Invoice | `custom_qbo_id`, `custom_synced_from` — 2 each | `add_qbo_sync_fields` |
| Payment Entry | `custom_qbo_id`, `custom_synced_from`, `custom_qbo_event_type`, `custom_qbo_last_synced`, `custom_qbo_sync_note` — 5 | `add_qbo_sync_fields`, `add_qbo_payment_sync_fields` |
| Contact | `ill_portal_contact_only`, `ill_portal_archived` — 2 | `b2b_accounts` |
| Company | `custom_invoice_payment_instructions` — 1 | `add_company_invoice_payment_instructions` |
| Issue | `ill_portal_request_key` (unique), `ill_portal_request_hash`, `ill_portal_order`, `ill_next_action_by`, `ill_support_owner`, `ill_support_due` — 6 | `b2b_portal_foundations`, `b2b_conversations` |
| Task | `ill_drawing_impact_key`, `ill_drawing_request` — 2 | `b2b_conversations` |
| ilL-Document-Request | `ill_next_action_by`, `ill_observed_build_hash`, `ill_review_state`, `ill_impact_task` — 4 | `b2b_conversations` |
| CRM Lead | `webflow_campaign_id`, `webflow_utm_source`, `webflow_utm_medium`, `webflow_utm_campaign`, `webflow_form_name`, `webflow_form_id`, `webflow_submission_id`, `webflow_form_data` — 8 | `add_webflow_lead_fields` |
| 24 × ilL-Attribute-* | `webflow_item_id`, `webflow_sync_status`, `webflow_last_synced`, `webflow_sync_error` (legacy scalars, later hidden) + `webflow_sync_targets` (Table) | `add_webflow_sync_fields_to_attributes`, `migrate_attribute_sync_fields_to_brand_table` |

**Fields the code uses that only exist in the unloaded legacy fixture** (so their presence on production is UNKNOWN, G-005):

| Field | Used by |
|---|---|
| CRM Lead `webflow_submitted_at`, `webflow_contact_form_subject`, `webflow_contact_form_message`, `webflow_contact_form_file_url`, `webflow_project_name`, `webflow_products_interested` | `app/api/webflow_leads.py` |
| Item `ill_build_id` | `app/api/manufacturing_generator.py` |
| Work Order `ill_configured_fixture` (and legacy-only `ill_functional_test_result`, `ill_serial_no`, `ill_test_notes`, which no current code reads) | `app/api/manufacturing_generator.py` (~L1199 sets `ill_configured_fixture`) |

### 6.3 Property Setters (patches)

| DocType.field | Property → value | Patch |
|---|---|---|
| CRM Lead.`job_title` | `fieldtype` → Link; `options` → `ilL-Job-Title-Master` | `convert_lead_job_title_to_link` |
| Purchase Order.`schedule_date`, Purchase Order Item.`schedule_date` | `reqd` → 0 | `make_po_schedule_date_optional` |

UI-created Property Setters on the site: UNKNOWN (G-001).

### 6.4 Print Formats

| Print Format | DocType | Where defined | Installed? |
|---|---|---|---|
| ilL Quotation | Quotation | `app/print_format/ill_quotation/` (Jinja, custom) | Yes — module-folder print formats are imported on migrate (`frappe/model/sync.py → IMPORTABLE_DOCTYPES` includes `print_format`). Not set as default. |
| ilL Sales Order | Sales Order | `app/print_format/ill_sales_order/` | Same. |
| ilL Sales Invoice | Sales Invoice | `app/print_format/ill_sales_invoice/` | Same. |
| ilL Purchase Order | Purchase Order | `app/print_format/ill_purchase_order/` | Same. |
| ilL Delivery Note | Delivery Note | Created by patch `b2b_commercial_lineage` from `illumenate_lighting/templates/print_formats/delivery_note.html` (unpriced). | Yes, if patch ran. |
| ilL Work Order Traveler; ilL Fixture Schedule | Work Order; ilL-Project-Fixture-Schedule | Only in unloaded `app/fixtures/print_format.json` | UNKNOWN (G-004). |

Site default print formats: unchanged by the app (per `docs/B2B_STAFF_OPERATIONS.md`); actual defaults UNKNOWN.

### 6.5 Reports (Script Reports, module ilLumenate Lighting)

| Report | Ref DocType | Roles | Data source (OBSERVED) |
|---|---|---|---|
| Sales Team Commissions | Sales Invoice | Sales Manager, Sales User, Accounts Manager, Accounts User, System Manager | SQL over `tabSales Invoice` ⨝ `tabSales Team` (ERPNext sales-person allocation). |
| Sales Partner Invoice Report | Sales Invoice | *(none listed)* | SQL over `tabSales Invoice` (sales partner). With no roles, access follows Sales Invoice read permission (I). |
| Email Campaign Activity Summary | CRM Lead | *(none listed)* | Reads a child "email activity log" DocType discovered from a CRM Lead field defined on the **site**, not in this repo; benchmarks from Email Campaign Benchmark Settings. |

### 6.6 Desk Page, Workspace, Number Cards

- **Page** `ill-portal-operations` ("Portal Operations"): roles System Manager, ilL Sales Review, ilL Order Approver, ilL Engineering, ilL Support, ilL Operations, ilL Integration. Calls `portal.queues.summary` / `portal.queues.items` (permission-aware counts; "Unavailable" ≠ zero).
- **Workspace** `ilLumenate Lighting` (public, no role restriction, `type: Workspace`): 18 shortcuts (Fixture/Tape-Neon/LED-Sheet/Driver/Controller/Extrusion-Kit templates, configured products, Project, Document Request, Export Job, Controller, Accessory, Portal Operations, Product Publication, Publication Jobs, Item Literature) and 15 link cards: ilLumenate Reports (Sales Team Commissions), Linear Fixture Setup (27 ordered steps), LED Tape/Neon Setup (18), LED Sheet Setup (19), Extrusion Kit Setup (14), Controller Setup (3), Accessory Setup (9), Attributes, Specifications, Projects & Scheduling, Document Requests, Relationships & Mappings, Webflow Integration, Settings & Utilities. No charts, quick lists or custom blocks. Site customizations are merged, not replaced (`portal_workspace.after_migrate`).
- **Number Cards** (loaded fixture; all public; Document Type count/sum; monthly % stats):

| Card | Definition | Note |
|---|---|---|
| Open Quotations | Count Quotation, submitted, status in Open/Replied/Partially Ordered | |
| Open Sales Orders | Count Sales Order, submitted, status not Completed/Closed/Cancelled | |
| Sales Invoiced MTD | Sum Sales Invoice `grand_total`, submitted | **No date filter** in `filters_json`; name says MTD. Whether the Number Card's built-in time settings limit it is UNKNOWN (G-013). |
| AR Outstanding | Sum Sales Invoice `outstanding_amount` > 0, submitted | Only meaningful if ERPNext outstanding is kept current (depends on payment sync; §9). |
| Open Purchase Orders | Count Purchase Order, submitted, open statuses | |
| AP Outstanding | Sum Purchase Invoice `outstanding_amount` > 0, submitted | |

---

## 7. Roles and permissions

### 7.1 Roles referenced in code or fixtures

| Role | Created by | Desk access | Meaning in code |
|---|---|---|---|
| System Manager | Frappe | Yes | Treated as **internal** everywhere (`ill_project.INTERNAL_ROLES`), bypasses portal scoping; satisfies every staff capability (`portal/staff.allowed`). |
| Administrator (user) | Frappe | Yes | Always allowed. |
| Dealer | `app/install.py → create_dealer_role` (desk_access 0); `b2b_portal_foundations` forces desk_access 0 | **No** | External dealer/buyer; company-wide access to their Customer's projects; can request quotes and submit order intakes; cannot submit Sales Orders. |
| Website User / Customer | Frappe / ERPNext | No | Portal users without Dealer role; `role_home_page` → `/portal`. Collaborators are Website Users (per `docs/DEALER_ROLE.md`). |
| All | Frappe automatic | — | **Includes website users** (`frappe/permissions.py`: `ALL_USER_ROLE = "All"  # This includes website users too.`). |
| Guest | Frappe automatic | — | Unauthenticated. |
| ilL Sales Review | `b2b_portal_foundations` | Yes | Capability `sales`, `accounts`: prepare Quotation from intake, issue offers, edit draft Sales Orders, request info. |
| ilL Order Approver | `b2b_portal_foundations` | Yes | `sales`, `accounts` + native Sales Order **submit/cancel/amend**: approves portal orders. |
| ilL Engineering | `b2b_portal_foundations` | Yes | `engineering`: drawing requests, deliverables, reapproval tasks, product authoring. |
| ilL Catalog Publisher | `b2b_portal_foundations` | Yes | `catalog`: product authoring, Webflow product/category content, approve/stage/publish. |
| ilL Integration | `b2b_portal_foundations` | Yes | `integration`: publication job and email delivery failures, retries. |
| ilL Support | `portal_staff_permissions.apply_service_permissions` (if missing) | Yes | `support`, `accounts`: Issue queue and portal conversation. |
| ilL Operations | same | Yes | `operations`: read manufacturing drawing holds (no Work Order submit). |
| Accounts Manager / Accounts User / Stock User / Sales User / Sales Manager | ERPNext | Yes | Appear only in a few DocType JSON permissions and report roles (§6.5). Standard ERPNext job roles otherwise govern Quotation/SO/DN/SI/PE/WO/PO. |
| Can View Pricing | **Not created by any code or fixture** | — | Still checked by `app/api/exports.py` (~L115) for priced exports. Existence on site UNKNOWN (G-006). |

Capability helper (OBSERVED `app/portal/staff.py`): a capability is granted only to an **enabled System User** holding one of the listed roles or System Manager. Website users can never hold a staff capability.

No patch assigns any role to any user ("No users are automatically assigned new roles", `docs/B2B_STAFF_OPERATIONS.md`; confirmed in `portal_staff_permissions.py` docstring). Who holds which role on production is **UNKNOWN (G-002)**.

### 7.2 Role × app DocType matrix

Legend: r read · w write · c create · d delete · s submit · x cancel · a amend. Plain letters = DocType JSON permission. `P:` = granted by a patch through `frappe.permissions.add_permission` / `update_permission_property` (lands in Custom DocPerm). Where both exist, `JSON / P:patch` is shown. Child tables are excluded (they inherit their parent's permissions). ilL-Quote-Request also has **permlevel-1** rw for System Manager, ilL Sales Review and ilL Order Approver (not shown).

**Important interpretation rules (OBSERVED in Frappe v16 source):**
1. Once any Custom DocPerm row exists for a DocType, Frappe uses the Custom DocPerm set **instead of** the JSON permissions (`frappe/model/meta.py` ~L641; `add_permission` first copies the JSON rows via `setup_custom_perms`). Every DocType marked `P:` below therefore runs on its Custom DocPerm copy on production, and later edits to that DocType's JSON permissions in the repo will **not** take effect there.
2. The `has_permission` / query hooks (§4.5) further restrict the 15 hooked DocTypes per user (company, project, collaborator scope). The matrix shows the maximum role grant, not what a given dealer can see.
3. The live site may have extra Custom DocPerm rows added in the UI. UNKNOWN (G-001).

| DocType | SysMgr | All | Guest | Cust | WebUser | Dealer | SalesRev | OrdAppr | Eng | CatPub | Integ | Support | Ops | AcctMgr | AcctUser | StockUser |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Email Campaign Benchmark Settings | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Account-Request | r | r |  |  |  |  | r | r |  |  |  | r |  |  |  |  |
| ilL-Attribute-CCT | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Certification | rwcd |  |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Controller Type | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-CRI | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Dimming Protocol | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Endcap Color | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Endcap Style | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Environment Rating | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Feed-Direction | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Finish | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  | r |
| ilL-Attribute-IP Rating | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Joiner Angle | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Joiner System | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Lead Time Class | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Leader Cable | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-LED Package | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Lens Appearance | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Lens Interface Type | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Mounting Method | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Mounting Type | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Output Level | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Output Voltage | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-PCB Finish | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-PCB Mounting | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Power Feed Type | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Pricing Class | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-SDCM | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Attribute-Series | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Configuration-Receipt | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Configurator-Session | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Configured-Fixture | rwcd | r |  |  |  | rwc |  |  |  |  |  |  |  |  |  |  |
| ilL-Configured-Group | r |  |  |  |  | r |  |  |  |  |  |  |  |  |  |  |
| ilL-Configured-LED-Sheet | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Configured-Tape-Neon | rwcd | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Controller-Submittal-Mapping | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Controller-Template | rwcd | r |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Document-Request | rwcd | rwc |  |  |  | rwc |  |  | rw / P:rwc |  |  |  | P:r |  |  |  |
| ilL-Drawing-Review | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Driver-Submittal-Mapping | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Driver-Template | rwcd | r |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Export-Job | rwcd | r |  |  |  | rc |  |  | P:r |  |  |  |  |  |  |  |
| ilL-Extrusion-Kit-Template | rwcd | r |  |  |  | rwc |  |  |  |  |  |  |  |  |  |  |
| ilL-Fixture-Template | rwcd | r |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Item-Literature | rwc |  |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Job-Title-Master | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-LED-Sheet-Submittal-Mapping | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-LED-Sheet-Template | rwcd |  |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Line-Document | r | r |  |  |  | r |  |  |  |  |  |  |  |  |  |  |
| ilL-Neon-Submittal-Mapping | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Order-Change | r |  |  |  |  |  | r | r |  |  |  |  |  |  |  |  |
| ilL-Order-Intake | r |  |  |  |  |  | P:r | P:r |  |  |  |  |  |  |  |  |
| ilL-Portal-Delivery | r |  |  |  |  |  |  |  |  |  | P:r |  |  |  |  |  |
| ilL-Portal-Event | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Portal-Invitation | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Portal-Message | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Portal-Upload | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Portal-User-Settings | rwcd |  |  | rwc | rwc | rwc |  |  |  |  |  |  |  |  |  |  |
| ilL-Product-Publication | r |  |  |  |  |  |  |  |  | r | r |  |  |  |  |  |
| ilL-Project | rwcd |  |  | rwc |  | rwc | P:rwc | P:rwc |  |  |  |  |  |  |  |  |
| ilL-Project-Fixture-Schedule | rwcd | rwc |  |  |  | rwc | P:rwc | P:rwc |  |  |  |  |  |  |  |  |
| ilL-Publish-Job | r |  |  |  |  |  |  |  |  | r | r |  |  |  |  |  |
| ilL-QBO-Settings | rwcd |  |  |  |  |  |  |  |  |  |  |  |  | rw |  |  |
| ilL-QBO-Sync-Log | rwcd |  |  |  |  |  |  |  |  |  |  |  |  | r | r |  |
| ilL-Quote-Offer | r |  |  |  |  |  | r | r |  |  |  |  |  |  |  |  |
| ilL-Quote-Request | rwc |  |  |  |  |  | rw | rw |  |  |  |  |  |  |  |  |
| ilL-Rel-Driver-Eligibility | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Endcap-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Finish Endcap Color | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Kit-Endcap-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Kit-Lens-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Kit-Mounting-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Kit-Profile-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Leader-Cable-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Mounting-Accessory-Map | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Profile Lens | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Rel-Tape Offering | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Request-Type | rwcd | r |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Spec-Accessory | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-Controller | rwcd |  |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-Driver | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-LED Tape | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-LED-Sheet | rwcd |  |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-Lens | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-Profile | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Spec-Submittal-Mapping | rwcd | r |  |  |  |  |  |  | P:rwc | P:rwc |  |  |  |  |  |  |
| ilL-Tape-Neon-Template | rwcd | r |  |  |  |  |  |  | P:rwc | rwc |  |  |  |  |  |  |
| ilL-Webflow-Brand | rwcd |  |  |  |  |  |  |  |  | P:r | P:r |  |  |  |  |  |
| ilL-Webflow-Category | rwcd |  |  |  |  |  |  |  | P:r | P:rwc | P:r |  |  |  |  |  |
| ilL-Webflow-Configurator-Cache | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Webflow-Product | rwcd |  |  |  |  |  |  |  | P:r | rwc | P:r |  |  |  |  |  |
| ilL-Webflow-Session | rwcd |  | rwc |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ilL-Webflow-Settings | rwcd |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

### 7.3 Grants on ERPNext / Frappe DocTypes

| Role | DocType → rights | Source |
|---|---|---|
| Dealer | Sales Order: select, read, **create**, print (no write/submit/cancel/delete). Customer, Contact, Address, Item, Item Group, UOM, Currency: select + read. **Every other flag on these DocTypes is revoked.** | `app/dealer_permissions.py → DEALER_PERMISSION_MATRIX`, applied by `install.py` and patch `setup_dealer_sales_permissions` |
| Dealer (row filter) | Sales Order list/doc limited to own Customer or own-created orders | `dealer_permissions.sales_order_query_conditions` / `sales_order_has_permission` |
| ilL Sales Review | Read/select: Customer, Contact, Address, Company, Currency, UOM, Item, Item Group, Brand, Price List, Item Price, BOM, Warehouse, Account, Cost Center, Payment Terms Template, Terms and Conditions, Sales Taxes and Charges Template, Project. **Quotation**: r w c s x a + print/report. **Sales Order**: r w c + print/report (no submit). ilL-Order-Intake: r. | `portal_staff_permissions.apply_staff_permissions` |
| ilL Order Approver | Same as Sales Review **plus Sales Order submit, cancel, amend**. | same |
| ilL Engineering | Task: r w c. ilL-Document-Request: r w c. ilL-Export-Job: r. Item, UOM, Item Group, Brand: read. All authoring masters (ilL-Spec-*, ilL-Attribute-*, ilL-Rel-*, 5 templates, 5 submittal mappings, ilL-Item-Literature): r w c + import/export (no delete). | `apply_service_permissions` |
| ilL Catalog Publisher | Same authoring masters as Engineering; ilL-Webflow-Product and ilL-Webflow-Category: r w c; ilL-Webflow-Brand: r. | same |
| ilL Support | Issue: r w c + report. | same |
| ilL Operations | ilL-Document-Request: read only. **No Work Order permission.** | same |
| ilL Integration | ilL-Portal-Delivery: r; Webflow Brand/Product/Category: r. **No Email Queue permission** (docs tell them to escalate). | same |

Standard ERPNext role permissions on Quotation, Sales Order, Delivery Note, Sales Invoice, Payment Entry, Work Order, BOM, Purchase Order, Stock Entry etc. are **untouched** by the app and still apply (Sales User/Manager, Stock User/Manager, Manufacturing User/Manager, Purchase User/Manager, Accounts User/Manager). Site state UNKNOWN (G-001, G-002).

---

## 8. n8n workflows (checked into `n8n_workflows/`)

All exports have `active` unset or `false`. Whether each is imported, active and scheduled in n8n Cloud is **UNKNOWN (G-007)**. ERP base URL is hard-coded to `https://illumenatelighting.v.frappe.cloud` except in the product publication worker (configurable).

| Workflow (file) | Trigger | Steps | Destination / ERP endpoints | Credentials (names/types only) |
|---|---|---|---|---|
| Webflow Form → Frappe CRM Lead (`webflow_lead_form.json`) | Webhook POST `/webflow-lead-form` | Check payload → transform → require fields → create lead → respond success/error. Slack notify and auto-reply email nodes **disabled**. | `webflow_leads.create_lead_from_webflow` (brand `illumenate`) | HTTP Header Auth "ERPNext API Key" (`token key:secret`); Slack API, SMTP (disabled nodes) |
| Webflow Form (206 Lighting) → CRM Lead (`webflow_lead_form_206.json`) | Webhook POST `/webflow-lead-form-206` | Same, brand `lighting_206` | same | same |
| ERPNext → Webflow Attributes Sync (`webflow_attribute_sync.json`) | Every 6 h + manual | Set brand → list pending attribute types → per type fetch Webflow collection fields → fetch attributes → create/update Webflow items → mark synced / mark error | `webflow_attributes.get_all_attributes_for_sync`, `.get_webflow_attributes`, `.mark_attribute_synced`, `.mark_attribute_error`; `webflow_brand.get_brand_config`; Webflow API v2 collections/items | ERPNext header auth; Webflow header auth (per brand) |
| ERPNext → Webflow Category Sync (`webflow_category_sync.json`) | Every 6 h + manual | Set brand → brand config → fetch categories → create/update → mark synced (no error-mark branch) | `webflow_export.get_webflow_categories`, `.mark_category_synced`; `webflow_brand.get_brand_config` | ERPNext header auth / `erpNextApi`; Webflow header auth |
| ERPNext → Webflow Product-Attribute Reference Sync (`webflow_product_attribute_filter_sync.json`) | Every 6 h + manual | Brand config → fetch products with attribute refs → PATCH product filter fields → mark synced | `webflow_attributes.get_product_attribute_references`, `.mark_filter_synced`; `webflow_brand.get_brand_config` | same |
| ilL Product Publication v2 (one brand) (`webflow_product_sync.json`, generated by `tools/build_publication_workflow.py` from `n8n_workflows/lib/product_projection.js`) | **Manual only**, inactive | Claim job → find remote item by slug → create/update staged item → optional publish live, or unpublish + archive for retirement → acknowledge success/failure → loop (≤1,000 jobs/run) | `publication.claim`, `publication.acknowledge`; Webflow API v2 items, `/live`, `/publish` | n8n variables `ILL_ERP_BASE_URL`, `ILL_WEBFLOW_BRAND`; ERP integration-user credential; brand Webflow credential |
| QuickBooks Payment → ERPNext Payment Entry (`quickbooks_payment_sync.json`) | Webhook POST `/quickbooks-payment-events` (Intuit) | Verify `intuit-signature` → split entities → delete/void branch or fetch Payment from QBO → build payload → HMAC-sign → POST to ERP → success no-op / alert (**alert node is a NoOp placeholder**) | `qbo_sync.receive_payment_event`; QBO API `GET /v3/company/{realm}/payment/{id}` | n8n variables `QBO_WEBHOOK_SECRET`, `INTUIT_VERIFIER_TOKEN`; QuickBooks OAuth2 credential |

**Known to exist outside the repo (per docs), not inventoried:** ERPNext → QBO Customer/Sales Invoice push ("on Sales Invoice submit webhook", QBO plan §0) and the Postmark campaign workflow behind site config `n8n_campaign_webhook_url` (recovery plan §4.1; its ERP-side scheduler entry was removed).

---

## 9. External systems and credential types

Names and types only. No secret values were read or printed.

| System | Direction | Credential / secret (type, where stored) | Evidence |
|---|---|---|---|
| Frappe Cloud (hosting, bench group "ilLumenate Production - V16") | — | Dashboard account; site config keys (encryption key etc. server-side) | Recovery plan |
| Webflow — brand `illumenate` and `lighting_206` | ERP → Webflow via n8n; Webflow pages → ERP public APIs | Webflow API token per brand, stored as n8n credential (name recorded in `ilL-Webflow-Brand.n8n_webflow_credential_name`) | `docs/MULTI_BRAND_WEBFLOW.md`; brand DocType |
| n8n Cloud | Both | ERPNext API key/secret of an integration user (HTTP Header Auth); n8n variables above | n8n exports; `docs/ERPNEXT_SETUP_GUIDE.md` Part 7 (suggests System Manager for the API user — see G-008) |
| QuickBooks Online (Intuit) | QBO → ERP payments; ERP → QBO invoices/customers (outside repo) | Intuit OAuth2 (n8n); Intuit Webhooks Verifier Token (n8n); shared HMAC secret (`ilL-QBO-Settings.webhook_secret` Password field or site config `qbo_webhook_secret`) | `app/api/qbo_sync.py`; QBO plan |
| Frappe CRM (same site) | Lead intake | — | §10 |
| Email (SMTP / outgoing Email Account) | ERP → customers | Frappe Email Account (site) | `portal/outbox.py`, `portal/email_queue.py` |
| Postmark (via n8n) | ERP → n8n → Postmark | Site config `n8n_campaign_webhook_url`; "Postmark Campaign" DocType read by `app/email_campaign_scheduler.py` is **not defined in this repo** | `email_campaign_scheduler.py`; recovery plan §4.1 |
| Slack | n8n → Slack | Slack API credential (nodes disabled) | lead-form exports |
| Google Chrome-for-Testing (storage.googleapis.com) | ERP downloads pinned headless Chromium for spec-sheet rendering, SHA-256 checked | none | `app/api/spec_sheets/render.py → PINNED_CHROMIUM` |
| Vercel (`configurator-ui-olive.vercel.app`) | Browser → ERP (CORS) | none (session cookie) | `app/utils.py → ALLOWED_ORIGINS`; `tools/configurator_ui` |
| GitHub Actions | CI | Repo secrets (not inspected) | `.github/workflows/*.yml` |

---

## 10. Frappe CRM usage

| Topic | Finding | Label |
|---|---|---|
| Installed? | Yes, CRM 1.85.1 as a separate app on production. | OBSERVED (doc) |
| Source in repo? | No. Checked upstream at the production commit. | OBSERVED |
| App touch points | Creates **CRM Lead** only (`webflow_leads.create_lead_from_webflow`, status `New`, `source` = brand label or "Webflow"); adds 8 lead custom fields; converts `job_title` to a Link to ilL-Job-Title-Master; Email Campaign Activity Summary report reads CRM Lead. The app never reads or writes **CRM Deal**. | OBSERVED |
| Lead statuses (CRM defaults) | New (Open), Contacted, Nurture (Ongoing), Qualified, Converted (Won), Unqualified, Junk (Lost). The site may have changed these. | OBSERVED upstream `crm/install.py → add_default_lead_statuses`; site UNKNOWN |
| Deal statuses (CRM defaults) | Qualification (Open, 10%), Demo/Making (25%), Proposal/Quotation (50%), Negotiation (70%), Ready to Close (90%), Won (100%), Lost (0%). | OBSERVED upstream `crm/install.py → add_default_deal_statuses`; site UNKNOWN |
| Deal → Customer | Stock CRM: if **ERPNext CRM Settings** is enabled with "create customer on status change", reaching the configured deal status creates an ERPNext Customer (`create_customer_in_erpnext`). A Sales Order made from a CRM-deal Quotation with no customer also triggers customer creation (`create_customer_on_sales_order`). | OBSERVED upstream `crm/fcrm/doctype/erpnext_crm_settings/erpnext_crm_settings.py`; site settings UNKNOWN (G-003) |
| Deal → Quotation | Stock ERPNext Quotation carries a `crm_deal` field used by CRM; how staff create it (from CRM UI or Desk) is not in this repo. | OBSERVED upstream; practice UNKNOWN (G-003) |
| Relationship to the dealer portal | Separate funnel: dealers enter through `/portal/request-dealer-access` / ilL-Account-Request and are linked to a Customer through Contact links; no code connects a CRM Lead/Deal to a portal account or ilL-Project. | OBSERVED absence; process link UNKNOWN (G-003) |
| Assignment rules, SLAs, lead routing | None in repo. | UNKNOWN (G-003) |

---

## 11. Conflicts between docs and code (code wins)

| # | Doc says | Code says (OBSERVED) | Impact |
|---|---|---|---|
| C1 | `DEALER_ROLE.md`: dealers "Create Sales Orders", create Customers/Contacts, are set up in Desk. | Dealer has **no Desk access**; Sales Order create/read/print only; portal orders become a draft SO + ilL-Order-Intake that only ilL Order Approver / System Manager can submit (`order_review.before_submit`). Customer/Contact creation goes through whitelisted portal services. | DEALER_ROLE.md must not be used as a role guide. |
| C2 | `MVP_CONSTRAINTS.md` (Jan 2026): no CRM integration, no webhooks, no payments, export files public (`is_private = 0`), pricing via "Can View Pricing" role, MSRP only. | CRM lead intake, QBO payment webhook and publication callbacks exist; exports and packets are saved private (`api/exports.py → _save_file_ignore_permissions` forces `is_private=1`); "Can View Pricing" is still checked but never created; dealer tier pricing exists in `pricing_utils.py` (detail in Phase 1). | Treat MVP_CONSTRAINTS as historical. |
| C3 | `DEMO_SCRIPT.md` / `QA_CHECKLIST.md` §4: "Create Sales Order" sets schedule ORDERED; Work Orders created by calling the generator by hand. | Conversion yields ORDER_REQUESTED + draft SO; ORDERED on SO submit; Work Orders auto-generated on SO submit (`manufacturing_generator.on_sales_order_submit`). To confirm in Phase 1. | Scripts outdated. |
| C4 | `WEBFLOW_PORTAL_INTEGRATION_GUIDE.md`: `get_user_context` returns an API key/secret stored in `sessionStorage`; CORS in `hooks.py` for 2 origins. | `get_user_context` explicitly returns **no** keys; CORS is in `app/utils.py` for 10 origins, plus `get_user_context` reflects any `*.webflow.io` / `*.vercel.app`. | Guide is wrong on security model. |
| C5 | `WEBFLOW_INTEGRATION_GUIDE.md` Part 7: products sync every 6 hours via scheduled n8n. | Product publication workflow v2 is **manual-trigger only** and inactive; runbook says schedule only after acceptance tests. Old product endpoints (`get_webflow_products`, `mark_webflow_synced`) have no in-repo caller. | Product publication cadence UNKNOWN (G-007). |
| C6 | `hooks.py` comment: Product Catalog "System Manager only". | Controller: "Dealers and internal users", gated by `portal.access.require_catalog_access`; owner decision #6 (`DEALER_PORTAL_ASSESSMENT…` §14) made it dealer-facing. | Comment stale. |
| C7 | QBO plan §1–§4 endpoint path `illumenate_lighting.api.qbo_sync…`. | Actual `illumenate_lighting.illumenate_lighting.api.qbo_sync.receive_payment_event` (plan §6 and n8n export use the right path). | Minor. |
| C8 | `hooks.py` fixtures list Dealer role, Document Request workflow, request types, job titles, custom fields, seed products. | Those files are in the module-level folder Frappe does not load; two names don't match. | Seed/config presence on site UNKNOWN (G-004). |
| C9 | Recovery plan §7.3 (dealer → customer resolution fix), §7.4 (list-typed sync params), §7.6 (skip lineage on plain rows), §7.7 (filter Custom Field fixture), §7.8 (dead `/portal/configure-kit` route). | Not implemented at this commit (OBSERVED in `ill_project._get_user_customer`, `webflow_export.trigger_sync(product_slugs: list…)`, `commercial_lineage.validate`, `hooks.py` fixtures and routes). | Carry to known-issues (Phase 4). |
| C10 | `api/README.md`: driver plan "placeholder", pricing "tier_unit = msrp", item codes placeholders. | Driver planner, dealer pricing and configured Item codes are implemented (`power_planner.py`, `pricing_utils.py`, recent commits "Use configured part numbers as Item codes"). | README historical. |
| C11 | `docs/job_title_master.md`: initial 13 titles "included in the initial fixture data". | Fixture not loaded (C8). | Titles may be missing on a fresh site. |

---

## 12. Open questions from Phase 0 (seed of the gaps register)

| ID | Question | Why it matters | Suggested owner |
|---|---|---|---|
| G-001 | Export site-level Custom DocPerm, Custom Field, Property Setter, Server Script, Client Script, Notification, Webhook, Assignment Rule and Workflow records. | The permission matrix and automation catalog are only as complete as the site's own customizations. | Systems/Dev |
| G-002 | Which named users hold which roles today (System Manager, Dealer, ilL * job roles, ERPNext job roles)? What is the org chart? | Role guides and segregation-of-duties analysis depend on it; no patch assigns roles. | Leadership + Systems |
| G-003 | How is Frappe CRM used: lead/deal statuses in use, assignment rules, ERPNext CRM Settings (auto-create Customer?), who converts a Deal to a Quotation/Customer, and how CRM leads become portal dealers? | Pre-sale SOPs. | Sales + Marketing |
| G-004 | Do these exist on production: `ilL Document Request Workflow` (active?), ilL-Request-Type records, 13 Job Title Master records, print formats "ilL Work Order Traveler" and "ilL Fixture Schedule", Snowfield seed data? | They are shipped only in the unloaded fixtures folder. | Systems/Dev |
| G-005 | Do CRM Lead fields `webflow_submitted_at` … `webflow_products_interested`, Item `ill_build_id`, and Work Order `ill_configured_fixture` / test/serial fields exist on production? | Code writes them; absence may silently drop data. | Systems/Dev |
| G-006 | Does a "Can View Pricing" role exist, and who should see priced exports? | Priced PDF/CSV export gate. | Sales |
| G-007 | Which n8n workflows are active, on what schedule, with which credentials; export the ERPNext→QBO invoice/customer workflow and the Postmark campaign workflow. | Integration SOPs and accounting system-of-record. | Systems/Dev |
| G-008 | Which ERP user and roles do n8n's API credentials use (setup guide suggests System Manager)? | Least privilege; audit trail of integration writes. | Systems/Dev |
| G-009 | System of record for invoices, payments, GL and tax: ERPNext, QBO or both? Who creates invoices, where are payments first recorded, which system is reconciled to the bank? | Accounting SOPs; AR number cards. | Accounting |
| G-010 | Which "no in-repo caller" endpoints are used by the live Webflow sites or n8n, and which are dead? | Dead-code cleanup and API change safety. | Systems/Dev + Marketing |
| G-011 | Is Guest create/write on ilL-Webflow-Session intentional, and has REST access been tested? | Possible unauthenticated data tampering. | Systems/Dev |
| G-012 | Should `get_user_context` reflect credentialed CORS to any `*.webflow.io` / `*.vercel.app` origin? | Any site on those domains can read a logged-in user's name and customer. | Systems/Dev |
| G-013 | Is "Sales Invoiced MTD" meant to be month-to-date? | Card has no date filter in its definition. | Accounting |
| G-014 | Is "Postmark Campaign" (and the CRM Lead email-activity child table) a site-only custom DocType? Are scheduled campaigns supposed to run (scheduler entry removed Aug 12)? | Marketing email SOP. | Marketing |
| G-015 | Is the staging site `stagingillumenatelighting.v.frappe.cloud` live and on its own bench group? | Release SOP. | Systems/Dev |
| G-016 | Is `tools/configurator_ui` deployed at `configurator-ui-olive.vercel.app`, and who owns it? | Marketing/integration ownership. | Marketing + Dev |
