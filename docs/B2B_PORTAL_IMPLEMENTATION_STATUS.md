# B2B portal implementation status

Recovery assessment: September 25, 2026. Baseline: `845979669b3760fa49a80dd7000892a3a327838e`.

Scope: [original S0-S9 plan](B2B_PORTAL_TECHNICAL_IMPLEMENTATION_PLAN.md), including S2A/S4A/S8A, and [independent grouping add-on](CONFIGURATOR_GROUPING_ALIGNMENT_PLAN.md). This register replaces stale incremental crash-recovery checkpoints. Application changes survived the interruption; the remaining local implementation and regression work described below has been completed. The release is **not certified**: installed-site engineering, browser, migration, integration and pilot acceptance require the owner's Frappe Cloud deployment.

No commit, push, deployment, production migration, live email or Webflow mutation was performed. Pre-existing AGENTS, .claude, .codex and Repowise changes were preserved.

## Binding owner decisions

- Implement all phases without approval pauses; test locally now, owner deploys to Cloud.
- Drawing approval holds manufacturing release only, not Sales Order approval.
- PDF/JPEG/PNG uploads, 20 MiB each, ten files per intake; optional PO file; ERP quotation validity/terms; explicit staff live publication.
- Reference templates: `ILL-SH01-SW`, `led-hd-sw`, `non-pnc-sw`, `Snowfield Static White LED Sheet`.
- Sheet feeds follow associated drivers' usable total/per-output loading. Tunable White uses full panel wattage, never averaged channel demand.
- Tape reel choices represent continuous tape from bulk stock, not separately stocked reel Items or cut assemblies.
- Independent groups share family/spec/power policy; quantity repeats the entire group. Individual and jumper-connected configurations remain supported.
- Linear cable pricing retains the prior template price basis pending a different owner policy. No numerical engineering approval was invented.

## Completed local implementation

Each row is implemented in source and has applicable local checks. The final column names acceptance that local framework doubles cannot establish.

| Scope | Implemented | Installed-site acceptance still required |
|---|---|---|
| S0 baseline/harness | Operational inventory; private historical record/version/hook/asset/permission checkpoints; isolated 14-actor fixtures; desktop/tablet/mobile browser suite; local CI | Actual installed versions, overrides, engineering cases and performance baseline |
| S1 privacy/receipts | Password/account actions; private verified upload/finalization/replacement; native File guard; historical public-file inventory and checksum-guarded private-copy rehearsal; unpriced quote receipt; authorized order retry | Native downloads, legacy reference/CDN retirement, fresh/upgraded schema |
| S2 catalog/accounts | Shared product projection, certifications/documents/options, search/filter/paging/error states; active-route guards; shared shell; company contacts/addresses/profile/invitations/member disabling; Add Line foundation | Real company/collaborator matrix, invitation delivery, accessibility and mobile layout |
| S2A authoring/publication | Family/dependency/channel readiness; template preflight/authoring permissions; CSV/generator parity; immutable approved/staged/live revisions, leases/retries/retirement; inactive n8n worker; read-only staged/live CMS reconciliation with asset hashes | Real masters, CMS field types, credentials, installed n8n and remote audit |
| S3 configuration | Scoped lifecycle/IDs/labels, stale-response fencing and teardown; power controls; four-family preview/save/reopen; Portal/Desk atomic retry receipts; metadata-preserving Add Line; public Sheet choices/PDF/handoff; continuous-stock reels; compatibility adapters | Actual Desk hit testing/open-close/reopen, assets, unsaved parent, DB races and external legacy callers |
| S4 physical builds | Versioned immutable full-hash builds/Items/BOMs; actual-run total/per-output planner; explicit independent outputs; cable cuts/UOMs/split-run feeds; whole Sheet bundles; current pricing of pinned components; company/ilL-Stores stock scope; family/cohort rollout controls | Signed numerical references, installed ERP reservations/planning, actual prices/UOMs/eligible drivers |
| S4A documents | Stable private line documents, duplicate/version copies and replacement; required PDF mapping checks; frozen engineering values; asynchronous byte-checked packet manifests/retries/fencing/index/progress; incomplete drafts vs issued history; Item-literature registry | Real forms/fonts/layout/Cloud renderer, mixed packets and worker failures |
| S5 groups | Canonical independent members/shared specifications; one parent Item/quantity-one flat BOM; shared power; member editor/reopen/labels; Portal/Desk/conversion/stock/export/PDF/manufacturing dispatch; server opt-in flag | All-family one-member parity, L1 reference and quantity two, real rollback/races/manufacturing |
| S6 commercial | Frozen quote intake/offer/PDF; response/expiry guards; direct PO with owned address/contact/instructions/exclusions; buyer acknowledgment; staff confirmation/approval; native SO guard; amendments/replacement; standard-SKU ordering; Quote -> SO -> DN -> SI lineage and prints | ERP pricing/taxes/address/UOM semantics, native submit permissions, acknowledgment and partial fulfillment |
| S7 drawings | Private requests/replies/internal notes; assignee/SLA/Task; immutable revisions and reviewer/file/build decisions; impact/reapproval Tasks; actual order-vs-schedule check at Work Order release | Ordinary-role review loop, physical order edits, waiver restriction and Work Order submission |
| S8 service/notifications | Paginated orders/shipments/returns/invoice/date states; change/cancel/reorder/replacement; private linked support reply/resolve/reopen; durable recipient/event/delivery ledger and send-time preference/access check | Scheduler/native Email Queue, SMTP sink, role/recipient matrix |
| S8A staff Desk | Additive job permissions; template/mapping/literature shortcuts; preserved Workspace merge/backups; permission-aware counts/drilldowns/queues; departmental runbooks | Fresh/upgraded ordinary-role walkthroughs, count agreement, owners and absence coverage |
| S9 release tooling | Cloud acceptance pack, checkpoints/comparison, fixture/browser runner, synthetic PDF evidence, CI, remote audit and rollout/rollback instructions | Migration/restore, mandatory installed scenarios, pilot, timing targets and signoffs |

