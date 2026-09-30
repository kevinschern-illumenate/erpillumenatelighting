# SOP & Walkthrough Discovery Prompt

Hand everything below the line to a chatbot or coding agent that has access to this repository (ideally also to a Frappe Cloud bench console or exported site data). Run it in phases: the prompt tells the agent to stop after each phase so you can review before it continues.

---

## PROMPT START

# Role

You are a senior business-systems analyst and technical writer. You are documenting the real, as-built operating model of **ilLumenate Lighting**, a lighting manufacturer and B2B seller. Its operating stack is **Frappe v16, ERPNext, Frappe CRM, and a custom Frappe app (`illumenate_lighting`)**, plus external integrations. Your output becomes the company's starting set of process documentation, role guides and SOPs, so accuracy matters more than volume.

# Goal

Investigate the systems and code, then produce:

1. A **company-wide end-to-end process breakdown** covering Pre-Sale, Sale and Post-Sale.
2. **Role walkthroughs and how-to guides** for each role.
3. **SOPs per department:** Sales, Marketing, Product Development, Operations, Accounting, Systems Integration & Development.
4. A **gaps and decisions register** listing everything the code and data cannot answer, so leadership can fill it in.

# Ground rules (strict)

1. **Evidence over assumption.** Every non-trivial claim about how the system behaves must cite its source, such as a file path with function or doctype name, a doc in `docs/`, or a screenshot or export the user supplied. Format: `[src: illumenate_lighting/hooks.py → doc_events["Sales Order"]]`.
2. **Label every statement** as one of:
   - **OBSERVED**: read directly in code, config, fixtures or docs.
   - **INFERRED**: a reasonable conclusion from observed facts. State the reasoning.
   - **UNKNOWN / ASK**: cannot be determined from what you can see. Never fill these in with plausible-sounding process. Add them to the gaps register.
3. **Separate what the system enforces from what people are expected to do.** Code enforces validations, permissions, workflow states and automatic side effects. Anything else (who reviews what, SLAs, pricing approval habits) is a policy that you must mark UNKNOWN unless a doc states it.
4. **Standard vs custom.** For each step, say whether it uses stock Frappe/ERPNext/CRM behavior or custom code, so a reader knows where to look when something breaks.
5. **Do not modify code, data or configuration.** This is read-only investigation plus writing documentation files. Do not run destructive commands or hit production APIs.
6. **Do not invent UI labels, menu paths, field names or button names.** Take them from doctype JSON, JS files, templates and workspace JSON. If a label cannot be verified, describe it generically and flag it.
7. **Frappe v16 specifics.** Where you rely on standard Frappe or ERPNext behavior (naming series, workflow engine, permissions model, print formats, scheduler, Frappe CRM lead-to-deal conversion), check the installed version's behavior if you have access to it. Do not rely on memory of older versions.
8. If you cannot access something (live site, CRM app source, QuickBooks, Webflow, n8n instance), say so at the start and list what you would need. Do not silently substitute guesses.

# What is already known about this codebase (verify each item, do not trust blindly)

Starting points from a quick survey. Treat them as leads, not facts.

**Repo layout**
- Custom Frappe app: `illumenate_lighting/` with module `illumenate_lighting/illumenate_lighting/`. Key files: `hooks.py` (doc events, permissions, portal routes, fixtures, scheduler), `api/`, `doctype/`, `portal/`, `page/`, `report/`, `workspace/`, `print_format/`, `fixtures/`, `patches/`, `templates/pages/` (portal web pages).
- `docs/` holds about 40 existing docs. **Read all of them first**, especially: `ERPNEXT_SETUP_GUIDE.md`, `B2B_STAFF_OPERATIONS.md`, `B2B_QUOTE_OPERATIONS.md`, `B2B_PUBLICATION_RUNBOOK.md`, `DEALER_ROLE.md`, `B2B_PORTAL_IMPLEMENTATION_STATUS.md`, `B2B_PORTAL_PRODUCT_AUDIT_AND_ROADMAP.md`, `QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md`, `MULTI_BRAND_WEBFLOW.md`, `WEBFLOW_*_GUIDE.md`, `QA_CHECKLIST.md`, `MVP_CONSTRAINTS.md`, `DEMO_SCRIPT.md`, `job_title_master.md`, `DEPLOYMENT_RECOVERY_PLAN_*`, `FRAPPE_CLOUD_BACKUP_REPAIR_*`. Note where docs conflict with code and prefer the code, flagging the conflict.
- Also read `api/README.md`, `api/IMPLEMENTATION_NOTES.md`, `api/WEBFLOW_API_DOCUMENTATION.md`, `tools/fixture_builder/README.md`, and `tools/fixture_builder/CATALOG.md`.

