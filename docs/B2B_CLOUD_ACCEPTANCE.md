# B2B Cloud acceptance and release evidence

This is the runnable handoff for the original plan and grouping add-on. Local tests use framework/database doubles. No fresh-site installation, upgraded-site migration, real browser journey, SQL race, stock reservation, installed n8n workflow, remote publication, or restore drill has been run in this workspace. Run this pack on an isolated Frappe Cloud test site before dealer rollout. The owner will deploy the app.

## Site preparation and historical evidence

Use both a fresh ERPNext site and a restored, sanitized production-shaped site with the same intended app commits. Record Frappe/ERPNext/app commits, Python/Node/MariaDB versions, installed apps, custom overrides, asset manifest, PDF renderer, scheduler/worker state, stock reservation settings, companies/warehouses, CMS schema and n8n version. Keep real outbound mail, production credentials and live publication disabled during rehearsal. Use a mail sink for notification acceptance.

Back up database, public/private files, site configuration, custom Workspace records, custom permissions and the previous deployed assets. Retain the current code revision alongside those backups. On the restored site, put this app's new code on disk, but capture the historical checkpoint **before** migration. The checkpoint reader tolerates new DocTypes/fields being absent. Run as the Bench Administrator; all evidence functions below are Bench-only System Manager tools.

```sh
bench --site TEST_SITE execute illumenate_lighting.illumenate_lighting.portal.release_evidence.capture --kwargs '{"label":"before-migration"}'
bench --site TEST_SITE migrate
bench build --app illumenate_lighting
bench --site TEST_SITE clear-cache
bench --site TEST_SITE execute illumenate_lighting.illumenate_lighting.portal.release_evidence.capture --kwargs '{"label":"after-migration"}'
bench --site TEST_SITE execute illumenate_lighting.illumenate_lighting.portal.release_evidence.compare_checkpoints --kwargs '{"before_label":"before-migration","after_label":"after-migration"}'
bench --site TEST_SITE execute illumenate_lighting.illumenate_lighting.portal.release_audit.inventory
bench --site TEST_SITE run-tests --app illumenate_lighting
```

Use the Cloud deployment/job equivalents when direct Bench commands are unavailable. Do not run mutation-based tests on production. Historical Quotation/Sales Order/BOM/configured-record/offer/intake hashes must have no unexplained changes or missing records. New schema rows are reported separately. The collector also records app commits, active-hook/asset hashes, managed custom fields and role permissions; compare those explicitly, since the historical-record comparator does not approve permission changes. Evidence lives under `private/backups/b2b-release`; protect downloaded copies too.

The Workspace migration saves the prior workspace beneath `private/backups/ill-workspace`. Compare every existing useful destination and site-specific block after the merge. No users are assigned new job roles automatically. Verify each ordinary role with its intended native ERP permissions, not an Administrator session.

## Actor fixtures and browser suite

On the isolated site only, set `ill_portal_acceptance` to JSON `true`. Provision distinct secret values of at least 16 characters in the environment of the seed command for all 14 actors:

`B2B_E2E_ADMIN_PASSWORD`, `B2B_E2E_DEALER_A_PASSWORD`, `B2B_E2E_BUYER_A_PASSWORD`, `B2B_E2E_DEALER_B_PASSWORD`, `B2B_E2E_MEMBER_A_PASSWORD`, `B2B_E2E_VIEWER_PASSWORD`, `B2B_E2E_EDITOR_PASSWORD`, `B2B_E2E_SALES_PASSWORD`, `B2B_E2E_APPROVER_PASSWORD`, `B2B_E2E_ENGINEERING_PASSWORD`, `B2B_E2E_CATALOG_PASSWORD`, `B2B_E2E_INTEGRATION_PASSWORD`, `B2B_E2E_OPERATIONS_PASSWORD`, `B2B_E2E_SUPPORT_PASSWORD`.

Use the site's secret manager or a private process environment, rather than placing passwords in a checked-in file or command argument. The seeder suppresses welcome mail and returns no passwords.

```sh
bench --site TEST_SITE execute illumenate_lighting.illumenate_lighting.portal.acceptance_fixtures.seed --kwargs '{"run_id":"qa20260925"}'
```

Each new run ID creates two customers with contacts, two projects/schedules, private image fixtures, VIEW/EDIT collaboration and named job-role users. It deliberately does not invent engineering data, Item prices, offers or approved orders. Download the private fixture manifest `b2b-qa-RUN_ID-fixtures.json`; retain it outside Git. Restore the disposable site to reset fixtures, or choose another run ID. The tool does not delete business records.

Engineering must populate `engineering_cases` in that manifest with at least the four owner-selected templates: Linear `ILL-SH01-SW`, Tape `led-hd-sw`, Neon `non-pnc-sw`, Sheet `Snowfield Static White LED Sheet`. Each case has this shape:

