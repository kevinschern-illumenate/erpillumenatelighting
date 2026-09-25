# B2B portal technical implementation plan

Prepared September 25, 2026. Source baseline: `845979669b3760fa49a80dd7000892a3a327838e`.

**Deliverable: investigation and implementation handoff only. No application implementation, migration, deployment, publication, or customer communication is authorized by this document.** Proposed modules, fields, roles, endpoints, and DocTypes below do not exist unless explicitly identified as existing. Their names are implementation proposals; their behavior is the contract.

This plan implements the expanded [product audit](B2B_PORTAL_PRODUCT_AUDIT_AND_ROADMAP.md), including all F01–F32 findings and all 13 increments. It preserves the recorded decisions in the [dealer portal plan](DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md), [quotation/configurator plan](QUOTE_ORDER_CONFIGURATOR_PLAN.md), and [grouping plan](CONFIGURATOR_GROUPING_ALIGNMENT_PLAN.md). It replaces their obsolete implementation assumptions where current source proves that work already exists.

## 1. Implementation brief and constraints

Complete the existing application as a staff-approved B2B service. Keep Frappe/ERPNext, the family engines, scoped configurator classes, project access policy, ERP commercial documents, export jobs, and n8n/Webflow publishing. Do not begin with a portal rewrite or a wholesale split of `api/portal.py`.

The next implementation agent should first deliver S0 and the independently releasable S1 corrections, while investigating S4 blockers immediately. All four configurable families, independent groups, visual schedule selection, mixed-manufacturer specification packets, product authoring/publication, public filled downloads, and the staff workspace remain release scope. Earlier pilots may expose only families that have passed their correctness gates; removing a family or grouping from the final release requires an explicit scope decision.

**Settled decisions — do not ask the owner to reconfirm these:**

| Subject | Binding requirement and source |
|---|---|
| Buying | Dealer submits a quote request or PO/order request. Staff approval confirms the order. No immediate checkout/payment/automatic acceptance. |
| Durable order request | Existing draft `Sales Order` is the request; `docstatus=1` submission is approval. Do not introduce a second order-request master. Dealer has no submit/cancel/amend permission. |
| Schedule lifecycle | `ORDER_REQUESTED` means draft order awaiting approval; `ORDERED` follows submission. Rejected/deleted/cancelled requests use `ISSUE` with the sales contact message. Preserve existing versioning when leaving a quoted version to edit. |
| Dealer access | Dealers use the portal, not Desk. Company-linked dealers retain the existing company project/schedule rights; same-company non-dealers are read-only unless owner or explicitly invited to edit. Collaborators see project artifacts, not company commercial documents. |
| Commercial visibility | Dealers and appropriately authorized staff see price/stock information. Non-dealer collaborators do not gain pricing through a picker, PDF, API, or email. |
| Stock | Only `ilL-Stores`; no inter-warehouse promise. Display available now, with time and scope. Reservation starts at Sales Order submission, never browsing, quote request, or draft order creation. Verify how the installed ERP performs that reservation. |
| Manufacturing | Existing automatic linear-fixture Work Order behavior is retained subject to the release checks below. Tape/neon, sheets, kits and accessories use standard ERP planning; do not add automatic Work Orders for them as a side effect of parity/grouping. |
| Dates/tracking | Sales Order `delivery_date` is the authoritative staff promise. Add separate requested/estimated facts and an explicit confirmation event. Delivery Note `transporter_name` and `vehicle_no` are the maintained carrier/tracking fields. |
| Printed field meanings | `line.location` → Section/Room; `line.line_id` → fixture designation printed above its item; customer notes → additional notes below; configuration summary → description. Do not duplicate fixture designation into notes. No new supplier Purchase Order workflow is requested. |
| Desk configuration | Quotation/Sales Order toolbar plus Items-grid action; optional schedule with warning; parent document may remain unsaved; deleting a transaction row does not silently delete its schedule line. Submitted Quotation marks eligible schedule QUOTED. |
| Grouping | Same family/shared compatible specifications, independent members with internal jumper chains preserved, one power choice per group, quantity multiplies the entire group. Prefer one feasible supply; allow more where necessary. Excluded power adds no automatic supply row. Sheets have coverage areas and no max-run override. |
| Follow-ups | Searchable cards/thumbnails in Add Line; other-manufacturer specifications in the overall packet; reliable authoring → n8n/Webflow → filled PDF; refresh `/desk/illumenate-lighting`. |
| Communication/retention | Email is the initial channel. The earlier one-year preference is not authority to delete commercial/audit records indiscriminately; define retention by artifact before any deletion automation. |

## 2. Investigation result and evidence limits

HEAD matches the audit. Repowise overview and risk queries were used; the broad answer was low confidence and was not treated as proof. Source/schema comparisons confirmed the important findings. Source references in section 12 identify the implementation anchors. Existing local changes, including the audit, grouping plan and Repowise state, predated this deliverable.

| Confirmed in this investigation | Planning consequence |
|---|---|
| Catalog detail reads `document_name/file_url`, but child rows store `document_title/document_file`; options use `option_label/allowed_values_json`; certifications link `ilL-Attribute-Certification`. | Repair the projection, not the storage schema by adding duplicate legacy fields. Certification master has name/body/code/badge/applicability, **no certificate-file field**; a certificate download needs an explicitly added document relationship. |
| Direct catalog lookup does not filter inactive products. Detail invokes nonexistent `initializeFromProduct`; the retained JS shim has no runtime initializer. | Active/readiness policy must apply to direct routes and configure/download APIs. Route by family; merely renaming the initializer is insufficient. |
| Drawing/support forms serialize `FormData` into JSON; request attachment API creates a public File from a URL. Other-manufacturer upload is real, public, and returns the same null value for failure/no selection. | Upload bytes separately, verify server-owned File IDs, then finalize the request/line. Reject arbitrary URL adoption and preserve old files on failed replacement. |
| Schedule conversion has a database row lock/savepoint, but both endpoint and controller perform state eligibility before linked-order lookup. Existing duplicate-conversion tests expect success. | Separate authorization from create eligibility; perform the authorized existing-request lookup under the lock before the create-only guard. Retain atomic conversion. Bench reproduction is still required. |
| `request_quote()` directly writes QUOTED and sends “Quote ready”; the generic status API also permits READY→QUOTED for dealers/internal users. | Fix both entry points. An issued quotation must be the source of offer state, not a caller-selected schedule badge. |
| Tape/neon driver queries use missing fields; builder uses `bool()` on strings; tape segment forwarding differs from neon; BOM omits power and labels raw leader inches as Item UOM. Linear leader components are disabled. | S4 is a release gate, with contracts and engineering reconciliation before wider ordering. Procurement `cost` must not simply be relabeled MSRP. |
| Sheet configured Item lookup can reuse `part_number`; accessories exist both as sibling commercial rows and BOM components. | New build identity and bundled representation are required; preserve legacy presentation with explicit migration rules. Historical corruption is not proven by static inspection alone. |
| Stock already subtracts reservations and scales/allocates shared demand. Empty `ilL-Stores` lookup falls back to all warehouses. | Keep existing aggregation and change missing scope to unavailable/error, with no cross-company fallback. |
| Quotation/Sales Order hooks, order read model and access-checked commercial PDFs already exist. SO timeline uses transaction date for approval; production completion considers only existing Work Orders. | Extend these modules; add actual events and line coverage rather than replacing tracking. |
| `get_webflow_products` already accepts limit/offset. Checked-in product workflow fetches 50 without continuation, stages drafts, lacks executable product-error branches. Sync callback has no payload revision/hash. | API pagination support alone does not complete workflow pagination. Use revision-aware jobs/acknowledgments and explicit staged/live facts. |
| Sync APIs inspected use authenticated whitelisting and privileged queries/writes without an explicit local integration-role gate. | Add an integration capability and negative authorization tests; authentication alone is not the intended publish authority. Deployed middleware/permissions remain to be checked. |
| Public filled-download dispatcher lacks LED sheets. Packet code includes OTHER lines in both modes, can fall back to static sheets, and can complete with a cover but no required sheets. | Preserve supported inclusion; add family dispatch, explicit fallback classification and a completeness manifest. |
| Request deliverables have version/publication fields but no revision-specific customer decision record. Workspace already contains useful setup links but no quick lists/charts/custom blocks. | Extend deliverables and workspace instead of recreating them. |
| Fresh-install `create_dealer_role()` sets `desk_access=1`, while the recorded decision requires portal-only dealer usage. | Include fresh/install upgrade role reconciliation in S0/S6. Do not assume this alone proves that a deployed Website User can access Desk. |

**Verification actually performed:** read-only source/schema/workflow inspection; repository/route/test searches; current HEAD check; `python -B -m unittest illumenate_lighting.illumenate_lighting.api.test_led_sheet_math` passed **34 tests**. No application tests were added. Frappe is not installed in the inspected Python runtime. No Bench test, authenticated browser test, generated PDF visual test, production data inspection, n8n execution, Webflow publication, or migration was performed. Password and Desk checkbox runtime causes remain unverified. The absence of a browser journey suite is based on the inspected repository/CI, not external test systems.

## 3. Target architecture and contracts

### 3.1 Extend existing boundaries

| Existing area | Target change / proposed addition | Reason |
|---|---|---|
| `portal/access.py`, DocType permission hooks, `dealer_permissions.py` | Named staff capabilities and shared query predicates; new artifact/request access rules | Preserve existing customer isolation without turning every staff role into globally unrestricted “internal.” |
| `api/product_catalog.py`, Webflow enrichment/export, template controllers, `guardrail_audits.py` | Proposed `api/product_projection.py` and `api/product_readiness.py` | Share approved field mapping and channel readiness while retaining family engineering authority. Reuse current fixture mapping coverage audits. |
| Shared configurator classes and family engines | Proposed `api/configuration_contract.py`, `api/power_planner.py`; extend builder to sheets via existing adapter | One normalized contract; family geometry remains in the engines. Keep public method wrappers until external consumers migrate. |
| Existing configured records and BOM helpers | Immutable versioned build snapshots and component manifest | Price, stock, BOM and documents must consume the same build facts. Do not recalculate historical commercial records from live templates. |
| Grouping proposal | `api/fixture_group_configurator.py`, `api/fixture_group_bom.py`, group/member/allocation DocTypes | Aggregates are required server-side; a UI-only member array cannot survive conversion/export/manufacturing. |
| `api/document_requests.py`, `api/exports.py`, `api/spec_submittal.py` | Proposed `portal/files.py`, line-document records; extend export job | A shared authenticated file lifecycle and immutable packet manifest. Avoid a generic document-management platform. |
| Schedule conversion / `quote_from_schedule.py` / Desk hooks | Proposed `portal/quotes.py`, `portal/order_requests.py`, quote-request DocType; extend Sales Order | Quote intake requires a durable unpriced request; Sales Order already provides durable order intake. |
| `portal/orders.py`, `portal/status.py`, `portal/notifications.py` | Real event timestamps, per-line fulfillment facts, recipient resolver and durable event delivery records | Reliable history and retries without replacing ERP fulfillment/accounting. |
| Existing `Issue`, `ilL-Document-Request`, request deliverables | Portal issue replies and document review records | Reuse standard support and existing technical-request workflows. |
| Workspace JSON / fixtures / setup guides | Role-filtered live queues plus maintained setup navigation | Counts, lists and detail screens must use identical state/access rules. |

Keep `api/portal.py` as a compatibility transport layer while stories move their own logic into cohesive services. No unrelated endpoint renaming, mass formatting, or framework migration. Update `hooks.py` bundles, events, permissions and fixture exports together with each affected feature; it is dynamically loaded and a graph's zero dependents does not imply no impact.

### 3.2 Catalog and publication projection

Define a versioned product projection consumed by the portal and exported to n8n. It contains:

- Stable product name/slug, canonical family, template/spec/Item references, approved revision, active/retired state and capability declaration: `configure`, `quantity_request`, `inquiry`, or `unavailable`.
- Identity/title/series/category, description/features, hero/gallery/alt text/dimension image; ordered specifications `{group,label,value,unit,display_order,source}`.
- Certifications resolved from linked masters, including code/name/body/badge and validated applicability. No fabricated certificate URL or inherited family certification claim.
- Documents `{id,title,type,classification,source,revision,file_id,download_url,required,display_order}`. Product-document override may take precedence for that declared document type; otherwise use family template literature. Filled submittals are generated artifacts, not substitutes for a static datasheet.
- Options `{step,type,label,description,required,depends_on_step,allowed_values}` parsed/validated from actual JSON fields. Preserve codes and labels separately. Malformed options block configured publication, not draft authoring.
- Capability-specific quantity/unit/dimension metadata; pricing `{basis,currency,amount,includes,excludes,as_of}` only for eligible actors. Never use a fixture MSRP for tape/sheet products or render absent pricing as zero. Backend strips commercial facts for public/non-dealer projections.