## Recovery closeout corrections

- Shipment and invoice rows retain exact source-row notes, designation, room, engineering request, configured group/build and BOM. Fresh sites receive missing note fields while existing definitions are preserved. Added optional unpriced `ilL Delivery Note`; site print defaults are unchanged.
- Offer/review snapshots include group identity and line presentation. Disabled buyers cannot supply current acknowledgment evidence. Staff-confirmed dates update native order/item dates; amendment clears prior acknowledgment/promise evidence. Schedule/order locking has a deterministic order.
- Reorder preserves intent and clears calculated artifacts/prices, including legacy selection JSON, so resale requires current engineering.
- Work Order release checks that schedule-approved drawings match the actual order. Engineering can bind the requirement to the same-customer/same-schedule order and obtain a new revision approval. Waiving/moving requirements still requires System Manager. Disabled reviewers/assignees cannot retain access.
- New Linear/Tape/Neon builds freeze supported specification/offering/profile/lens/driver PDF sources; Sheet freezes panel engineering values. Older v2 builds lacking a required frozen value fail that mapping instead of silently using edited masters. Issued PDFs stay unchanged.
- Tape/neon previews and saves share one snapshot/hash constructor. Legacy BOM previews use actual builders. Group labels follow canonical geometry while duplicate members remain distinct; artifact failure rolls back before handoff.
- Five template forms expose Engineering preflight and paginated affected products. Authoring roles can manage product masters without commercial transaction privileges. Flat CSV validation reports unknown fields and invalid numbers.
- Optional family/pilot-user controls gate new configurations, with catalog inquiry actions when unavailable. Group preview/save additionally requires its site flag. These controls do not grant permissions or change historical document access.
- Cloud evidence, actor fixtures, separate-session tests, private-copy rehearsal, CI and operating documentation are ready to run; none are represented as executed Cloud acceptance.

## Local verification

| Check | Result | Boundary |
|---|---|---|
| `python -B -m unittest discover -s tests/portal_unit` | **193 passed** | Explicit Frappe/database/service doubles; no installed Bench |
| `python -B -m unittest discover -s tools/fixture_builder/tests` | **99 passed** | Local generators/import contracts |
| Six `tests/portal_ui/*.test.cjs` suites | **27 passed** | JSDOM/rendered fixtures, not native layout |
| `node tests/portal_unit/publication_workflow.test.cjs` | **123-job simulation passed** | Checked-in worker branches with HTTP doubles: recovery/429/identity/publish/retire |
| `node --test tests/portal_unit/reconciliation.test.cjs` | **6 passed** | Remote fields/assets/revisions/retirement with HTTP doubles |
| `python -B tools/check_portal_templates.py` | **35 templates; 12 rendered inline scripts; quote/configurator/shipment rendering passed** | Framework/layout globals are doubles |
| Changed/new JS syntax checks | **40 files passed** | Node parser; runtime behaviors covered separately above |
| `python -B tools/check_pdf_fidelity.py` | **Four distinct pages filled/merged/rasterized and visually checked; missing required form field rejected** | Synthetic master, not installed family masters |
| `python -B tools/check_b2b_changes.py --format-new` | **204 Python files; no introduced Ruff diagnostics** | 656 existing baseline diagnostics retained; AST/JSON parsing passed |
| `npm run list --prefix tests/portal_e2e` | **27 browser cases discovered** | Listed only; no Cloud URL/fixtures/approved numerical references |

PDF evidence: ignored `.tools/portal-pdf-qa`; lint evidence: `.tools/b2b-validation.json`. `.github/workflows/b2b-contracts.yml` runs local checks; GitHub has not executed it here. Existing Bench CI is separate. Repowise reports stored baseline health with new modules not indexed; no live coverage/health improvement is claimed.

## What still needs to be done

The remaining work requires the owner's deployed test site, actual engineering/product data or external service bindings. It is not a phase-approval pause.

1. Deploy to isolated fresh and upgraded Cloud sites; migrate/build/run installed tests, compare history/roles/workspace, and prove matched database/files/code/assets restore.
2. Approve numerical cases for the four reference templates, Tunable White and grouped L1 quantity two. Verify ERP stock reservation/planning on the installed version.
3. Run the prepared browser suite and all mandatory installed journeys: Desk, native permissions, concurrent sessions, mixed packets, commercial review/fulfillment, drawings, support and notification delivery.
4. Rehearse legacy public-file references/access/CDN retirement; bind test n8n/Webflow credentials; verify CMS schema, PDF masters and embeds; run remote reconciliation.
5. Record owners/absence coverage, baseline timing targets, pilot results and signoffs. Require every mandatory case, zero unresolved P0/core-journey P1, and the plan's at least 90% unassisted pilot completion with sample size.

Use [Cloud acceptance](B2B_CLOUD_ACCEPTANCE.md) for commands, fixture schema, the journey matrix and release record. Related handoffs: [authoring fields](B2B_AUTHORING_FIELD_REGISTER.md), [compatibility](B2B_CONFIGURATOR_COMPATIBILITY.md), [publication](B2B_PUBLICATION_RUNBOOK.md), [staff operations](B2B_STAFF_OPERATIONS.md), [quote operations](B2B_QUOTE_OPERATIONS.md), [Sheet policy](B2B_SHEET_BUILD_NOTES.md).