**Product and configuration domain (Product Development)**
- Templates: `ilL-Fixture-Template`, `ilL-Tape-Neon-Template`, `ilL-LED-Sheet-Template`, `ilL-Driver-Template`, `ilL-Controller-Template`, `ilL-Extrusion-Kit-Template`.
- Specs (`ilL-Spec-*`), attributes (`ilL-Attribute-*`: CCT, CRI, finish, IP rating and so on), relationship maps (`ilL-Rel-*`) and child tables (`ilL-Child-*`).
- Configurators: fixture, tape/neon, LED sheet, extrusion kit, driver/controller, fixture group, and quote-order. See `api/configurator_engine.py`, `configured_product_builder.py`, `power_planner.py`, `linear_build.py`, `tape_neon_*`, `led_sheet_*`.
- Authoring and publication: `authoring_contract.py`, `product_readiness.py`, `publication.py`, `ilL-Product-Publication`, `ilL-Publish-Job`, `ilL-Webflow-Product`, and the `tools/fixture_builder`, `tools/yaml_builder_ui` and `tools/configurator_ui` tooling.
- Output artifacts: spec sheets (`spec_sheet_generator.py`, `spec_sheets/`), spec submittals (`spec_submittal.py`, `ilL-*-Submittal-Mapping`), drawings, BOMs, manufacturing output.

**Pre-sale and sale**
- Lead capture via Webflow forms through n8n into the CRM Lead (`webflow_lead_form*.json`, `webflow_leads.py`, `ilL-Job-Title-Master`, custom fields fixture).
- Dealer and customer B2B portal at `/portal`: account requests (`ilL-Account-Request`, `ilL-Portal-Invitation`), projects (`ilL-Project`), fixture schedules (`ilL-Project-Fixture-Schedule` and lines), configurator sessions and receipts, quote requests (`ilL-Quote-Request`), quote offers (`ilL-Quote-Offer`), orders (`ilL-Order-Intake`, `ilL-Order-Decision`, `ilL-Order-Change`), drawings (`ilL-Drawing-Review`), document requests (`ilL-Document-Request`, workflow "ILL Document Request Workflow", `ilL-Request-Type`), support (Issue), messages (`ilL-Portal-Message`), and uploads.
- Desk-side configuration inside Quotation and Sales Order (`desk_configurator.py`, `public/js/quotation.js`, `sales_order.js`). Quotation submit creates a portal offer (`portal/offers.py`). Sales Order validation and review (`portal/order_review.py`).
- Roles: `Dealer` plus stock roles. Also `dealer_permissions.py`, `portal_staff_permissions.py`, and the permission query conditions in `hooks.py`.

**Post-sale**
- Sales Order submit triggers `manufacturing_generator.on_sales_order_submit` (Work Orders and BOMs?), schedule linkage, and drawing-impact checks. Work Order `before_submit` triggers drawing review gating.
- Delivery Note leads to notifications. `commercial_lineage.py`. Purchase Orders (`purchase_order.py`). Stock and reels (`tape_reels.py`, `test_bundle_stock.py`). Reconciliation (`reconciliation.py`). Exports (`ilL-Export-Job`, `exports.py`).
- Accounting: Sales Invoice, QuickBooks Online sync (`qbo_sync.py`, `ilL-QBO-Settings`, `ilL-QBO-Sync-Log`, `n8n_workflows/quickbooks_payment_sync.json`). **Determine which system is the system of record for invoicing, payments and the GL. Do not assume.**
- Reports: sales partner invoice report, sales team commissions, email campaign activity summary. Commission logic lives in the reports and in sales-partner data.

**Marketing**
- Email campaign scheduler (`email_campaign_scheduler.py`, `email_campaign_benchmark_settings`), Webflow site sync (products, attributes, categories, multi-brand), lead form flow, and the public spec sheet embed script.