```json
{
  "family": "Linear Fixture",
  "template": "ILL-SH01-SW",
  "payload": {"fixture_template_code": "ILL-SH01-SW"},
  "portal_request": {
    "template": "ILL-SH01-SW",
    "product_slug": "ACTUAL_APPROVED_SLUG",
    "selections": {},
    "segments": []
  },
  "expected_build_hash": "ENGINEERING_APPROVED_64_CHARACTER_HASH"
}
```

This example is intentionally incomplete and cannot pass. `payload` is the complete family builder input accepted by `configured_product_builder.calculate_and_lookup`; `portal_request` is the complete current UI selection/topology input accepted by `portal.configuration.save`. For Tape/Neon include `tape_neon_template` in the builder payload, and pass it separately through the suite's template argument. Preserve explicit power inclusion, max-run policy, protocol, cable lengths and Sheet coverage units. Approve dimensions, light-engine quantities, cable cuts, run watts, allocations, stock UOM quantities and BOM quantities independently before recording a build hash. A hash copied from an unreviewed calculation is not an engineering reference.

From the checked-out repository, with the same actor secrets available:

```sh
npm ci --prefix tests/portal_e2e
npm exec --prefix tests/portal_e2e -- playwright install chromium
export B2B_E2E_URL=https://YOUR-ISOLATED-SITE
export B2B_E2E_FIXTURE=/PRIVATE/PATH/b2b-qa-RUN_ID-fixtures.json
npm run test --prefix tests/portal_e2e
```

The suite runs desktop 1440×900, tablet 768×1024 and mobile 390×844. It verifies native private-file access, company/VIEW read-only behavior, built assets/modal dismissal, denied staff APIs, catalog failure/retry, two-session save races with changed-retry rejection, ordinary Sales Desk navigation and approved four-family hashes. It records seven catalog timing samples per viewport without inventing an acceptance threshold. Missing engineering cases fail, rather than silently skip. Artifacts may contain private business IDs and failure screenshots; keep them restricted. Traces/video are disabled and login secrets never enter page screenshots.

## Mandatory installed-site journeys

The automated browser suite is a starting set. Record each row below as pass/fail with actor, site/app revision, evidence file and reviewer. No local test count substitutes for these scenarios.

| Area | Required acceptance |
|---|---|
| Identity, account and privacy | Guest, dealer A, dealer B, company member, VIEW, EDIT, every job role and admin. Profile/contact/address changes, invitation acceptance and disabling. Attempt foreign customer/project/order links, native REST writes and direct private URLs. Revoke access between enqueue and mail send; verify no delivery. |
| Catalog and standard products | Search/filter/page with empty, loading, transport failure and inactive direct links. Driver/controller/accessory/approved kit selects a real Item/variant and quantity in its stock UOM. Unsupported products show inquiry. Keyboard focus, Escape, Enter, back navigation and mobile layout. |
| Four configurators | Same selection in Portal, Linear wizard where supported, and Quotation/Sales Order Desk. Toggle power by mouse, label and keyboard; Back, close/reopen, second dialog, Add Another, stale/late response and unsaved-parent paths. Reopen every option and unit. Inject a failed Item/BOM/parent save: no partial configured record, line or receipt. |
| Engineering | Reference templates; power included/excluded; true/false strings; actual uneven runs; driver total/per-output/independent-output limits; exact shared jumpers and extra split-run feeds; cable stock-UOM/assembly-length validation. Sheet Tunable White uses full panel wattage. Reels are continuous bulk stock without fabricated cut-assembly leaders. |
| Independent groups | Enable `ill_portal_fixture_groups` only on the test site. One-member parity for all four families; multiple independent members with internal jumpers; same-family/spec enforcement; one/multiple/shared supplies; excluded-power requirements; reordered/renamed labels; identical geometry duplicates; L1 20/5/25 ft with 6/3/2 ft leaders, quantity 2. Verify parent BOM is quantity one, overall demand doubles every component exactly once, PDF labels/cuts remain distinct, failure rolls back all artifacts, and existing groups remain readable when the new-group flag is off. |
| Stock and production | Only configured company + eligible `ilL-Stores` warehouses. No all-warehouse fallback. View/quote/draft requests reserve nothing. At SO submission inspect the installed ERP reservation/planning records. Confirm component requirements, draft Work Order reuse, partial demand and cancellations. Record the approved planning process if the installed ERP mechanism does not reserve the intended components. |
| Documents | Real family PDF masters, required mapping values, Unicode/long labels, checkboxes, all pages and actual Cloud renderer. Mixed four-family/group/OTHER/approved Item-literature packet; replace/duplicate/version attachments; unavailable source; forced worker failure/retry; changed bytes and stale claims; explicit incomplete draft; issue/freeze/download old packet after source changes. No cover-only success. Compare PDF byte checksums and page index. |
| Quote and direct PO | Unpriced inquiry receipt, staff preparation, submitted Quotation offer and frozen PDF, validity/supersession/cancel, accept-once, revised terms and buyer acknowledgment. Direct PO accepts optional private PO file, owned addresses/contact, requested date, instructions, exclusions and retry. Confirm address display is the native owned address and OTHER scope stays in packet but outside sellable lines. |
| Review and lineage | Sales can prepare but cannot approve; Approver can set confirmed dates and submit only with current acknowledgment/build. Dealer native submit denied. Amendment clears prior approval. Rejected/withdrawn/deleted/cancelled lifecycle reaches the intended state. Designation, room, notes, configured group/build/BOM and engineering request survive Quote→SO→DN→SI, including partial deliveries, returns and print output. Select `ilL Delivery Note` for the new unpriced shipment print. |
| Drawings | Revision 1→changes requested→revision 2 approval; denied/unpublished/stale bytes; physical change creates reapproval Task. Pending drawing does not block SO approval. Work Order release checks the actual order scope; bind a schedule-only drawing to a changed SO and publish/reapprove. Only System Manager can waive/move an existing requirement. |
| Order service/support | Mixed produced/unstarted/standard lines, partial shipments/returns/cancelled DN, invoices issued vs paid, requested vs staff-confirmed dates. Change/cancel/reorder/replacement require current evidence; new draft recalculates engineering/pricing. Private support replies/files, resolve/reopen and pagination beyond five tickets. |
| Notifications/queues | Staff-created order reaches actual buyer, not staff owner; preferences and revoked recipients; duplicate events/retries; mail outage, pending/queued/failed/SMTP-accepted/unknown distinctions. Count equals paginated drilldown for every role and Mine/Unassigned/Overdue filter. Forbidden/unavailable is never zero. |
| Authoring/publication | Ordinary Engineering/Catalog author the five template families, specs/compatibility/mappings/literature; drafts save with useful channel blockers. CSV/generator parity, real sample PDF, public Sheet controls/PDF/sign-in handoff. Stage vs live approval, two brands, edit during claim, 429, timeout-after-create, permanent failure, retry, retirement and read-only remote reconciliation. |
| Upgrade/restore | Workspace and role comparison, approved-record hash comparison, old private/issued PDFs, repeated migrations. Restore the database/files/configuration/previous code and assets on another disposable site, verify access and historical documents, then redeploy and repeat smoke tests. |