Normalize existing family aliases at the boundary: catalog `Fixture Template`, schedule `Linear Fixture`/`Linear Fixtures`, tape, neon, sheet. Retain original identifiers for backward-compatible wrappers. Do not assume every Webflow product has `fixture_template`; use its actual family linkage. Driver/controller variants resolve to sellable Items; unsupported kits/components receive inquiry, not a broken configurator URL.

Readiness returns `{channel,ready,source_revision,checked_at,errors[],warnings[]}` where errors have record, field, code, owner and remediation. Channels are portal catalog, portal order configuration, Webflow, filled PDF. Draft saves remain possible. A changed shared dependency invalidates affected readiness; channel caches include the dependency fingerprint. Approval records the exact projection fingerprint. Catalog detail, list, direct configure and public download apply the same channel decision. Read-only historical documents remain readable even if their product is retired.

### 3.3 Configuration, save envelope and identity

Proposed normalized request:

```json
{
  "contract_version": 2,
  "family": "LED Tape",
  "template": "<existing template name>",
  "mode": "single",
  "shared_options": {"cct": "<code>", "output": "<code>", "control": "<code>"},
  "include_power_supply": false,
  "max_run_override_mm": null,
  "members": [{"member_key": "<uuid>", "segments": ["<validated family segment objects>"]}]
}
```

This is a shape example, not executable input. Segment objects contain requested length, leader/feed information, end type and outgoing jumper; sheet members instead contain width/height and supported feed inputs. Store normalized millimeters with documented precision, retaining display-unit preferences separately. No NaN/infinite/nonpositive physical dimensions. Parse true/false, 1/0 and supported legacy strings explicitly; reject ambiguous values. A missing value invokes a default; an explicit false survives. Reject sheet max-run override.

The save envelope adds schedule/version, stable line key, expected parent `modified` value, fixture designation, location, notes, quantity and idempotency key. Keep line quantity outside the per-group calculation. Server ignores client-supplied prices, loads, BOMs and validity claims except separately authorized staff BOM overrides.

Result contains normalized inputs, requested/manufactured dimensions, members/segments/pieces/electrical runs, power requirements/allocation, numeric component manifest, price estimate/scope, warnings/errors, input fingerprint, engine version and dependency revision. Save either recalculates server-side or verifies a server-issued calculation token bound to those inputs/dependencies; a stale UI result never authorizes persistence. Concurrent edits return a conflict with reload/reapply guidance.

Two identities are needed: canonical engineering input identity and resolved build identity (components, allocations, rule/version fingerprints, approved overrides). Stable UI member UUIDs and display names must not unnecessarily alter physical build identity; ordering/topology that changes assembly must. A new build does not overwrite an earlier configured record, Item or BOM. Store canonical JSON and full hash; human part number is a label, not a sufficient uniqueness key. Customer-specific prices belong to offer/order snapshots, not a globally reused Item name. Include power policy, override/control choices, sheet dimensions and selected components in the correct identity layer.

**Component manifest:** `{role,item_code,member_key,run_key,cable_key,physical_qty,physical_unit,stock_qty,stock_uom,conversion_factor,included,unit_price_basis}`. Aggregate only after preserving traceability. For bulk cable, convert length into the actual stock UOM; a `Nos` cable requires a valid fixed-length assembly mapping. Count every physical leader/jumper once. Bundled new sheet/group output has one commercial unit and one BOM; no generated sibling supply/cable sale rows. Legacy exploded-sheet rows remain explicitly marked and owned by their schedule line.

### 3.4 Proposed schema changes

Names below are proposals to implement additively. Use existing Link/Dynamic Link/custom-field conventions. Do not insert nested Frappe child tables into schedule child rows.

| Record | Add/extend | Invariants / migration |
|---|---|---|
| Schedule line | `line_key` UUID, `source_line_key` for deliberate duplicates if useful, supply scope (`SELLABLE`/`SPEC_ONLY`/`INQUIRY`), build schema/mode, group link | `line_id` remains user fixture designation; child `name` remains legacy transaction reference. New duplicate gets new key; new schedule version preserves logical key scoped by schedule. Old index-based APIs adapt with parent version checks until retired. |
| Existing configured fixture/tape-neon/sheet | Contract/build versions, normalized input/resolved snapshot, full build fingerprint, immutable predecessor linkage where absent, tape/neon inclusion and persisted power allocations | Do not rehash or mutate historical records automatically. Existing arrays/fields remain readable through adapters. Audit controller fallback hashing as well as API hashes. |
| `ilL-Configured-Group` and member/allocation children | Family/template/shared choices, ordered members, snapshots, input/build hashes, power, price/component manifest, Item/BOM, predecessor | Group compute/save is atomic; group link dispatch precedes old singular fields. Each member references pinned configuration/snapshot, not an editable live template interpretation. |
| `ilL-Line-Document` (top-level) | Schedule link, line key, title/type, File link, document revision, replaces link, classification, primary/include flags, uploader, validation result | Permission derives from schedule. New revision creates a new File/document record. Existing `spec_sheet` remains a compatibility projection of primary file until old clients migrate. |
| `ilL-Quote-Request` | Owning customer/project/schedule version, request snapshot/hash, requester/contact, notes/date, assigned team/user, state, latest offer link, idempotency key | Separate from issued Quotation. Submission freezes request scope; later changes create a linked request revision. Attach private files to an authorized request record. |
| Quotation custom fields | Quote-request link, offer revision/predecessor, issued timestamp/by, snapshot/hash, portal availability/response | ERP `docstatus`, party, validity, items/rates/taxes/terms remain authoritative. Standard cancel/amend for commercial revision. Distinguish publishing an offer from a schedule-only status change. |
| Sales Order custom fields | Intake state, submitted requester/contact/time, request fingerprint/idempotency key, PO File link, requested date, shipping/receiving instructions, terms revision/acknowledgment, estimate metadata, approval by/time, confirmed-date flag/time, pinned scope | Reuse `po_no`, existing Customer/Contact/Address fields, `delivery_date`, existing schedule/custom item fields. Approval requires current customer acknowledgment when material terms changed. Rejected request can remain draft with terminal intake state; active-order lookup must exclude rejected/withdrawn requests under lock. |
| Transaction rows | Stable schedule line key plus existing `ill_schedule_line_id`; pinned group/build/BOM links and snapshot schema | Extend both Quotation Item and Sales Order Item fixtures/install logic. Preserve fixture type/location/notes and downstream Delivery Note/Sales Invoice lineage/print behavior. |
| Drawing deliverable + review | Stable deliverable revision identity/content hash, supersedes/current markers, customer-visible notes; `ilL-Document-Review` records decision, reviewer, time, comments, revision | Do not use mutable child index for approval. Published revisions immutable. Technical acceptance distinct from production release. |
| Support Issue / replies | Customer/project/order links, authorized requester/contact, response-required party; use existing Communication linkage for public replies and internal comments separately | Server validates linked order/project ownership; text pasted into description is insufficient linkage. Customer sees only designated external replies/attachments. |
| Export Job | Packet mode, immutable request/schedule snapshot, per-line manifest/errors, progress, `INCOMPLETE` terminal state, revision/hash, issued by/time, output checksum | Existing COMPLETE means required content present. Requested partial draft uses INCOMPLETE and a visible omissions page. Existing outputs remain untouched. |
| Webflow product + per-brand sync state | Source revision/fingerprint, readiness/approved revision, desired publication state; staged hash/time, published hash/time, operation ID and error/attempt metadata | Keep legacy scalar dual-write temporarily; `Synced` means staged only. Product/brand/operation concurrency control. Do not treat parent `modified` as content revision because sync metadata writes change it. |
| `ilL-Webflow-Publish-Job` | Product/brand/source hash, action, status, attempt, claimed worker/lease, CMS ID/result, error | Durable operation identity handles pagination, callback retry and crash recovery. Unpublish/retirement remains queued even though inactive products are excluded from normal export. |
| `ilL-Portal-Event` + delivery children | Source event key/type, record/revision, actor/time, customer-visible payload; intended recipient/category, queue reference, attempts/state | Unique event identity and recipient key prevent duplicate enqueue. Reuse Frappe Email Queue delivery; no SMTP replacement. Exactly-once external delivery is not guaranteed; receipts and enqueue are idempotent. |
| Account intake and invites | `ilL-Dealer-Application` (also support profile-change request), invitation records with company, scope/role, expiry/revocation and one-use token hash | Existing Customer/Contact/User/Address remain masters. No arbitrary company linking or role escalation from client fields. Apply stricter grant checks to invitations than ordinary schedule edits. |

Add indexes for actual queues/query predicates: customer/state/time, assignee/state/due date, schedule/line key, request/source revision, event key and product/brand/job state. Add unique constraints for business idempotency, not just frontend disabled buttons. Before adding uniqueness, report duplicates and resolve explicitly; never silently drop records.

### 3.5 Files, uploads and immutable documents

Classify documents as public approved literature, public informational generated output, private project material, private commercial material, or internal-only. An unrelated user knowing a URL must not bypass that classification.

Use an authorized draft parent (request or line-document staging record) and upload token. Upload bytes through the supported Frappe mechanism; server fixes private storage/parent assignment, validates content type/signature, allowed size/page/pixel limits and records checksum/size. Return File ID plus validation state. Finalize accepts only verified files belonging to this actor/upload session and intended parent. No arbitrary `file_url`, filename path or claimed owner may grant attachment rights. Retain the existing parent when a replacement upload fails.

Submit only when all required uploads validate; otherwise preserve a resumable draft and show per-file failure. Optional “save incomplete draft” must be explicit. Finalization and attachment-link changes are one DB transaction; external filesystem writes require rollback/orphan cleanup handling. File deduplication must not downgrade another private reference. Define an orphan staging-file cleanup policy separately from retention of business records.

Use authenticated download services that recheck the owning artifact, commercial visibility and revision publication at download time. Also verify native `/private/files/...` and generic File download behavior: hiding URLs behind a custom endpoint does not protect another permissive route. Unpublished staff deliverables/internal attachments must have a parent/permission model that cannot be read just because the customer can read the overall request. Add narrow file permission hooks or an artifact-owned private parent after testing the installed Frappe version; do not globally override every File in the ERP without need.

For historical public customer files: inventory every reference, classify with owner, copy to private storage with checksum validation, relink all authorized references, verify native and custom downloads, then remove old public bytes/URLs and invalidate relevant caches under a migration manifest. Changing `is_private` alone is insufficient. Shared public literature stays public only after deliberate classification. Previously downloaded public copies cannot be recalled; the migration report must not claim otherwise.

Default public Webflow informational PDFs contain product selections only. If project/customer labels are requested, require an authenticated private generation path; preserve selections through login. Do not silently write project metadata into a public File. Public informational generation still uses valid product choices, rate/resource limits and no dealer price/private links; it does not create order-ready approval.

### 3.6 Commercial state and transaction rules

| Object/event | Allowed action and effect | Failure/retry behavior |
|---|---|---|
| Quote request | DRAFT→REQUESTED by authorized schedule editor; staff→UNDER_REVIEW/INFORMATION_NEEDED; issue links a submitted eligible Quotation | Idempotent receipt identifies request/version and files. No QUOTED state or “ready” email on intake. Non-dealer editor can request assistance but cannot read dealer commercial offer or accept/place order. |
| Issued offer | Authorized staff submits/issues; dealer buyer views offer revision, expiry and terms; accept/decline/revision-request | Accept verifies customer, latest active revision, expiry and snapshot hash under lock. A repeated identical acceptance returns the same result; stale offer returns conflict. A quote revision supersedes the prior portal offer without editing its snapshot. |
| Schedule | Keep DRAFT/READY for editable preparation; QUOTED only from actual issued offer; ORDER_REQUESTED from draft SO; ORDERED from submitted SO; ISSUE for exceptions | Quote-request status is separate, avoiding unnecessary expansion of schedule enum. Remove dealer/manual READY→QUOTED path. Historical ambiguous QUOTED is flagged for reconciliation, not automatically rewritten. |
| Order intake | Dealer direct PO or accepted quote creates/reuses draft SO; intake progresses SUBMITTED→UNDER_REVIEW→INFORMATION_NEEDED/CHANGES_PROPOSED→APPROVED, REJECTED or WITHDRAWN | Authenticate and authorize schedule/customer first; lock schedule then request; look up eligible existing request before create-state guard; compare request key/hash. Same key/different body is conflict. Rejected/withdrawn replacement requires a new intent/version, not a retry that returns a dead request. |
| Staff approval | Staff approval capability + ERP submit permission + valid intake/build/customer acknowledgment; submit SO; record approval and versioned acknowledgment | `docstatus=1` remains the decisive approval fact. All paths, including native Desk submit/API, must execute the same before-submit guard. Customer cannot trigger submit through status mutation. |
| Approved changes | Customer proposes change/cancel against a specific order revision; staff evaluates and uses supported amendment/cancellation | No mutation of approved instructions by portal edit. Reject cancellation that ERP cannot safely perform and retain the request/outcome. Reorder creates a new draft using current validation/pricing. |