**Integrations**
- Webflow (multi-brand), n8n workflows in `n8n_workflows/`, QuickBooks Online, Frappe Cloud hosting, backups and deployment (see the recovery docs). Trace every scheduler event, whitelisted API endpoint, webhook and background job.

# Method

Work in the phases below. **At the end of each phase, write its deliverable to `docs/sop/` (create it), summarize what you found in under 15 lines, list the new open questions, and STOP and wait for my go-ahead before starting the next phase.**

## Phase 0: Access check and inventory
- State what you can and cannot see (repo only? live site? CRM source? exports?).
- Read all files in `docs/` and the READMEs listed above.
- Build an **inventory** and write it to `docs/sop/00_inventory.md`:
  - every custom DocType with module, purpose in one line, whether it is customer-facing (portal), staff-facing (desk), or config/master data;
  - every whitelisted API endpoint and which UI or integration calls it;
  - every `hooks.py` entry: doc_events, scheduler_events, permission hooks, fixtures, routes, redirects, class overrides;
  - every Workflow, Custom Field, Property Setter, Print Format, Report, Page and Workspace shortcut;
  - every role referenced in code or fixtures, and the permission each grants (build a role × doctype matrix from the DocType JSON `permissions`);
  - every n8n workflow with its trigger, steps and destination;
  - every external system and credential type it needs (names only; never print secrets).
- If Frappe CRM is installed as a separate app, inventory its use: lead and deal statuses, custom fields, assignment rules and how a CRM deal becomes a Quotation or Sales Order. If its source is not in the repo, say so and list what you need.

## Phase 1: Company-wide lifecycle map
Write `docs/sop/01_company_lifecycle.md`. Produce a step-by-step end-to-end flow from first touch to final payment and support, split into three stages:

**Pre-sale**
- Visitor, lead capture, lead qualification, dealer/customer account request, invitation and approval, project creation, configurator use, fixture schedule building, spec sheet and submittal generation, quote request, staff review, quote offer issue.

**Sale**
- Quote acceptance, order intake, order review and decision, Sales Order creation and submit, drawing review and approval gating, order changes, deposits and terms, production release.

**Post-sale**
- Manufacturing (Work Orders, BOMs, tape reels, kitting), purchasing, shipping (Delivery Note), invoicing (Sales Invoice, QuickBooks), payment reconciliation, commissions, warranty, support tickets, document requests, RMAs or returns if any.

For each step provide: trigger, actor (role), system and screen or route, inputs, outputs, records created or changed, automatic side effects (notifications, status changes, integrations), validations and blocking rules, and the exact custom code or config responsible. Add:
- a **state-machine table** for each major record (Project, Fixture Schedule, Quote Request, Quote Offer, Order Intake, Sales Order, Drawing Review, Document Request, Work Order): every status, allowed transitions, who can trigger them, and what enforces them;
- **Mermaid diagrams**: one master swimlane and one per stage;
- a **data lineage diagram**: Lead to Project to Schedule to Configured Fixture to Quote Request to Offer/Quotation to Order Intake to Sales Order to Work Order to Delivery Note to Sales Invoice to QBO;
- a **handoff table** listing every point where work moves between departments and how the receiving team finds out.

## Phase 2: Role walkthroughs
Write one file per role to `docs/sop/roles/`. Determine the role list from the code, fixtures and docs (at minimum: Dealer/external customer, Sales rep, Sales manager, Marketing, Product/Engineering author, Operations/production, Purchasing/inventory, Accounting/AR, System Manager/Admin, Integration developer). Reconcile what the code implies with what I tell you the org chart is, and flag mismatches.

Each role guide contains:
- role purpose and the permissions it actually has (from the permission matrix);
- **"A day in the life"**: the recurring tasks in order;
- **click-by-click walkthroughs** for their top tasks, each with prerequisites, navigation path, field-by-field guidance (required fields, what each choice does downstream), expected result, and common errors with fixes. Use only verified labels;
- dashboards, reports, list views and number cards they should live in;
- what they are **not** allowed or expected to do, and who to escalate to;
- a glossary of the terms they will meet (CCT, CRI, SDCM, IP rating, leader cable, joiner, endcap, feed direction, run, segment, group, lead time class and so on), defined in plain language.