## Legacy files and external systems

Use `release_audit.inventory` to select legacy public project File records. Run `legacy_file_migration.dry_run` with an explicit list of 1–50 File names. It reports known direct references, same-URL aliases and SHA-256. Search rich text, JSON snapshots and external URLs separately. `copy_private(file_name, expected_sha256)` creates a checksum-verified private copy attached to the same parent and retains the public original; it does not rewrite references or assert that every actor can read the new file. Rehearse permitted/denied native downloads and reviewed pointer changes on the clone. Published drawing and issued-packet evidence stays immutable; publish a replacement revision where needed. Retire the public origin and purge CDN only after reference/access verification. No automatic destructive cleanup ships in this app.

For n8n/Webflow use [the publication runbook](B2B_PUBLICATION_RUNBOOK.md). Bind real credentials on the test deployment, inspect actual field types and embeds, and retain staged/live remote comparison reports. All live publication remains an explicit staff action. For staff training use [Portal operations](B2B_STAFF_OPERATIONS.md), [quote operations](B2B_QUOTE_OPERATIONS.md), and [authoring fields](B2B_AUTHORING_FIELD_REGISTER.md).

## Release record

Record the release owner, Sales approver, Engineering reference reviewer, Catalog owner, Integration/email owner, Support owner and Operations owner, with named absence coverage. Keep a signed evidence manifest identifying app/site revisions, fixture run IDs, test results, PDF samples, migration/restore reports, remote reconciliation, pilot cohort, timing baseline and unresolved issues.

Require every mandatory scenario to pass, no unresolved P0 or core-journey P1, and the plan's at least 90% unassisted pilot completion with sample size and individual failures retained. Set performance targets from the approved S0 baseline before judging results. Do not invent numerical engineering or timing approval locally.

Roll out approved families with the optional JSON-list site settings `ill_portal_enabled_families` and `ill_portal_pilot_users`, alongside product/channel approvals. Canonical family values are `Linear Fixture`, `LED Tape`, `LED Neon`, `LED Sheet`. Omitted lists preserve availability; an empty family list disables new configurations. An empty pilot list allows only authorized Sales/Engineering. Public product-only literature bypasses the user cohort but still obeys family availability. Test direct API calls as well as catalog actions. Retain `ill_portal_fixture_groups=false` until group acceptance; this flag also gates new group preview/save on the server. Historical orders and private issued documents remain readable. These controls do not stop every commercial transaction or integration; use a maintenance window/site access restriction when an incident requires stopping all new writes.

After rollout, inspect failed/incomplete packets, stale/failed publication, mail failures/unknown attempts, unassigned/overdue review work and manufacturing holds. Recheck one private download, one family calculation, one native Desk queue and one remote staged/live comparison after each deployment. Rollback restores the tested matched database/files/code/assets set; do not downgrade code blindly against newer business records.