Use existing ERP Quotation validity, pricing, taxes and terms and its supported amendment/conversion path; validate exact behavior on the installed version. [ERPNext Quotation documentation](https://docs.frappe.io/erpnext/quotation).

Keep locks and savepoints through artifact creation and order linking. Audit explicit commits in called engines/helpers; no inner commit may escape a failed aggregate save. Business events/outbox rows are inserted with the business transaction; workers run after commit and can recover pending events after a crash. Frappe documents transaction callbacks and request rollback behavior; verify the installed v15 APIs before choosing a hook. [Frappe Database API](https://docs.frappe.io/framework/user/en/api/database).

Approval and manufacturing progress are separate facts. Today the linear submit hook logs generation failure without blocking approval. Target: validate build completeness before submit, then record any operational generation failure as a durable operations exception with retry. Decide explicitly whether a drawing hold blocks SO approval or only production release; neither a logged error nor a draft Work Order may masquerade as released production.

### 3.7 Permissions, staff roles and notifications

Retain current actor/customer resolution; add capability checks alongside it. Do **not** solve staff access by broadening `_is_internal_user()` to every Sales/Engineering role because it grants unrestricted access across many unrelated paths.

| Persona | Capabilities to map to installed roles | Explicit limits |
|---|---|---|
| Dealer buyer | Company project/schedule rights already defined; company commercial read; submit intake; respond to own authorized requests | Website User; no Desk, order approval, price override, publication, cross-company access. |
| Company access administrator | Buyer plus invite/revoke approved company memberships and choose notification contacts | New capability must not silently revoke existing dealer project editing. No System User/ERP role escalation; explicit disclosure of company editing rights. |
| Non-dealer company member / VIEW / EDIT collaborator | Existing read/edit project rules; permitted technical requests/reviews | No commercial pricing/orders/invoices; project file access only. Drawing signoff requires named reviewer authorization, not any read permission. |
| Sales/support staff | Prepare quotes, triage intake/support, propose commercial corrections | ERP record/company permissions still enforced; separate approval capability when required. |
| Order approver | Validate and submit approved customer orders | Native ERP submit permission plus intake guard; not every configurator operator. |
| Engineering | Configure, manage assigned drawing requests, publish deliverables, review technical data | Publishing a drawing or signing technical acceptance does not automatically release manufacturing. |
| Catalog/integration owner | Edit assigned masters, review readiness, stage/publish/retry approved revisions | Dedicated integration user for callbacks; no customer document access merely from publishing permission. |
| Operations | Order fulfillment/stock/date commitments and production exceptions | Financial access only if granted; no private internal note leakage to portal. |

Apply policy to list/count/detail/mutate/export/native File paths, not only menu visibility. Review permissive `All` DocPerm rows, Custom DocPerm, Role Profiles, User Permissions, Website User types, and document permission hooks together. Invitations/revocation must invalidate application handoffs and file access appropriately while preserving historical author/decision attribution.

Recipient resolver uses request submitter, validated purchasing contacts, named technical reviewers and staff queue ownership. Schedule/SO owner is an optional fallback only after validating that it is a customer contact. Do not discard the submitting buyer simply because they are the session actor. Events: quote receipt/info-needed/issued/expiring; order receipt/changes/approved/rejected/date-change/shipped; drawing clarification/published/review outcome; support response/resolution; staff failed export/sync/manufacturing queue. Each event maps to a preference category and accessible destination. Marketing stays opt-in. Default to existing optional transactional preferences until the owner defines mandatory messages; the portal receipt always remains available. Email failure never deletes the durable request.

### 3.8 Publication and packet processing

**Publishing:** source change → readiness → approved fingerprint → per-brand publish job → dependencies present → staged CMS update → exact-revision acknowledgment → authorized live publish → live verification. Maintain staged/live hashes independently. Webflow explicitly distinguishes staged content from live publication. [Webflow CMS publishing](https://developers.webflow.com/data/docs/working-with-the-cms/publishing).

Claim immutable queued jobs or a stable snapshot/cursor. Do not simply increase offset over a `needs_sync` set while callbacks remove earlier rows: that skips products. Export errors are not included by today's `needs_sync` filter; retry must explicitly claim failed jobs. Callback includes operation ID, product, brand, source hash and CMS ID. A completed older payload records its outcome but cannot clear a newer pending revision. If create succeeded but callback failed, reconcile stored operation/slug/brand/CMS identity before attempting another create. Enforce single active mutation per product/brand, bounded leases, backoff for throttling/timeouts, and terminal actionable errors. No site-wide publish that unintentionally includes unrelated edits; prefer approved item scope.

Sync categories/attributes/references before products, then dependent filter bindings; verify actual collection slugs and disabled transform flags before enabling fields. Active-product-only export cannot retire removed products, so explicit unpublish/archive jobs are necessary. Preserve per-brand credentials and IDs and test brands that intentionally exclude configurator payload. n8n must have executable per-item failure handling plus a workflow-level error path, not sticky notes. Reuse execution history/error workflow mechanisms. [n8n error handling](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully).

**Packets:** preflight an authorized immutable schedule/build/document snapshot; produce an ordered line manifest; validate/convert source documents; generate filled ilLumenate sheets; create schedule/cover/index and merge; verify page counts/checksum; store private immutable output. Manifest entries include line key/designation, manufacturer, selected source revision/hash, mode (`FILLED`/`STATIC`/`UPLOADED`), required/included/excluded/missing state, errors and page range. Repeated fixture designations never replace stable line identity.

Default mode is configured overall packet, with static literature as a separately named mode. No silent filled→static fallback. Required failures block final output; a user-authorized incomplete draft gets conspicuous incomplete status/cover and omissions. Supported raster images are converted to readable PDF pages before merge; unsupported/corrupt/encrypted documents are rejected with a clear reason. Keep AcroForm uniqueness/appearance handling; prove two differently filled copies of one template remain independent. Jobs retry from pinned sources; issued outputs never regenerate in place from changed templates. Download still reevaluates current user access.

### 3.9 API surface and compatibility checklist

Proposed service names are below; implementation may use equivalent names while keeping these contracts. New mutation APIs use authenticated POST/CSRF protection except the deliberately public informational generator. Each returns structured errors `{code,message,field_errors,retryable,request_id}` with no private identifier disclosure; forbidden/not-found behavior follows current domain policy. Include `expected_modified`/revision for editable resources and an idempotency key for creation/finalization/decisions. Validate current authorization even when returning an idempotent receipt.

| Existing wrapper or proposed API | Request / result contract | Policy and concurrency |
|---|---|---|
| Existing catalog list/detail | Existing paging/slug plus capability filters → versioned product projection, total/cursor and next action | Dealer/catalog capability for commercial projection; public projection separate; inactive/readiness consistent. |
| Proposed `product_readiness.check` / `approve` | Product + channel + expected fingerprint → field-level report / approved fingerprint | Check requires authoring read; approve requires channel approval capability and unchanged dependencies. |
| Existing family calculation wrappers → common calculate service | Normalized configuration → calculation result/token/fingerprint, no authoritative client price/BOM | No committed configured Item/BOM/schedule writes for preview. Public adapter strips private/commercial fields. |
| Existing builder/Desk/portal save → common save service | Inputs + context envelope + expected revision/key → build identity, Item/BOM, attached line and price scope | Schedule write or authorized parent-document write; current provenance/handoff rules retained; one atomic save. No generic client-selected `ignore_permissions`. |
| Proposed upload begin/finalize | Parent context/file metadata → private upload session; verified File IDs → receipt with stored file list | Verify bytes/ownership/parent scope; finalization idempotent. A generic upload success alone does not mark business submission complete. |
| Existing `request_schedule_quote` | Preserve schedule-only compatibility input initially; expanded intake/version/key → quote-request ID/state and receipt | Schedule editor; freeze intake scope. Legacy callers receive compatible `success` plus ID, never QUOTED. |
| Proposed quote list/detail/PDF | Scoped filters or offer ID → authorized current/previous offer read model and protected PDF | Dealer customer match plus staff capability; collaborators cannot read a commercial offer through shared schedule access. |
| Proposed quote respond | Offer ID/revision/hash, accept/decline/revise, note/key → response receipt and optional draft SO reference | Buyer capability; reject stale/expired/cancelled offer under lock. Revision request does not edit issued offer. |
| Existing `create_schedule_sales_order` | Schedule plus reviewed intake or legacy adapter → SO draft receipt, scope exclusions, intake state, `already_existed` | Separate authorized retrieval from create eligibility. New review flow mandatory when feature enabled; no approval by receipt. |
| Proposed staff order decision | SO/intake revision, decision, changes/reason → persisted review state or submitted order acknowledgment | Staff capability plus native ERP permission; material customer changes need acknowledgment. Native Desk submit uses identical guard. |
| Proposed drawing reply/review | Request + published deliverable revision/hash + comment/files/decision/key → receipt and next actor | Current request access plus reply/reviewer capability; immutable revision; stale review conflicts. |
| Proposed support detail/reply | Issue ID + authorized links/reply/files → customer-visible thread/status | Requester/customer scope; public-to-customer vs internal content explicit, server-enforced. |
| Proposed packet preflight/start/status | Schedule/version/mode/document selection → manifest; pinned manifest/hash/key → queued job; job → progress/outcome/download | Schedule access and pricing permission if applicable; worker revalidates source access/completeness; output is immutable and private. |
| Existing packet generation wrapper | Existing `generate_spec_submittal_packet` response compatibility during migration | Do not change an old synchronous `success + file_url` consumer into false immediate success. Add async endpoint, migrate callers, then retire/block old path explicitly if needed. |
| Proposed publish job claim / existing sync callbacks | Brand/worker lease → immutable operations; operation/hash/result → recorded staged/live/error facts | Integration capability, brand scope and compare-and-set hash; stale callback records outcome without clearing newer work. |
| Proposed workspace queue query | Named queue + filters/cursor → count, records, owner/age/next action | Same predicate as domain list/detail; errors distinct from count zero; no arbitrary SQL/filter field input. |

Record consumer migration in a small compatibility register: endpoint/global name, in-repo callers, installed n8n/embedded consumers, version introduced, removal gate. Include legacy configurator globals/routes, ordinal schedule line indexes, packet mode names, sync scalar fields and direct File URLs. Do not retire a shim based only on static dead-code analysis.

## 4. Delivery backlog, estimates and acceptance

Each story includes its regression/integration checks and local code review. Estimates are **engineering person-days, not elapsed days or fixed bids**, assuming an experienced Frappe developer and access to a prepared staging environment. They exclude content authoring volume, owner approval waiting, infrastructure procurement and prolonged legacy-data remediation. Ranges reflect source-level planning without live baselines; rescope after S0. Cross-cutting architecture in section 3 is normative for every story. Dependencies name prerequisites, not a prohibition on drafting independent UI or tests.

Business owners are accountable roles to assign to named people in S0: PO (product owner), QA, Sales, Engineering, Catalog, Integration, Operations, Support and Release. Engineering implementation/QA owns technical execution throughout. Every story must demonstrate both the happy path and denied/failure/retry behavior. Do not close a story solely because a control appears.

### S0 — Baseline and release contract

Owner: PO + QA + Release. Dependencies: none. Source-confirmed S1/S4 investigation can proceed without waiting for production access.

| Story / effort | Implementation work to prepare | Acceptance evidence |
|---|---|---|
| S0.1 Deployment and policy baseline — 2–3 days | Record app/Frappe/ERPNext commits, built asset versions, active hooks, Custom Fields/DocPerm, Website User types, workflow overrides, installed n8n exports, Webflow field/brand/embedded-script bindings, storage/CDN and workspace overrides. Compare with checkout. Record named owners and supported SKU/family/action register. | Reproducible staging version manifest; every F01–F32 classified confirmed/source-only/live-different/pending with owner. No production mutation required. |
| S0.2 Acceptance fixtures and baseline — 2–4 days | Seed two unrelated dealers, multiple buyers, non-dealer company member, VIEW/EDIT collaborators, sales/engineering/catalog/operations users and admin. Add mixed-family, mixed-manufacturer, legacy sheet, quote/order, private file and incomplete product fixtures. Run existing server suite; reproduce password, checkbox, order retry and actual file authorization in browser. | Results distinguish prior failures from new regressions; screenshot/network evidence for reported UI defects; seed data reset instructions and test IDs. Capture installed ERP reservation semantics. |
| S0.3 Test harness and diagnostics — 2–4 days | Add proposed `tests/portal_e2e/` browser harness with separate actor sessions and staging-only test data; CI service/web/worker setup, network failure injection and trace artifacts. Record p95 page/configure/export baseline and production-sized list dataset. | CI opens portal and Desk with real assets, proves dealer A/B isolation, and executes one seeded save/reopen path. Credentials remain CI secrets; traces exclude passwords and private file contents. |

### S1 — Broken promises and urgent privacy/retry fixes

Owner: PO + Support; Catalog for mapping; Engineering for files. Dependencies: source diagnosis plus S0 test environment for release. Does not certify unresolved S4 product builds.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S1.1 Password and truthful account actions — 2–4 days | Inspect `account.html::changePassword`, browser loaded framework APIs and installed password endpoint. Repair actual runtime cause; add submitting/error/expired-session handling and password mismatch feedback. Keep framework password policy/recovery, not custom credential storage. Replace fake irreversible deletion with support-assisted account-closure intake; replace misrouted company creation with accurate profile/access request. Remove unapproved response-time promises. | Real dealer changes password then signs in; wrong current/weak/mismatch/session-expired cases are actionable. No password in logs. Company action does not call end-client `create_customer` under false labeling. Closure preserves business records and produces a receipt. |
| S1.2 Catalog contracts and safe handoff — 2–4 days | Correct `product_catalog.py` projections from schema; resolve certification masters; validate options JSON; hide unavailable URLs rather than `#`. Add active-product direct lookup check. Replace broken embedded call in `product_detail.js` with correct family preselected `/portal/configure` handoff as first slice; preserve context and error recovery. | Direct contract tests verify populated names/files/options and missing-data behavior. Active fixture/tape/neon/sheet routes open the correct product; inactive slug is unavailable through direct detail. No unrelated family form. |
| S1.3 Real file intake and replacement — 4–7 days | Shared upload service/UI under `portal/files.py` and proposed `public/js/portal_uploads.js`; integrate drawings, `ill_support.html`, OTHER-line add/edit. Create resumable draft parent; upload bytes privately; validate File ownership; finalize request only with successful required uploads. Stop OTHER callbacks from saving as if failed upload succeeded. | Two PDFs and image arrive with matching checksums; disconnect/oversize/denied ownership give per-file error; request not falsely submitted; replacement failure leaves prior spec unchanged. Forged File ID/URL rejected. Optional incomplete draft visibly marked. |
| S1.4 Private file access and historical inventory — 3–5 days | Replace public request creation/list filter in `document_requests.py`; align native File permissions with intended request/revision access and export service. Inventory legacy public references and implement dry-run migration/report using section 6. Public Webflow project-metadata path gets immediate authenticated-private containment. | Native URL/custom endpoint/metadata tests deny guest, dealer B, revoked collaborator and unpublished deliverable access. Approved owner can retrieve every migrated sample. Legacy source files are not deleted until checks pass. |
| S1.5 Honest quote receipt and idempotent order retry — 4–7 days | In schedule controller and `portal.create_schedule_sales_order`, separate actor authorization from create-state eligibility, retain lock/rollback and authorized existing-order return. Remove quote-ready notification from quote intake; land the minimal durable quote-request model/service from section 3.4 now, with S6 enhancing it. Prevent manual QUOTED transition without issued offer. | Existing two duplicate-conversion tests pass on Bench; add concurrent separate-session requests, denied actor, cancelled order and failed BOM rollback. Quote request has durable ID/status and no issued-offer claim. Email failure preserves receipt. |

### S2 — Catalog, shared portal and account foundations

Owner: Catalog + PO. Dependencies: S1.1/S1.2; S1.3/S1.4 for private account artifacts.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S2.1 Complete product projection/detail/discovery — 4–6 days | Add shared projection mapper, typed family capabilities, ordered units/spec groups, features/dimensions/compatible-product data, document precedence and family-specific price labels. Extend `product_catalog.py`, `product_catalog.js`, `product_detail.js` and catalog templates. Search model/series, useful family filters, bounded pagination and missing/retired states. | One approved product per family and standard Item matches source values/units; filtered paging total stable; no non-dealer price exposure; no zero for missing price; all document actions usable. Catalog owner signs off launch product register. |
| S2.2 Shared portal shell and interaction states — 4–7 days | Extend `public/css/portal.css`, `public/js/portal.js`, reusable includes and page layouts. Converge navigation/breadcrumb/header/buttons/status/form errors/loading/empty states incrementally; remove replaced inline rules only from migrated pages. Define dialog focus/keyboard/mobile patterns. | Main discovery/account/project/schedule flows work at 390×844, 768×1024, 1440×900; keyboard focus returns after modal close; errors announced/readable; no hidden horizontal primary action. Before/after screenshots approved. |
| S2.3 Account/team/address lifecycle — 5–9 days | Extend `portal.py` profile/preferences/user invitation foundations via proposed account service and intake records. Verified company linkage, dealer application triage, one-use scoped invitations, revoke/disable, purchasing contact selection; authorized Address/Contact CRUD with ownership checks and review for sensitive changes. | Inviter cannot grant foreign company, administrator or System User rights; invite replay/expiry/revocation fail; same-company non-dealer permissions preserved; disabled member loses access but historic approvals remain attributed. Addresses supplied to S6 belong to approved customer context. |
| S2.4 Picker and workspace foundation contract — 2–3 days | Define common card data/select API for templates and standard Items; reuse `renderTemplateCards` including search/selection/image fallback, add cleanup and keyboard semantics. Define Add Line draft context and workspace task-group destination register. S3 implements picker; S8A completes queues. | Design/contract fixtures cover four families, accessory, OTHER, missing image and no results. Fixture designation/location/quantity/notes survive selection changes in a prototype/test fixture; every future workspace target has an owning story. |

### S2A — Authoring and n8n/Webflow publication

Owner: Engineering + Catalog + Integration. Dependencies: S0 inventory, S2.1 projection. Contract delivery precedes S3/S4A integration; their final acceptance completes downstream readiness, avoiding a circular prerequisite.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S2A.1 Family readiness engine — 5–9 days | Extend template controllers without forbidding incomplete drafts. Add `product_readiness.py` and channel gates; reuse `guardrail_audits.py`. Check linked Items/specs/options, active compatibility maps, dimensional/electrical rules, price scope, imagery/specifications/documents/certification applicability and PDF mapping prerequisites. Resolve affected products when shared dependencies change. | Each family has valid/incomplete/incompatible samples with record+field remediation. Invalid draft saves but cannot be approved/published for failing channel. Dependency change invalidates old approval. Readiness never modifies historical build/offer snapshots. |
| S2A.2 Authoring/import/generator parity and preview — 4–7 days | Update Desk forms/setup guides, fixture-builder generators and import validation contracts. Build source→portal→CMS→PDF mapping register. Provide product preview, allowed-choice preview, sample configuration/PDF preflight and affected-product report. | Staff creates representative fixture/tape/neon/sheet and variant driver/controller products through supported paths; bad data cannot bypass readiness via CSV/import. Generated fixtures/schema contracts validate; no developer edit needed to correct normal content. |
| S2A.3 Revision-aware publishing workflow — 7–12 days | Add publish-job/per-brand hash state; capability-gated API claim/export/ack/error/publish/retire services behind legacy wrappers. Complete checked-in n8n product workflow, dependency ordering, bounded batch loop, credentials per brand, executable error branches and retry/backoff. Remove environment URLs from transform constants into approved configuration. | >50 products (test 123), create/update, 429/timeout/validation failure, duplicate callbacks, crash after remote create, concurrent local edit, two brands and retirement all reconcile. Old callback cannot clear new pending revision; no duplicate CMS product; staged success never claims live. |
| S2A.4 Operational publication/reconciliation — 3–5 days | Readiness/pending/failed/stale views, execution links, safe retry and reconciliation of ERP projection hash vs staged/live state. Verify installed CMS fields/embedded script on staging and approved live publication in later release task. | Integration owner resolves missing dependency and retries from workspace. Unauthorized dealer cannot invoke status callbacks. Last-good live content survives failed update; inactive product retirement reaches remote target. Runbook records credential/trigger ownership. |

### S3 — Configuration parity and visual Add Line

Owner: PO + Engineering. Dependencies: S2 capability/UI contract. S4 computes final correctness; use explicit contract fixtures while it is developed. Do not expose a save path before its corresponding S4 checks pass.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S3.1 Shared request/state/lifecycle — 5–8 days | Introduce `configuration_contract.py`; extend Base instance lifecycle, unique IDs/label targets, scoped events and teardown, request sequence/fingerprint guards. Converge inline coordinator and family classes behind normalized adapters without rewriting geometry. Document deprecation wrappers and supported mode links. | Same inputs normalize identically in wizard/coordinator/Desk. Power string false remains false. Any material input disables save until recalculated. Delayed responses after edits/close cannot mutate another modal. First-open/reopen/label/Space checkbox tests pass. |
| S3.2 Four-family save/reopen parity — 5–9 days | Extend `configured_product_builder.py`, `desk_configurator.py`, family classes/forms and `configure.py/html`; preserve tape segments/reels, neon feeds, linear corners/jumpers, sheet areas, power and max-run override where applicable. Add sheet adapter into common orchestration using existing `_save_led_sheet`. Adapt legacy routes and React discovery handoff. | Catalog/main portal/schedule edit/Quotation/Sales Order round trips retain all values and return context. Bulk reels remain distinct. Unsaved parent, Cancel, Back and Add another leave no unexplained schedule duplicates; parent-save warning is accurate. |
| S3.3 Visual schedule Add Line — 4–7 days | Replace modal discovery dropdown experience with existing shared card picker driven by product capabilities; keep hidden select compatibility initially. Store draft context independent of product filter/selection. OTHER remains manual entry; standard Item opens quantity selection; configuration Save attaches once to stable line key. | All four families plus accessory/OTHER pass search/filter/thumbnail/selected/fallback/keyboard/mobile tests before selection. Configure/back/cancel preserves designation/location/quantity/notes; cancelled new configuration does not create an unintended line; duplicate submit attaches once. |
| S3.4 Public Webflow and entry-point adapters — 4–7 days | Add explicit sheet dispatcher/generator and sheet required selections in `webflow_configurator.py`, `spec_sheet_generator.py`, `webflow_spec_sheet_download.js`. Use same option meanings and channel readiness; retain selections during authenticated handoff. Remove active wrong-family/dead kit links or route to inquiry. | Installed staging Webflow page works for every advertised family; public informational PDF contains supported selections with correct classification. Project labels use private route; no dealer price leak. Public→portal asks for missing ordering fields and preserves existing selections. |

### S4 — Commercial and manufacturing correctness

Owner: Engineering + Sales + Operations. Dependencies: start diagnosis with S0; final implementation uses S3.1 normalized contract and S2A master-data checks. P0 work is not deferred until a fourth calendar sprint.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S4.1 Boolean/unit normalization and complete identity — 4–7 days | Complete contract parser and identity in both API/controller fallback paths. Include power/override/control/dimensions and resolved dependency versions. Distinguish build identity from customer pricing; create new immutable variants rather than mutating reused hashes. | True/false/0/1/string/null cases; inches/feet/mm equivalence; invalid finite checks. Included/excluded variants and different sheet areas resolve distinct builds/Items/BOMs; old approved order remains unchanged after new save/master edits. |
| S4.2 Common electrical planner — 7–12 days | Replace schema-invalid tape/neon loader with `driver_spec`, `voltage_output`, `input_protocols`, linked tape spec and validated eligibility. Common planner uses actual circuit watts, usable load, output/channel capacity and supported topology. Prefer feasible one supply, then minimum count with deterministic tie-break. Persist power before configured-record save. | Unequal 20W/100W runs are never sized by 60W average; total/per-output overload tests; missing/incompatible supply blocks included-power save. Excluded mode shows requirements without requiring a selected purchasable driver or adding rows. Engineering approves allocation/reference cases. |
| S4.3 Cables and common component manifest — 5–9 days | Repair `build_fixture_bom_items`, tape/neon BOM and sheet BOM adapters. Enable linear leaders, preserve tape segment leaders, validate neon jumper ownership, fixed-vs-bulk cable Item semantics and stock UOM conversion. Drive prospective BOM and stock from same manifest. | 72-inch bulk leader produces 6 Foot or 1.8288 Meter before defined rounding; `Nos` resolves correct fixed assembly or fails clearly. Each physical jumper appears once; quantity >1 scales all included parts exactly once. No source comment is accepted as evidence of actual supply rows. |
| S4.4 Sheet bundling, prices and pinned artifacts — 6–10 days | New sheet saves bundle panels/power/cables and use full build Item identity; remove automatic sibling rows in new mode. Legacy resync targets stable schedule-line ownership. Numeric component price quantities and bundle total include power once; use ERP price-list/customer/UOM rules for estimates and issued pricing. Persist transaction `ill_bom`/snapshot; audit artifact reuse/failure rollback. | Two identical sheet lines edit independently; one dimension/power change cannot reuse wrong Item/default BOM. Compare portal estimate vs ERP transaction using identical pricing context; scope differences explicit. Failed save leaves no partial linked artifacts. Approval never retroactively reprices. |
| S4.5 Inventory and engineering reconciliation — 4–7 days | Constrain `pricing_utils._eligible_warehouses` to intended ERP company and `ilL-Stores`; no match returns unavailable with action, not all warehouses or misleading zero. Retain reservation/shared-demand/quantity logic. Verify installed submission reservation and distinguish assembled finished stock from component availability as applicable. Audit automatic linear work generation and standard planning for other families. | Shared-component shortages across mixed lines, excluded warehouse, duplicate warehouse name across companies, negative/zero quantities and quantity scaling pass. Browsing/draft request creates no reservation; submit/cancel follows ERP policy. Signed reference manifest reconciles configuration/price/stock/BOM/production instructions. |

### S4A — Filled PDFs and complete mixed-manufacturer packets

Owner: Engineering/document owner + QA. Dependencies: S1 files; S2A mapping/readiness; S3/S4 selected-build correctness. OTHER-line support can start earlier; grouped output completes after S5.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S4A.1 Line-document model and manual specification workflow — 4–7 days | Add top-level line-document records/stable line keys and metadata for primary/additional specs. Extend add/edit/duplicate/version APIs and UI while preserving all current OTHER fields. Add per-line readiness and PDF/JPEG/PNG ingestion/validation; convert offered raster formats before assembly. | OTHER manufacturer/model/trim/housing/driver/lamp/dimming/voltage/finish plus qty/location/notes survive duplicate and schedule revision. Failed replacement preserves old file; new duplicate association is independent. All documents stay project-authorized. |
| S4A.2 Mapping validator and filled-output fidelity — 5–8 days | Validate field existence/uniqueness, mappings, units/transforms/required engineering values and template hash; keep family generators and field uniqueness/appearance safeguards. Consume pinned selected-build and line metadata instead of shared current configured-record file cache. Complete sheet/public consistency with S3.4. | Representative/boundary PDFs for all advertised families and driver/controller variants; long labels/multiple pages/checks/optional blanks. Two differently filled copies of same template retain distinct values in browser and print rendering. Missing required value is a structured failure. |
| S4A.3 Packet preflight, manifest and truthful jobs — 5–9 days | Extend `spec_submittal.py`, exports and Export Job with modes, immutable source manifest, per-line status/page index and background generation/progress. Default overall packet includes schedule/cover/index, filled ilLumenate and OTHER selected specs in schedule order. Do not choose arbitrary newest accessory PDF; use approved source registry. | Mixed fixture/tape/neon/sheet/accessory + two OTHER packet is complete/readable; missing/corrupt/encrypted/mapping-failed input cannot be COMPLETE or cover-only success. Explicit partial draft has INCOMPLETE status and omissions. Repeated designation still maps every line. |
| S4A.4 Issued packet history and grouped closure — 3–5 days | Add issue/freeze action and retained output hash/manifest; retry pinned sources; group summary/member pages after S5. Ensure schedule revision/new upload affects only future packets. Run private file tests and output visual review. | Earlier issued packet bytes/checksum unchanged after file/template/schedule edits. Group members/power are readable and match BOM; generated single downloads and packet agree. Revoked/unrelated user denied historic private packet. |

### S5 — Independent grouped configurations

Owner: Engineering. Dependencies: S3 contract/state, S4 identity/power/manifest. Adopt detailed grouping-plan scenarios as requirements, with current-source verification completed in S4.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S5.1 Aggregate schema and atomic compute/save — 6–10 days | Add group/member/allocation schema, group orchestrator and attach/read policy. Pure preview of each member, common group power plan, stable nested member/segment identity, bounded supported group size, server idempotency/concurrency. No engine commit inside group transaction. | Failed member/BOM/save rolls back group and links; incompatible shared options rejected; one-member adapter matches intended single behavior; adding/reordering/removing members recalculates without dropping topology. |
| S5.2 Shared member UI and bundle artifact — 6–10 days | Member editor integrated into all scoped family forms, portal and Desk; separate independent fixture vs add jumper; sheet coverage areas; one power toggle/override where allowed. Flatten canonical components into one parent configured Item/BOM and keep member cut/feed manifest. | L1 example: leaders 6/3/2 ft, fixture lengths 20/5/25 ft produce 11 ft entered leaders and 50 ft requested fixtures per group; quantity 2 doubles those and copies supply plan, without upsizing across copies. Internal jumper counted once; run-split extra feeds shown separately. |
| S5.3 End-to-end group dispatch and regression — 5–9 days | Extend schedule summary/duplicate/version/status, quotation/SO row construction, price/stock, export/PDF/traveler and planning consumers before singular-link branches. Use pinned group BOM; only appropriate linear grouping enters automatic manufacturing path. | One group commercial line survives schedule→Quotation→SO→appropriate manufacturing/planning with exact quantity and members. Four families save/reopen in portal/Desk. Legacy single/jumper/reel/exploded-sheet remains readable; no public group toggle before all consumers pass. |

### S6 — Quote/PO intake, review and staff approval

Owner: Sales + PO + Operations. Dependencies: S1.5 receipt; S3/S4 supported build contract; S5 for grouped scope; S1 private files. Design can start earlier. No implementation may replace draft SO as the order request.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S6.1 Quote intake/staff queue — 5–8 days | Extend S1 quote-request record with frozen scope, contact/timing/notes/files, assignment, information-needed/replies and due dates. Add staff list/report and quote preparation using `quote_from_schedule.add_schedule_to_quotation`, which delegates to the schedule controller's `append_quote_lines`. Update non-dealer technical-request behavior without exposing prices. | Request revision retains original; repeated submit yields one receipt; staff works without System Manager. Request contains schedule version and explicit sellable vs SPEC_ONLY scope. Non-dealer editor cannot obtain issued commercial terms. |
| S6.2 Issued-offer portal and response — 6–10 days | New `/portal/quotes` and detail controllers/templates plus `portal/quotes.py`. ERP Quotation submit/amend/validity, immutable issued snapshot/PDF, supersession and accept/decline/revision request. Gate actual issued event instead of generic QUOTED. Implement guarded reconciliation for failed schedule bookkeeping. | Valid offer accepted once into draft SO path; expired/superseded/cancelled/wrong-customer offer cannot be accepted. Material change requires new acknowledgment. Quotation PDF and portal agree; no production triggered by acceptance. |
| S6.3 Direct PO and order-review intake — 6–10 days | Extend existing conversion API with reviewed intake envelope: PO no/file, customer-authorized addresses/contacts, requested date, receiving/shipping instructions, reference docs and displayed-scope acknowledgment. Show exclusions. Pin quoted rates through ERP conversion when quote-led; direct requests show estimate subject to staff approval. | Direct PO and quote-led paths produce one durable draft SO; retries with same key/body return receipt, changed body conflicts. Validation/retry preserves uploads. OTHER lines remain in schedule/packet and are explicitly excluded from sellable request unless separately authorized resale. |
| S6.4 Staff capabilities, review/approval guards and events — 5–9 days | Map job roles, role/type/install migrations and before-submit guards; implement request information/changes/reject/withdraw/approve. Require authorized staff to set confirmed delivery date; record approval time/by and issue immutable acknowledgment. Preserve ISSUE behavior; prevent stale accepted terms; handle existing draft native Desk submissions under same rules. | Dealer cannot submit through UI/API/standard endpoints; sales configures/prepares without global admin; approver sees scope diff and valid intake. Rejected request reaches ISSUE and explicit replacement path; cancellation/deletion lifecycle tested. Late mail failure does not undo approval. |
| S6.5 Standard products and commercial field lineage — 3–5 days | Driver/controller/accessory/eligible kit quantity request resolves approved Item/variant. Unsupported configuration gets engineering inquiry. Verify `ill_section_label`, `ill_fixture_type`, notes, configured links/BOM/snapshots through Quotation→SO→Delivery Note/Sales Invoice and relevant print formats. | Every launch product has working next action; no absent configure-kit page link. Standard sellable line prices/plans correctly; fixture designation printed above, notes below, room grouping preserved, no duplicate notes. No supplier Purchase Order feature added. |

### S7 — Drawing collaboration

Owner: Engineering/drawing team. Dependencies: S1 files/access; S0 review policy. Can develop alongside S3–S6; associated-order linking uses S6 access model.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S7.1 Request/reply and assignment — 4–7 days | Extend `ilL-Document-Request`, `document_requests.py`, `drawings.html`, `drawing_detail.html`; intake purpose/type/project/schedule/order links, private public-to-customer replies, internal notes, owner/due date, customer action state. Preserve existing request type/SLA/Task automation. | Staff asks question; customer privately replies/uploads; correct party-to-act and assigned staff queue update. Wrong-company references rejected; internal notes/files absent from portal/notifications. |
| S7.2 Revision publication and technical review — 4–7 days | Stable immutable deliverable revisions, publication action, supersedes link and authorized reviewer decisions. Add approve/request-changes endpoints bound to revision hash and comments; stale/current guard and idempotent decision receipt. | Revision 1 published→changes requested→revision 2 approved; old/unpublished revision cannot become current approval. New revision clears current approval need, preserving prior decisions. Both list/detail and native file permissions agree. |
| S7.3 Configuration impact and production release — 3–5 days | Link drawing review to schedule/build revision. On material build change create reapproval/engineering-review task; define production hold/release check independent of customer acceptance and SO approval. Add due/overdue/unassigned views and brief staff/dealer guidance. | Approved drawing plus changed build cannot silently remain released. Ordinary engineering user handles task from workspace; operations sees hold/release evidence. No unauthorized automatic production release. |

### S8 — Order follow-up, support and notifications

Owner: Operations + Support + Sales. Dependencies: S6 states/events; S7 links; S1 upload service.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S8.1 Accurate order history/read model — 5–8 days | Extend `portal/orders.py`, `status.py`, orders/detail templates with scalable search/filter/paging, actual approval event, requested vs confirmed vs estimated dates, line demand/production/fulfillment coverage and partial shipments. Keep maintained DN tracking fields and protected document downloads. | One produced line plus one unstarted line is not globally production-complete. No-WO standard items follow their planning/fulfillment path. Partial delivery/returns/cancelled records and invoice issued vs paid remain distinct. Date defaults never appear as confirmed promise. |
| S8.2 Change/cancel/reorder and linked support — 5–8 days | Proposed linked order-change request record/service, current-revision diff/decision, reorder-to-new-draft. Extend existing Issue with authorized references and private detail/reply/attachments/resolution/reopen path; paginate beyond five tickets. Avoid new return-credit automation. | Buyer proposes change and follows staff outcome while original acknowledgment remains unchanged; reorder reprices/revalidates current product. Support reply loop works for related order/project; foreign order attachment/ref rejected; no false 24-hour promise. |
| S8.3 Durable recipient/event delivery matrix — 4–7 days | Implement shared event/recipient resolver and per-recipient enqueue ledger using Frappe Email Queue, preferences, retry/escalation and accessible links. Integrate S6/S7/domain hooks; delete duplicate legacy sends only after coverage. Record suppressed/skipped/queued/failed/delivered distinctions accurately. | Staff-created SO notifies intended dealer buyer/contacts, not merely staff owner. Duplicate hook/retry enqueues once per event+recipient. Revoked contact filtered before delivery; preference test passes; email outage visible in staff queue while business operation succeeds. |

### S8A — Staff Desk workspace

Owner: PO + department leads. Dependencies: S2 navigation contract, role model, queues from S2A/S4A/S6–S8. Deliver links and queues incrementally, not all at release end.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S8A.1 Setup paths and safe workspace migration — 2–4 days | Extend exported workspace JSON and applicable fixtures/setup guides. Include sheet template/configured sheet, driver/controller templates and mappings, all family dependencies, readiness/sample PDF, catalog/brand/export operations. Back up and compare existing site overrides before merge. | Every visible shortcut/guide resolves for authorized staff on both fresh site and upgraded copy; existing useful links retained. Custom workspace override strategy is documented and repeatable. |
| S8A.2 Action queues and live counts — 4–6 days | Role-filtered cards/reports/quick lists for quote requests, draft SO review, information needed, drawing response/reapproval, Issue response, failed/incomplete export, failed/stale publication, account intake, production exception and overdue/unassigned tasks. Use shared server predicates; no copied state definitions. | Count equals drilldown for each role; forbidden/loading error differs from zero; no cross-company/financial data through direct report API. Financial cards only visible and callable by authorized roles. |
| S8A.3 Staff task walkthrough/training — 2–4 days | Complete sales quote/PO review, engineering drawing response, catalog sheet authoring+sample PDF, integration failed-sync retry and support incomplete-packet resolution from `/desk/illumenate-lighting`. Record department ownership/absence coverage and maintain navigation checklist. | Ordinary job roles finish tasks without System Manager. Result changes correct queue and portal state. New and upgraded workspace tests pass; no dead card destination. |

### S9 — Migration rehearsal, pilot and release readiness

Owner: Release + PO + QA; each business owner signs their reference outputs.

| Story / effort | Concrete changes and files | Acceptance evidence |
|---|---|---|
| S9.1 Full rehearsal and release artifacts — 3–5 days | Run section 6 migrations against sanitized production-shaped clone and fresh site; migrate/build/test and restore drill. Capture contract/browser/PDF/publishing/permission results, counts/hashes and known deferrals. | No lost history, silent permission expansion, false packet completion or stale publication. Approved-record checksum/rate/BOM comparisons pass; rollback proven before dealer rollout. |
| S9.2 Dealer/staff pilot and performance — 3–5 days | Representative dealer cohort and unfamiliar user; all declared families plus grouping, Add Line, mixed packets, Webflow authored product and staff review. Measure scenario completion, corrections, timings and operational queue aging. | 100% mandatory scripted cases; target ≥90% unassisted pilot completion with sample size, no critical error hidden by average. Performance targets validated/adjusted from S0, not invented after failure. |
| S9.3 Rollout/operating handoff — 2–4 days | Per-family/cohort flags, release checklist, owner signoffs, alerts/runbooks, support instructions, previous assets/schema compatibility and post-release checks. Hand off maintained field mapping and workflow exports. | Zero unresolved P0; no P1 failure in declared core journeys; all channels/families visibly supported or explicitly owner-approved inquiry-only. Staff can resolve failed sync/export/email/manufacturing without developer intervention. |

## 5. Traceability, dependencies and proposed releases

### 5.1 Finding coverage

All findings remain applicable to this checkout unless qualified below. “Source confirmed” does not mean reproduced in production. Owners are accountable business roles; story tests provide the exit evidence.

| Finding | Primary stories / owner | Required closing proof |
|---|---|---|
| F01 password | S0.2, S1.1 / Support | Actual Website User password/recovery and expired-session browser tests; root cause documented. |
| F02 document fields | S1.2, S2.1 / Catalog | Child-schema projection contract and working downloads. |
| F03 certifications/options | S1.2, S2A.1 / Catalog | Linked master resolution, typed JSON options, applicability. |
| F04 technical context | S2.1 / Catalog | Units/group/order/features/dimensions and correct price basis. |
| F05 catalog handoff | S1.2, S3.2 / PO | All four family preselection and preserved return context. |
| F06 publication/ownership | S2.1, S2A.1 / Catalog | Active/readiness direct-route parity and document source register. |
| F07 drawing uploads | S1.3, S7.1 / Engineering | Uploaded bytes/checksums/receipt, interrupt/retry. |
| F08 support | S1.3, S8.2 / Support | Files plus customer reply/resolution loop. |
| F09 public project files | S1.4 / Engineering + Release | Historical relink/removal report and unauthorized native download denial. P0. |
| F10 drawing review | S7.1–S7.3 / Engineering | Revision-specific changes/approval/reapproval/release workflow. |
| F11 request vs issue | S1.5, S6.1–S6.2 / Sales | Durable request; no QUOTED/ready claim before issued offer. |
| F12 issued quotations | S6.2 / Sales | Version/expiry/PDF/response and quote-led draft SO. |
| F13 retry guard | S1.5, S6.3 / Sales | Existing tests plus real concurrent separate-session conversion. |
| F14 thin intake | S6.3–S6.4 / Sales + Operations | Review packet, validated addresses/contact/PO, staff decision. |
| F15 date promise | S6.4, S8.1 / Operations | Requested/estimate/confirmed date distinction and real approval time. |
| F16 parity | S3.1–S3.4 / Engineering | Contract and browser round trips; no dropped segments/reels/power. |
| F17 power/cables | S4.1–S4.5 / Engineering | Engineering reference reconciliation, correct UOM/power BOM and price. P0. |
| F18 identity/sheet ownership | S4.1, S4.4, S5 / Engineering | Distinct builds/Items and independent line edits; historical snapshot tests. P0 validation gate. |
| F19 stock scope/coverage | S4.3, S4.5 / Operations | Leaders included, ilL-Stores-only, shared demand/reservation/UOM proof. |
| F20 recipients | S8.3, S6.4 / Sales | Staff-created order reaches validated customer contacts. |
| F21 order facts/actions | S8.1–S8.2 / Operations | Mixed-line coverage, partial shipments, actual dates and change requests. |
| F22 account affordances | S1.1, S2.3 / Support | Verified account/company workflow and truthful closure process. |
| F23 staff access | S0.1, S6.4, S7, S8A / PO | Ordinary staff task completion, restricted direct APIs and portal-only dealers. |
| F24 standard buying paths | S2.1, S3.4, S6.5 / Sales | Standard Item quantity or explicit inquiry for every launch product. |
| F25 interaction quality | S2.2, S3 and every UI story / PO | Responsive/keyboard/visual acceptance, documented runtime evidence. |
| F26 test coverage/readiness | S0.2–S0.3, all story tests, S9 / QA | Fresh/upgraded Bench, real browser, PDF and integration evidence. |
| F27 visual Add Line | S2.4, S3.3 / PO | Compare before select, all families/OTHER, context/back/cancel/keyboard. |
| F28 OTHER specs/packet | S1.3–S1.4, S4A, S6.3 / Engineering | Private uploads/replacements and complete mixed packet; excluded sale scope visible. |
| F29 authoring readiness | S2A.1–S2A.2, S4 / Engineering + Catalog | Validated DocType/import/generated inputs, dependency invalidation and previews. |
| F30 n8n workflow | S2A.3–S2A.4 / Integration | >50, revision race, failure/retry/create reconciliation, staged/live and brand tests. |
| F31 filled public output | S1.4, S3.4, S4A.2–S4A.4 / Engineering | Sheet public route, private project metadata, explicit static fallback and rendered fidelity. |
| F32 workspace | S2.4, S8A.1–S8A.3 / PO + leads | Real role task queues/counts/links, fresh/upgraded workspace walkthrough. |

The four follow-ups are explicit release gates: F27→S3.3; F28→S4A.1/S4A.3; F29–F31→S2A/S3.4/S4A.2; F32→S8A. No standalone cosmetic acceptance substitutes for those end-to-end tests.

### 5.2 Effort summary and sequencing

| Increment | Engineering days | Main prerequisite / release role |
|---|---:|---|
| S0 | 6–11 | Baseline and test infrastructure |
| S1 | 15–27 | Immediate reliability/privacy receipt slice |
| S2 | 15–25 | Catalog and shared interaction/data contract |
| S2A | 19–33 | S2 projection; closes publishing gate |
| S3 | 18–31 | S2 contract; aligned with S4 computation |
| S4 | 26–45 | Begin investigation at S0; correctness before ordering |
| S4A | 17–29 | Files/readiness/builds; grouped closure after S5 |
| S5 | 17–29 | Stable S3/S4 contract and manifests |
| S6 | 25–42 | Correct builds/files/roles; group route requires S5 |
| S7 | 11–19 | S1 file/access foundation |
| S8 | 14–23 | S6 events and S7 links |
| S8A | 8–14 | Built incrementally as actual queues ship |
| S9 | 8–14 | All declared release gates |
| **Total** | **199–342** | Sum of 49 story estimates; not a calendar commitment |

Budget contingency after S0 for unresolved data/deployment findings; do not add an arbitrary fixed release date. The full scope is a substantial multi-release program, even when implementation assistance accelerates code writing. Content review and real engineering acceptance cannot be estimated from source alone. For staffing, independent workstreams can be catalog/publishing, configuration/correctness, and commercial/documents, with shared QA/design; this describes future team organization, not agent delegation performed in this planning task.

Proposed merge/release order:

1. **R0 groundwork:** S0 fixtures/version baseline; central contract proposals approved by engineering; file/privacy and S4 probes start immediately.
2. **R1 reliability:** S1 fixes and required additive schema. Ship only after affected actor/file/retry tests; do not expand configuration ordering claims.
3. **R2 discovery/content:** S2, S2A channel gates and S3.3 visual Add Line. Public configuration can stage behind capability flags while build/PDF gates finish. Workspace navigation arrives with these features.
4. **R3 build correctness:** S3/S4 common contracts, pinned snapshots/Items/BOMs and S4A non-group PDFs. Enable family-specific configuration beta only after reference reconciliation.
5. **R4 grouped and commercial:** S5 and grouped S4A closure; S6 quote/PO review/approval. Single-family/single-configuration pilot may precede grouping only if visibly scoped; final grouping commitment remains.
6. **R5 project service:** S7/S8 plus completed S8A operating queues; these can merge independently once access/events are stable.
7. **R6 full pilot/release:** S9 cross-system acceptance and signoffs. Do not treat a successful ERP deployment as evidence that n8n/Webflow embeds/workspace overrides are deployed.

Land contract/schema changes before callers; keep backward-compatible wrappers and feature flags during each transition. S2A can complete export/readiness contracts while S3/S4A consume test fixtures; final configured/PDF readiness only turns green after actual consumer tests. This breaks the potential circular dependency without weakening release criteria.

## 6. Data cleanup and migration runbook

Each migration is idempotent, checkpointed and supports a read-only report first. Implementation should add numbered patches under `illumenate_lighting/patches/` and register them in `patches.txt`, using the existing custom-field/permission installation pattern. Avoid dumping all site Custom Fields or replacing all workspace customizations merely because `hooks.py` exports those fixture types.

| Stage | Specific actions | Verification / safe reversal |
|---|---|---|
| M0 inventory and backup | Snapshot DB, public/private files, assets, enabled flags, installed workflow JSON, Webflow per-brand IDs/live state, workspace/Custom DocPerm overrides. Count affected objects and capture approved SO/Quotation amounts, configurations, BOM links and issued file hashes. | Tested restore on clone; baseline manifest stored privately. No migration until missing backup components are resolved. |
| M1 expand schema and roles | Add nullable fields, new request/event/document/job/group DocTypes, indexes and capabilities. Backfill stable line keys while preserving child names and transaction refs. Add API adapters before UI switches. Correct dealer fresh-install role setup and existing role/user-type policy with explicit site exceptions reviewed. | Fresh install and repeated upgrade pass. Ordinary staff permissions are least privilege; dealer portal works and Desk remains unavailable. Rollback disables new writers but retains readable schema/data. |
| M2 product/document data register | Identify bad/missing document URLs, malformed option JSON, mismatched family links, incomplete engineering references, duplicate slugs, missing images and mapping fields. Assign owners; repair authoritative source, not blank presentation text. Backfill channel status as unreviewed, not automatically approved. | Every launch product manually reviewed and reference-configured. Preserve existing publication until planned cutover unless urgent confidentiality/incorrect-sale containment requires disabling affected action. Record exact repaired values/revisions. |
| M3 private files and line documents | Build all-reference map, handle shared-file deduplication, validate byte hashes, create private copies and line associations, update active references, verify authorized access, remove old public copies/caches using migration manifest. Preserve previous issued packet bytes and document lineage. | Guest/foreign/revoked/native File tests for old and new URLs. Partial failed migration resumable. Never reverse a privacy fix by making customer files public again; fix forward or hold downloads pending repair. |
| M4 quotes/order status reconciliation | Match historical QUOTED schedules to submitted/current Quotations, amendments/cancellations, draft/submitted SOs and evidence. Create legacy intake links where determinable; flag ambiguous records for Sales. Backfill approval timestamp only from trustworthy event history; otherwise display unknown. Separate legacy 30-day default from confirmed promise. | Reconciliation report has counts and unresolved cases; no invented quote, price, acceptance or date. Preserve status/history until reviewed. Revert mappings using manifest if wrong; never undo completed real business events by bulk enum rewrite. |
| M5 build identity and legacy sheet ownership | Tag existing snapshots as legacy schema; inventory reused sheet Items/BOMs and power inconsistencies. Freeze referenced commercial/build artifacts where enough data exists. New edits create v2 builds; map legacy sheet accessories by actual line evidence, otherwise flag ambiguous. Do not rename old Items/recalculate approved prices or manufacture new BOMs merely on read. | Compare all sampled approved commercial amounts/build links before/after. Ambiguous historical builds require staff assessment; immutable snapshot capture cannot reconstruct already-overwritten history. Test two identical lines and schedule version copy. |
| M6 sync/publication reconciliation | Capture current per-brand mappings and observed staged/live content. Add source/staged/published hashes, leave unknown states unknown. Import/disable old n8n triggers as planned; queued retirement jobs included. Resume only reconciled operations; new approval needed for new content. | No mass duplicate creation or unintentional publication. Restore previous workflow exports/disable worker if needed; remote changes require explicit republish/unpublish reconciliation, not just DB restore. |
| M7 export/review/event backfill | Preserve existing Export Job COMPLETE records as legacy results with unknown completeness until assessed; do not relabel all as verified. Link known drawing revisions without inventing approvals. Seed event ledger only from reliable facts, with historical emails suppressed. | No notification storm; old documents stay accessible to current authorized users. Future issued output uses manifest format. Old reviews/attachments not lost. |
| M8 workspace/assets cutover | Merge approved workspace standard changes with site override strategy; deploy hooks/templates/JS together, build assets, clear caches and verify URLs. Retain previous assets and compatible reader version. | Fresh/upgraded staff walkthrough, no stale globals/duplicate handlers, correct queue counts and links. Restore prior workspace export without undoing underlying business records. |

Ordering: M0→M1; M2/M3 begin independently; M4/M5 before new commercial/build writers; M6 before automated publication; M7 before new document/review consumers; M8 per release slice. File moves and remote CMS operations are external side effects: record compensation and resumable state explicitly; a DB rollback cannot reverse them automatically.

Maintain a migration ledger of input version, affected IDs, old/new reference, outcome, checksum, timestamp and error. Restrict it as operational data. Post-migration checks compare counts, dangling links, duplicate business keys, file retrievability, price/BOM snapshots, role grants and live publication state. No automatic one-year deletion in this release without the artifact-specific decision.

## 7. Verification design

### 7.1 Environments and commands

Use a Linux Bench environment matching deployed Frappe/ERPNext revisions, MariaDB/Redis, working workers/scheduler and built web/Desk assets. Current repository CI uses Python 3.11, Node 18, MariaDB 10.6, Frappe/ERPNext `version-15` and `bench build`; capture exact versions at S0 rather than assuming a floating branch reproduces production. Do not install Frappe into this Windows checkout solely to pretend to run integration tests.

Run a fresh site and an upgraded sanitized clone with real permission/customization patterns. Browser harness uses real Website User and ordinary staff sessions, not Administrator-only tests. n8n uses staging credentials, a test CMS/brand target and controlled failure responses; assert execution effects and actual page/embed behavior. Email tests use a capture mailbox/queue; no real customer messages. PDF tests need actual representative fillable templates and a renderer/print check.

Suggested commands for the subsequent implementation task:

```text
python -B -m unittest illumenate_lighting.illumenate_lighting.api.test_led_sheet_math
ruff check <changed-python-paths>
ruff format --check <changed-python-paths>
node --check <changed-standalone-js-file>
bench --site <test-site> migrate
bench build --app illumenate_lighting
bench --site <test-site> run-tests --module <changed-test-module>
bench --site <test-site> run-tests --app illumenate_lighting
```

Add the browser harness's documented command when S0.3 creates its package/config; no root Playwright script currently exists to invoke. JS embedded in Jinja requires rendering in browser tests, not only `node --check`. Run focused checks per story and the CI-equivalent app suite at integration/release boundaries. Distinguish environment/setup failures from application assertions; do not mark skipped Bench tests as passing.

### 7.2 Existing and proposed suites

Existing API test files below live under `illumenate_lighting/illumenate_lighting/api/` unless stated otherwise.

| Test level | Extend existing / add proposed coverage | Assertions that matter |
|---|---|---|
| Schema/contract | Add `test_product_catalog.py`, `test_product_readiness.py`, `test_configuration_contract.py`; extend `test_webflow_integration.py`, `test_webflow_configurator.py`, `test_webflow_brand.py` | Real DocType fixture schemas; typed projection/aliases; channel/role omissions; direct inactive route; dependency hashes. No source-string-only replacement for behavior tests. |
| Pure engineering | Existing `test_led_sheet_math.py`; new `test_power_planner.py` / manifest normalization tests | Exact circuits/rounding/UOM, infeasible assignments, deterministic allocation and identity; data errors distinct from no available product. |
| Persistence/conversion | `test_configurator_engine.py`, `test_tape_neon_configurator.py`, `test_manufacturing_generator.py`, `test_desk_configurator.py`, `test_quote_order_configurator.py`, `test_dealer_order_conversion.py`; schedule DocType tests | Immutable builds/line ownership, Item/BOM/price reuse, new/legacy modes, rollback and idempotency. True concurrent transactions, not two calls in the same test transaction, for locking races. |
| Access/lifecycle | `test_portal_access_matrix.py`, `test_portal_status_transitions.py`, `test_portal_status_and_stock.py`; proposed file/quote/Issue/review tests | Every actor against list/count/detail/mutate/raw File/export; revoked access; native ERP submit guard; event-derived status; own-company standard masters not globally exposed. |
| Stock | `test_bundle_stock.py`, `test_pricing_utils.py`, existing stock tests | Stock UOM conversion, exact approved company/warehouse set, shared shortage/quantity, reservation event and no reservation on view. |
| Documents | `test_exports.py`, `test_spec_submittal_field_uniqueness.py`, `test_spec_submittal_computed_fields.py`; proposed packet completeness/revision tests | Required manifest content, independent filled templates, supported image conversion, immutable output and private access. Rendered visual checks complement extraction. |
| Browser | Proposed `tests/portal_e2e/` and Desk scenarios | Mouse/label/keyboard, repeated modal mount, slow stale responses, add/configure/back/cancel, save/reopen, upload interruption, expired session, role navigation. Assert values/files/results, not just modal presence. |
| Publishing | Export contract tests plus n8n test executions/Webflow staging page | 123-record job set, retry/429/timeout/concurrent edits, create-before-callback crash, brand separation, retirement, stage/live verification and sheet download. |
| Notifications | Proposed event/recipient/queue tests | Idempotent event+recipient enqueue, intended company contacts, preference suppression, revoked recipients, queue failure/retry and no request loss. |

### 7.3 Golden reference dataset

Engineering/Sales/Operations approve numerical expected outputs, not screenshots alone. Store fixture inputs and manifests in a test-fixture directory proposed by S0, with environment-dependent Item names resolved by seeded aliases.

| Case | Inputs and expected proof |
|---|---|
| G01 linear single | Minimum and maximum supported lengths, just below/at/above cut/run limits; included/excluded power; requested vs manufactured output. |
| G02 linear jumper/corner | Multiple pieces and one internal jumper; leaders and physical jumper once; invalid corner/endcap mapping fails with exact field. |
| G03 tape | Cut runs/segments plus separate bulk reel case; Desk and portal match; string false and enabled/disabled override persist. |
| G04 neon | Start/end feed and leader/jumper choices; IP/endcap compatibility; unequal circuit load allocation. |
| G05 sheet | Boundary row/column area changes, different areas sharing human part number, extra vs included cables, power excluded, two identical schedule lines. |
| G06 independent group | User's 20/5/25-ft fixtures with 6/3/2-ft leaders, quantity 1 and 2; internal jumper in one member; per-member split/extra-feed instructions; one/multiple supply explanation. Sheet analog uses three coverage areas. |
| G07 power failure | 20W/100W loads, total-capacity pass but per-output fail, unsupported fan-out, missing eligibility and no compatible stock Item. No successful included-power build without feasible plan. |
| G08 units/shared stock | 72-inch bulk leader; Foot/Meter/Inch/fixed Nos Items; shared component across two lines; ilL-Stores missing and duplicate warehouse label across companies. |
| G09 mixed packet | Fixture/tape/neon/sheet/accessory and two OTHER lines; multipage PDF/image/long labels; replacement, duplicate, version; corrupt file and missing mapping; two configurations from same PDF template. |
| G10 commerce/fulfillment | Direct PO plus quote-led order, expired/superseded offer, rejection/withdrawal/cancel, one fulfilled and one unstarted line, partial shipments/invoices, standard Items with no Work Order. |
| G11 isolation/history | Dealer A/B, non-dealer owner/member, VIEW/EDIT collaborator, revoked contact; old issued packet/quote/order after template/price/document change. |
| G12 publishing/workspace | >50 products, one invalid dependency, second brand without configurator, mid-sync edit, remote create timeout; ordinary staff recovers issue from workspace and verifies filled sheet download. |

Parameterize multiplicity and included-power policy across four families; run all applicable entry points. Mark inapplicable combinations explicitly (for example a sheet has no linear max-run override). Add direct controller/native ERP/API tests as well as portal clicks so bypass paths cannot escape validation. Test mutating endpoints as POST with normal session/CSRF protection; guest endpoints remain limited to public product capability and bounded informational generation.

PDF QA includes field extraction plus rendered pages at normal print scale, page order/rotation, long text clipping, repeated form field identities, and appearance in browser PDF viewer and at least one print/render engine. Store approved reference renders with an intentional update process; do not auto-approve changed engineering values through snapshot updates.

## 8. Rollout, monitoring and rollback

Use per-family/channel enablement and cohort flags stored in an existing suitable settings DocType or a small proposed release-settings record; decide exact home during S0 schema inventory. Backend gates must enforce flags as well as hiding UI. Suggested independent switches: new configuration schema writers, group creation, quote portal, order intake, complete-packet mode, public sheet download, automatic CMS staging and live publication.

Before each release: record app/schema/asset/workflow versions, backup status, migration dry-run counts, test evidence, unresolved records and named go/no-go owner. Pause affected writers/workers only where required for consistent migration, resume after checks, and make maintenance state explicit to users. Never run real dealer transactions as an unnoticed production smoke test.

Monitor by family/channel: configuration validation/save failures; order/quote idempotency conflicts; file upload/finalization errors; missing-packet lines and stuck export jobs; stale/failed publish jobs; notification enqueue/delivery failures; unassigned/overdue requests; incomplete linear manufacturing generation; stock-scope configuration errors. Use request/event/job IDs and timings, not private drawings, passwords or full commercial payloads in general analytics.

Provisional p95 targets from the audit: ordinary pages/list results usable within 2.5 seconds and normal calculations within 3 seconds on representative load. Confirm at S0 and record dataset/concurrency. Slow exports must show durable progress/status/retry. Track request age and first-human-response separately from total completion; no 24-hour public promise until an operational owner commits.

Rollback is normally **disable new writers and retain new readers/schema**, then fix forward. Old code that does not understand groups/build schema v2 must not be restored over new records without a compatibility reader or maintenance mode. Preserve new requests, approvals, uploads and issued documents. Full DB restore is only a controlled disaster recovery action with a plan for post-backup transactions and file/CMS side effects. For a bad publication, stop jobs and reconcile/republish the last approved remote revision; rolling back application code does not roll back Webflow. Privacy fixes are not rolled back to public storage.

Final gate: zero unresolved P0; all required F01–F32 dispositions evidenced; no P1 failure in a declared core journey; all approved reference configurations reconcile; launch catalog/document inventory signed; ordinary staff can operate queues; private access/native download tests pass; migration/restore drill complete; actual installed Webflow/n8n/workspace verified. Any deferred capability must be visibly inquiry-only/unavailable and explicitly approved as scope, not merely left broken.

## 9. Remaining decisions with defaults and consequences

These are planning assumptions to resolve during implementation discovery, not requests for renewed approval of the settled buying model. The next agent can implement independent stories while the owning business role resolves them.

| Decision / owner | Recommended planning default | If changed or unresolved |
|---|---|---|
| Actual launch SKU list / PO + Catalog | Four configurable families, grouping, approved standard Items; unsupported kit/components inquiry-only | Gates exact catalog fixtures/content workload. Do not infer launch approval from `is_active` alone. |
| Dealer invitation administration / PO | Introduce explicit access-admin capability; preserve existing dealer project rights; disclose company-wide edit effect | Avoid silently taking away already approved dealer rights or letting ordinary invites grant ERP roles. |
| Quote validity, discounts, acknowledgment rules / Sales | Use existing ERP terms/validity; material price/spec/date change requires fresh acknowledgment; no default business validity invented here | Must be decided before S6 acceptance; outdated quote cannot proceed merely because schedule is QUOTED. |
| Required PO/address/receiving fields / Sales + Operations | Quote request does not require PO; direct order intake requires validated buyer/ship/bill context; PO file optional unless customer policy says required | Missing mandatory intake blocks staff approval, not necessarily an incomplete draft. |
| Stock implementation detail / Operations | Enforce already-set ilL-Stores/company scope and reservation only on submit; verify installed ERP mechanism | Do not reopen scope as undecided; if ERP cannot reserve intended components automatically, specify approved planning process and accurate availability messaging. |
| Electrical topology/tie-breaks / Engineering | Only explicit supported wiring; one feasible supply preferred, then least count, deterministic cost/priority/capacity tie-break | Missing engineering data blocks affected configurations; no guessed parallel wiring. Define practical supported group size before selecting search algorithm. |
| Drawing signoff/production release / Engineering | Named customer technical approver; material build/new drawing revision needs engineering review; explicit staff manufacturing release | Decide whether release hold blocks order approval or only production. No automatic authority inferred from a file download. |
| Document requiredness/source / Engineering + Catalog | Configured overall packet requires each configured line and selected OTHER primary spec; standard accessory requirement set in register; explicit static mode | Governs readiness and missing-document gate. Do not treat arbitrary Item attachment as approved literature. |
| Public metadata / PO + Engineering | Public informational product PDF excludes customer/project labels; authenticated private route handles them | Guest private token/session architecture is additional scope if anonymous personalized downloads are mandatory. |
| Upload bounds / Engineering + Operations | PDF/JPEG/PNG initially; proposed 20 MiB/file and 10 files/intake, additionally bounded PDF pages/image pixels | Validate hosting/renderer limits in S0 and change configured values before release. Any promised extra format requires parser/conversion/QA support. |
| Publication trigger/authority / Catalog + Integration | Scheduled staging of approved revisions; explicit authorized item publication; per-brand service identity | Trigger cadence and publish authority need named owners; no automatic site-wide publish from “Synced.” |
| Retention / PO + records owner | Preserve all existing records; define durations for transient uploads, final docs, commercial records, audit/events separately | No deletion job until policy and shared-reference rules are approved. |
| Mandatory emails and response SLAs / Sales + Support | Preserve optional category preferences, portal receipts always available; email staff escalation for failed/stuck work | Mandating messages or a public SLA changes policy and wording, not only code. |
| Workspace overrides / PO + Release | Export/back up site customizations and merge approved standard sections; dedicated custom area if needed | Blind fixture replacement can lose live customizations; S8A migration must state chosen strategy. |
| Capacity/timeline / Release | Re-estimate after S0 with actual team and content scope | 199–342 days is effort, not a promised launch date. |

## 10. Instructions for the implementation handoff

1. Read this plan and the three inherited decision sections before changing behavior. Compare current HEAD with the baseline; preserve unrelated work. Read affected source before edit and follow local AGENTS.md. Use small vertical PRs; do not rewrite the entire portal to start.
2. Complete S0 deployment/seed/test manifest. Start source-confirmed S1 repairs and S4 defect tests in parallel workstreams only if the subsequent task/team authorizes that organization. Capture runtime password/checkbox evidence before asserting root cause.
3. Turn each story into a tracked unit using its ID, owner, dependency, files, schema impact, tests and release flag. New schema/API identifiers here are proposals; record a brief justified deviation when using an equivalent existing primitive.
4. Land S1.5 quote request foundation before S6.1 enhancement; do not implement two different quote-intake stores. Centralize staff capability and File authorization before new queues/download routes.
5. Establish canonical product/build/file/event contracts and fixtures early. Update existing consumers via adapters; preserve old external whitelisted names until the deployed n8n/embeds and legacy links migrate.
6. Keep a story evidence log: actual commands/results, actor-specific browser traces, engineering manifests, generated PDF renders, migration report, n8n execution IDs and staged/live verification. Do not substitute static-source assertions for UI or concurrency tests.
7. Do not silently drop grouping, sheet public downloads, OTHER packet support or workspace queues to fit a smaller implementation. Explicitly propose phasing when necessary, with backend/UI capability gates and remaining story IDs.
8. Deployment, production migrations, publication and customer communications require authorization from the subsequent implementation task. This planning deliverable performs none of them.

## 11. Planning validation record

- Repository baseline checked against supplied audit; same commit.
- Source/schema/workflow reads covered contracts and entry points listed below. Broader legacy operational/data scenarios are assigned to S0/S4 instead of claimed as reproduced.
- Standalone LED sheet math: **34 passing tests**, rerun September 25, 2026 with `-B`.
- Frappe unavailable in local runtime; no database-backed, browser, PDF rendering, live n8n/Webflow, migration or deployment test executed for this plan.
- Only this implementation-plan document was authored. No application source, workflow, schema or production record was intentionally changed. Repowise tools may maintain their pre-existing local index/cache state.

## 12. Source map for the next agent

Paths are repository-relative and refer to the baseline above. Line anchors are navigation hints; use symbols after edits move lines. A link here is evidence of a code path, not evidence of live runtime success.

| Area | Existing files and symbols to extend/test |
|---|---|
| Catalog schema/projection | [product_catalog.py](../illumenate_lighting/illumenate_lighting/api/product_catalog.py): `get_catalog_products`, `get_catalog_product_detail` (196), `get_catalog_filter_options`; [Webflow product schema](../illumenate_lighting/illumenate_lighting/doctype/ill_webflow_product/ill_webflow_product.json); child `ill_child_webflow_document`, `ill_child_webflow_specification`, `ill_child_webflow_configurator_option`, `ill_child_webflow_certification_link`; `ill_attribute_certification`. |
| Catalog UI | [product_detail.js](../illumenate_lighting/public/js/product_detail.js): `initEmbeddedConfigurator` (166); `product_catalog.js`; `templates/pages/product_detail.html`, `products_catalog.html`; legacy `public/js/webflow_configurator.js` shim. |
| Account/support/drawings | [account.html](../illumenate_lighting/templates/pages/account.html): `changePassword` (520), `deleteAccount`, `createCompany`; `ill_support.html/py`, `drawings.html/py`, `drawing_detail.html/py`, `request_dealer_access.html`; [portal.py](../illumenate_lighting/illumenate_lighting/api/portal.py): `create_customer` (2637), `create_drawing_request` (2710), `create_support_ticket` (2786), profile/settings/invite methods. |
| Access/roles | [access.py](../illumenate_lighting/illumenate_lighting/portal/access.py): actor, project/schedule permissions and query predicates, configured-record handoff; [ill_project.py](../illumenate_lighting/illumenate_lighting/doctype/ill_project/ill_project.py): `_is_internal_user`; [dealer_permissions.py](../illumenate_lighting/illumenate_lighting/dealer_permissions.py); [install.py](../illumenate_lighting/illumenate_lighting/install.py): `create_dealer_role`. |
| Schedule lifecycle/conversion | [schedule controller](../illumenate_lighting/illumenate_lighting/doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py): `create_new_version` (141), `create_sales_order_result` (254), `_build_and_insert_sales_order`, `append_quote_lines`, `request_quote` (1167), `duplicate_line`, `can_convert_schedule_to_order` (1360), `allowed_portal_transitions`, `transition_schedule_status`, Sales Order hooks; matching DocType/child schemas. |
| Portal schedule APIs/UI | `api/portal.py`: `add_schedule_line`, `update_schedule_line`, `request_schedule_quote` (2520), `create_schedule_sales_order` (2592); [schedule.html](../illumenate_lighting/templates/pages/schedule.html): Add Line, `uploadFile` (2600), add/edit/configure callbacks; `templates/pages/schedule.py`. |
| Shared configurators | [shared_configurator.js](../illumenate_lighting/public/js/configurator/shared_configurator.js): Base, `destroy`, `renderTemplateCards` (259); `fixture_steps.js`, `tape_neon_steps.js`, `led_sheet_steps.js`; corresponding `templates/includes/configurator_*_form.html`; `templates/pages/configure.html/py`; [desk_dialog.js](../illumenate_lighting/public/js/desk/desk_dialog.js). |
| Builder/Desk commercial bridge | [configured_product_builder.py](../illumenate_lighting/illumenate_lighting/api/configured_product_builder.py): calculate/save/preview, tape payload (493), dispatch (801/853); [desk_configurator.py](../illumenate_lighting/illumenate_lighting/api/desk_configurator.py): `_require_internal_user` (115), `build_configured_line` (454), `_save_led_sheet`, accessory rows, Quotation hooks (879); [quote_order_configurator.py](../illumenate_lighting/illumenate_lighting/api/quote_order_configurator.py): artifact creation, `_apply_artifact_to_row`; [quote_from_schedule.py](../illumenate_lighting/illumenate_lighting/api/quote_from_schedule.py). |
| Engineering/builds | [configurator_engine.py](../illumenate_lighting/illumenate_lighting/api/configurator_engine.py): candidate/final hashes, geometry, driver selection/pricing; [tape_neon_configurator.py](../illumenate_lighting/illumenate_lighting/api/tape_neon_configurator.py): validation/persistence, `select_driver_plan_for_tape_neon`; [led_sheet_configurator.py](../illumenate_lighting/illumenate_lighting/api/led_sheet_configurator.py) and `led_sheet_math.py`; configured DocType controllers and driver eligibility/spec schemas. |
| BOM/stock/manufacturing | [manufacturing_generator.py](../illumenate_lighting/illumenate_lighting/api/manufacturing_generator.py): `on_sales_order_submit` (244), `build_fixture_bom_items`, Item/price/BOM/WO helpers; `tape_neon_bom.py`, `led_sheet_bom.py`; [pricing_utils.py](../illumenate_lighting/illumenate_lighting/api/pricing_utils.py): `_eligible_warehouses` (183), `_available_qty_sql`, `fixture_components`, shared stock allocation. |
| Technical requests | [document_requests.py](../illumenate_lighting/illumenate_lighting/api/document_requests.py): `create_portal_document_request`, scoped reads, `get_request_detail` (505), `add_request_attachment` (602), deliverable APIs; `doctype/ill_document_request/*`, `ill_request_deliverable/*`; existing workflow fixture. |
| PDFs/exports | [spec_submittal.py](../illumenate_lighting/illumenate_lighting/api/spec_submittal.py): fill/uniqueness/appearance helpers, `_merge_pdfs` (870), `_gather_line_documents` (993), packet generation (1316), fixture/sheet/neon/driver/controller generators; [exports.py](../illumenate_lighting/illumenate_lighting/api/exports.py): export access, private saving, `validate_file_access` (1615), `serve_export_file` (1668); `doctype/ill_export_job/*`. |
| Authoring | Family template controllers/schemas under `doctype/ill_fixture_template`, `ill_tape_neon_template`, `ill_led_sheet_template`, `ill_driver_template`, `ill_controller_template`, `ill_extrusion_kit_template`; corresponding spec/option/relationship and submittal-mapping DocTypes; [guardrail_audits.py](../illumenate_lighting/illumenate_lighting/api/guardrail_audits.py); [fixture builder generators](../tools/fixture_builder/generators). |
| Publishing | [Webflow product controller](../illumenate_lighting/illumenate_lighting/doctype/ill_webflow_product/ill_webflow_product.py): save/enrichment/options/backlinks; [webflow_export.py](../illumenate_lighting/illumenate_lighting/api/webflow_export.py): export (185), synced/error callbacks (585/651), statistics and enrichment; `webflow_sync_events.py`, `webflow_brand.py`, per-brand child schemas; [product n8n workflow](../n8n_workflows/webflow_product_sync.json) and attribute/category/filter workflows. |
| Public download/handoff | [webflow_configurator.py](../illumenate_lighting/illumenate_lighting/api/webflow_configurator.py): `download_spec_sheet` (527), session/handoff; `spec_sheet_generator.py`, `webflow_schedule.py`, `public/js/webflow_spec_sheet_download.js`; `tools/configurator_ui` discovery handoff only. |
| Orders/events | [orders.py](../illumenate_lighting/illumenate_lighting/portal/orders.py): access, read model, `_production_summary`, `_timeline`, PDF access; [status.py](../illumenate_lighting/illumenate_lighting/portal/status.py); [notifications.py](../illumenate_lighting/illumenate_lighting/portal/notifications.py); `templates/pages/orders.html`, `order_detail.html`. |
| Workspace/schema/deployment | [workspace JSON](../illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/illumenate_lighting.json); [hooks.py](../illumenate_lighting/hooks.py), `illumenate_lighting/illumenate_lighting/fixtures/custom_field.json`, `illumenate_lighting/patches.txt`, patches/install/permission code; [.github/workflows/ci.yml](../.github/workflows/ci.yml), [pyproject.toml](../pyproject.toml). |