## Phase 3: Department SOPs
Write to `docs/sop/departments/`, one file per department: **Sales, Marketing, Product Development, Operations, Accounting, Systems Integration & Development.** Each SOP follows this template:

```
SOP-<DEPT>-<NNN>: <Title>
Owner: <role>  |  Version: 0.1 DRAFT  |  Last verified against code: <date/commit>
Purpose / Scope / Out of scope
Roles & responsibilities (RACI)
Systems & records involved
Prerequisites & access
Procedure (numbered steps; each with actor, action, system location, expected result)
Decision points & approval rules (mark POLICY-UNKNOWN where not enforced by code)
Exceptions & error handling
Controls / audit trail (what the system logs; what a reviewer should check)
KPIs & reports
Related SOPs / docs / code references
Open questions
```

Minimum SOP coverage (add more if the code shows more):
- **Sales:** lead intake and qualification; dealer account approval; project and schedule support; quote-request review; issuing and revising quote offers; discounts and pricing classes; converting to order; order changes; commissions and sales-partner handling.
- **Marketing:** Webflow content and product publication; attribute and category sync; lead form to CRM handling; email campaigns and scheduling; multi-brand management; spec-sheet distribution.
- **Product Development:** adding a series/template, spec and attribute records, compatibility and relationship maps, pricing setup, readiness checks and publication gating, seed and CSV import via `fixture_builder` and the authoring validators, spec-sheet and submittal template maintenance, publish and rollback.
- **Operations:** order review, drawing review, Work Order and BOM generation, tape reel and stock handling, purchasing, kitting and shipping, delivery notifications, document requests, support ticket handling, exports.
- **Accounting:** quote to invoice, invoice and payment via QBO sync, sync-log monitoring and error resolution, reconciliation, commissions payout, period-end, tax, and terms. Flag every control gap you find, such as a manual step with no system check.
- **Systems Integration & Development:** environment map (Frappe Cloud sites and benches), deploy and migrate procedure, patches, fixtures export/import, backups and restore (use the repair and recovery docs), n8n workflow management, Webflow/QBO credentials rotation, monitoring and error logs, testing (`tests/`, `test_*.py`, `QA_CHECKLIST.md`), release checklist, hotspot files that need extra care, permissions change process, and onboarding a new developer.

## Phase 4: Cross-cutting and gaps
- `docs/sop/90_permissions_and_segregation_of_duties.md`: who can do what, and conflicts (for example one person who can create, approve and pay).
- `docs/sop/91_notifications_and_automation_catalog.md`: every email, notification, scheduler job, background job and webhook, with its trigger and audience.
- `docs/sop/92_reports_and_kpis.md`: reports and dashboards that exist, plus recommended KPIs per department that the data could support.
- `docs/sop/93_known_issues_and_risks.md`: bugs, dead code, TODO/FIXME markers, incomplete features versus what docs promise, and the risky hotspot files (`hooks.py`, `api/portal.py`, `tape_neon_configurator.py`, `led_sheet_configurator.py`, `spec_submittal.py`, `quote_from_schedule.py`, `ill_project_fixture_schedule.js`).
- `docs/sop/99_gaps_and_decisions.md`: **a table of every UNKNOWN / ASK** with columns: ID, question, why it matters, which SOP it blocks, suggested owner, and a suggested default if leadership has no preference. Group by department.
- `docs/sop/README.md`: index, reading order per role, doc-maintenance guidance (how and when to re-verify against code), and a versioning and ownership convention.

# Output requirements

- Markdown files, with Mermaid for diagrams. Use tables for state machines, permission matrices and field guidance.
- Keep the plain-language tone of the role guides suitable for non-technical staff, and put technical detail in clearly marked "Under the hood" boxes.
- Every file starts with a header: purpose, audience, scope, date, commit hash inspected, and the confidence level of the document.
- Do not pad. If something is not there, say "not implemented" or "unknown", not filler.
- At the end of every phase, report: what you verified, what you inferred, what you could not determine, and the questions you need answered. Then stop.

# Start now

Begin with Phase 0. First tell me exactly what access you have, then proceed.

## PROMPT END
