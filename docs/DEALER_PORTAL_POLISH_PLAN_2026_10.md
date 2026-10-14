# Dealer Portal Polish & Desk Integration — Implementation Plan (October 2026)

> **Audience:** an implementing Claude agent working in the `erpillumenatelighting` repo (Frappe/ERPNext v16 custom app `illumenate_lighting`).
> **Author context:** produced from a read-only investigation of `main` at commit `0bee995` on 2026-10-14. Nothing was changed in code.
> **Goal:** make the dealer portal and its public surfaces feel robust and professional, and make every portal action land cleanly in the Desk workflow of internal staff.

---

## 0. How to use this plan (read first)

1. Work **phase by phase, task by task**. Each task has an ID (e.g. `SEC-1`), the evidence (file:line), the fix, acceptance criteria and tests. Do not start a later phase before the earlier phase's P0 items are merged.
2. **One PR per task or per small group of related tasks.** Keep diffs minimal. Do not refactor beyond what a task asks for.
3. Tasks marked **🟨 DECISION** need the owner (Kevin) to choose. Do not implement those until they answer; implement everything else.
4. Line numbers are from commit `0bee995` and will drift. Search for the quoted code if a line moved.
5. The repo's existing plans are background, not instructions: `docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md`, `docs/B2B_PORTAL_IMPLEMENTATION_STATUS.md`. **Several of their P0s are already fixed** (see §2.3). Don't redo them.

### 0.1 Repo conventions you must follow

- Python uses **tabs** for indentation, line length 110, `ruff check .` / `ruff format .` (see `pyproject.toml`). Only lint the files you touch; there is a large existing baseline.
- New domain logic goes in `illumenate_lighting/illumenate_lighting/portal/*.py` (small focused modules), **not** in the 4,600-line `api/portal.py`. `api/portal.py` keeps thin whitelisted wrappers for backward compatibility.
- The single access policy lives in `illumenate_lighting/illumenate_lighting/portal/access.py`. Staff capabilities live in `portal/staff.py` (`allowed("sales")`, etc.). Reuse them; never write a new ad-hoc role check.
- Customer-facing emails go through `portal/notifications.py::notify_user` → `portal/outbox.py` (preference-gated, idempotent). Never call `frappe.sendmail` directly from portal code.
- Shared status vocabulary lives in `portal/status.py`. Use it from Python and pass labels to templates/JS. Never re-declare status maps in JS.
- Bundles: `public/js/illumenate_web.bundle.js` (portal), `public/js/illumenate_desk.bundle.js` (Desk), `public/css/illumenate_web.bundle.scss`. They are built by `bench build`.

### 0.2 Frappe v16 facts verified during the investigation (rely on these)

| Fact | Consequence for this plan |
|---|---|
| Frappe's Jinja environment has **no autoescape** (`frappe/utils/jinja.py`: `FrappeSandboxedEnvironment(loader=..., undefined=DebugUndefined, cache_size=32)`). | Every `{{ value }}` without `| e` outputs raw HTML. Frappe's save-time `sanitize_html` strips `<script>`/event attributes from values that contain `<`/`>`, but values without angle brackets (quotes, `);`) pass untouched. |
| `@frappe.whitelist()` without `methods=` accepts **GET, POST, PUT, DELETE**. CSRF is only checked for unsafe methods. | Mutating endpoints are reachable by GET. |
| `frappe/app.py::sync_database` **commits on POST/PUT/DELETE and rolls back on GET**. | (a) A GET call to a mutating endpoint returns "success" but persists nothing (a silent no-op trap). (b) On POST, an endpoint that catches an exception and *returns* `{"success": False}` gets its partial writes **committed**. |
| `frappe.log_error(...)` inserts the Error Log in the current transaction unless `defer_insert=True`. | If you add a rollback to an error handler, roll back **first**, then log (or pass `defer_insert=True`), or the Error Log is lost. |
| Every file in `templates/pages/` is routable at `/<filename>` even without a `website_route_rules` entry. | Dead templates are live public URLs. |

### 0.3 Local checks (all pass on the baseline; keep them green)

```bash
python3 -B -m unittest discover -s tests/portal_unit          # baseline: 818 tests OK
python3 -B tools/check_portal_templates.py                    # baseline: 43 templates parsed OK
(cd tests/portal_ui && npm ci && node --test *.test.cjs)       # JSDOM UI suites
ruff check <files you touched>
```

Tests in `tests/portal_unit` use Frappe doubles, so no bench is needed. Follow the existing patterns there when adding tests. Installed-site checks (bench) are listed per task where they're needed.

### 0.4 Severity legend

- **P0**: security/data exposure or a broken core journey. Fix first.
- **P1**: wrong data, silent failure, or a workflow that strands a user or staff member.
- **P2**: polish, consistency, performance, maintainability.

---

## 1. Executive summary (why it feels "beginner")

The *domain layer* is far more sophisticated than the UI suggests: idempotent requests, frozen snapshots, immutable revisions, a unified access policy. What makes it feel sketchy is the **surface and the seams**:

1. **Two visual systems.** Newer pages (`orders`, `quotes`, `order_detail`, `quote_detail`) use the shared `.ill-commerce` shell and portal navigation. The most-used pages (**Overview, Projects, Project, Collaborators, Configure, Edit Fixture, Resources**) have no portal navigation at all and carry their own inline `<style>` blocks. `schedule.html` alone has ~1,000 lines of inline CSS (139 hard-coded hex colors) and ~2,200 lines of inline JS.
2. **The "msgprint + reload" interaction pattern.** Success pop-ups followed by `window.location.reload()`, raw `confirm()`, crashes on `r.message.error` when `r.message` is undefined, raw status codes (`ACTIVE`, `DRAFT`) shown to users.
3. **Seams between portal and Desk are invisible.** Dealer submissions (quote requests, order requests, account requests, support tickets, portal replies) generate **no staff notification**. Unassigned requests swallow dealer replies (nobody is emailed). Staff-configured request types never reach the portal. Desk forms hide collaborators. Staff can't easily create a project on a dealer's behalf.
4. **Dead ends in core journeys.** Invitations are never emailed (copy-paste links only). External collaborators can't be invited from the Collaborators page. Collaborators with EDIT access get bounced to "Request dealer access" when they click Configure. Login loses the deep link from notification emails. The schedule status menu offers an option ("QUOTED") that always fails. Moving a quoted schedule back to Draft silently kills the open offer.
5. **A handful of real security issues**: a stored XSS via inline `onclick` handlers, Dealer-role REST read access to every Customer/Contact/Address, unauthenticated lead webhooks, and partial-write commits on handled errors.

---

## 2. Investigation notes

### 2.1 Surfaces reviewed

- Routes: `illumenate_lighting/hooks.py` (`website_route_rules`, `website_redirects`, `doc_events`, `permission_query_conditions`, `has_permission`, web includes).
- Pages: all of `illumenate_lighting/templates/pages/*` and `templates/includes/*`.
- APIs: `illumenate_lighting/illumenate_lighting/api/portal.py`, `api/document_requests.py`, `api/webflow_leads.py`, `api/webflow_portal.py`, guest endpoints.
- Domain: `illumenate_lighting/illumenate_lighting/portal/*` (access, accounts, quotes, offers, orders, notifications, outbox, conversations, queues, support, staff).
- Desk: `public/js/commercial_tasks.js`, `desk_conversation.js`, `quote_request.js`, `sales_order.js`, `doctype/ill_project/ill_project.js`, `doctype/ill_project_fixture_schedule/*`, `dealer_permissions.py`.
- Assets: `public/css/*`, `public/js/portal*.js`, bundles.

### 2.2 Page inventory (inline code volume)

| Page | Portal nav? | Inline `<style>` lines | Inline `<script>` lines | Notes |
|---|---|---|---|---|
| `portal.html` (Overview) | ❌ | 164 | 0 | feature-card grid, no "what needs my attention" |
| `ill_projects.html` | ❌ | 0 | 82 | XSS, no search/pagination |
| `project.html` | ❌ | 0 | 784 | XSS, duplicated modals |
| `collaborators.html` | ❌ | 0 | 132 | bypasses invitations |
| `schedule.html` | ✅ | **1035** | **2179** | 139 hex colors |
| `edit_fixture.html` | ❌ | 117 | 1038 | route uses underscore `/portal/edit_fixture` |
| `configure.html` / `configure_tape.html` | ❌ | 0 | 73 / 15 | |
| `resources.html` | ❌ | 98 | 17 | |
| `account.html` | ✅ | 175 | 155 | |
| `drawings.html` / `drawing_detail.html` | ✅ | 141 / 201 | 52 / 26 | hard-coded request types |
| `ill_support.html` | ✅ | 162 | 54 | |
| `products_catalog.html` / `product_detail.html` | ✅ | 295 / 169 | 6 / 9 | 25 / 12 hex colors |
| `orders`, `quotes`, `order_detail`, `quote_detail`, `quote_request_detail` | ✅ | 0 | small | **target pattern** (`.ill-commerce`, `.ill-hero`) |
| `configure_old.html` | — | 0 | 262 | **dead**, no controller, still routable |
| `configure_multisegment.html` | — | 0 | 306 | **dead**, controller always redirects |
| `spec_submittal_cover.html` | — | 108 | 0 | PDF template, but routable as a page |

### 2.3 Items from the older plan that are already fixed (do not redo)

- Schedule list vs direct access agree: both come from `portal/access.py` (`schedule_query_conditions` mirrors `schedule_permission`).
- Document request lists are scoped (`permission_query_conditions` for `ilL-Document-Request` in hooks; `_scoped_request_count`).
- Drawing request project validation: `api/document_requests.py::create_portal_document_request` checks `can_read_project` (lines ~106–112).
- Project customer substitution on create: `create_project` now refuses rather than substituting (`api/portal.py` ~2241–2246).
- `_safe_error` hides internals for non-validation exceptions.

---

## 3. Phase 1: Security & data exposure (P0/P1)

### SEC-1 (P0): Stored XSS through inline `onclick` handlers

**Evidence**
- `templates/pages/ill_projects.html:62,66`: `onclick="...archiveProjectFromList('{{ project.name | e }}', '{{ project.project_name | e }}')"`
- `templates/pages/project.html:430,433`: `onclick="...openRenameModal('{{ schedule.name | e }}', '{{ schedule.schedule_name | e }}')"` and `confirmDeleteSchedule(...)`.

**Why it's exploitable:** `| e` turns `'` into `&#39;`. The browser HTML-decodes attribute values *before* running the JS, so the quote comes back and breaks out of the string. A project or schedule named `x');alert(document.cookie);//` contains no `<`/`>`, so Frappe's save-time sanitizer leaves it alone. Project names are visible to company members and collaborators, so this is cross-user.

**Fix**
1. Remove all four inline handlers. Render data attributes instead, e.g. `<button type="button" class="btn ... js-archive-project" data-project="{{ project.name | e }}" data-label="{{ project.project_name | e }}">`.
2. Bind with one delegated listener in the page script (`document.addEventListener('click', e => { const b = e.target.closest('.js-archive-project'); ... b.dataset.project ... })`).
3. Do the same for `schedule.html:1957,1960,1963` (`editLine({{ loop.index0 }})` etc.). They're integers so not exploitable, but convert them for consistency and because REL-3 changes the identifier to a string.
4. Add a guard to `tools/check_portal_templates.py`: **fail** if any template has an `on[a-z]+="...{{ ... }}..."` attribute. Regex: `on[a-z]+="[^"]*\{\{`.

**Acceptance:** `grep -rnE 'on[a-z]+="[^"]*\{\{' illumenate_lighting/templates` returns nothing. A project named `x');alert(1);//` archives normally and shows no alert.

**Tests:** extend `tools/check_portal_templates.py` with the new rule and a fixture that proves it fails. Add a `tests/portal_ui` JSDOM test that renders the projects list with a hostile name and asserts no script executes and that the click handler receives the exact name.

---

### SEC-2 (P1): Systematically escape user-controlled values in templates

**Evidence:** about 150 unescaped `{{ x.y }}` outputs of user-entered fields across templates. Worst offenders: `project.html` (29), `schedule.html` (20), `collaborators.html` (9), `drawing_detail.html` (9), `drawings.html` (9), `edit_fixture.html` (9). Examples: `project.project_name`, `schedule.schedule_name`, `schedule.notes` (`schedule.html:2024`), `deliverable.notes`, `attachment.file_name`, `request.fixture_or_product_text`, `collab.full_name`, `pm.first_name`, `project.location`. Save-time sanitization covers most HTML, but not values written via `db_set`/`db.set_value`/SQL, file names, or values from linked masters. Defense in depth is required.

**Fix**
1. In every template under `templates/pages` and `templates/includes`, add `| e` to every output that is not one of: a translation call `_()`, a number, a value already passed through `| tojson` inside `<script>`, or a known-safe HTML fragment that has been deliberately sanitized (use the existing `ill_sanitize_html` jinja method for those).
2. For `href`/`src` with user data, use `| urlencode` for path segments: `/portal/projects/{{ project.name | urlencode }}`.
3. For JS blocks that embed server values, always use `{{ value | tojson }}`, never `"{{ value }}"`. Example to fix: `collaborators.html:217` `var projectName = "{{ project.name }}";` becomes `var projectName = {{ project.name | tojson }};`.
4. Add a **warning-level** rule to `tools/check_portal_templates.py` listing `{{ <ident>.<field> }}` outputs without a filter, with an allowlist file for intentional raw outputs. Make it fail CI once the backlog is cleared.
5. JS string builders: replace ad-hoc `.replace(/</g...)` with one shared escape helper (see UI-3) and apply it to `template.template_name`, `item.item_name`, `template.template_code` in `schedule.html` (~2981, ~3216, ~3540) and other `.html(...)` builders.

**Acceptance:** the checker's unescaped list is empty or fully allow-listed. Rendering fixtures with `<b>x</b>` in every user field shows literal text.

---

### SEC-3 (P0, verify first): Dealer role can list every Customer, Contact and Address through REST

**Evidence:** `illumenate_lighting/illumenate_lighting/dealer_permissions.py:52`, the `DEALER_PERMISSION_MATRIX`, grants Dealer `read` on `Customer`, `Contact`, `Address`, `Item`, `Item Group`, `UOM`, `Currency`. Only `Sales Order` has `permission_query_conditions`/`has_permission` in `hooks.py:239-277`. Website users can't open Desk, but **REST (`/api/resource/<DocType>`, `frappe.client.get_list`) honors role DocPerms regardless of user type**.

**Step 1: verify on a staging site** (log in as a Dealer website user and keep the session cookie):
```bash
curl -s -b cookies.txt 'https://<site>/api/resource/Contact?fields=["name","email_id","phone"]&limit_page_length=5'
curl -s -b cookies.txt 'https://<site>/api/resource/Address?fields=["name","address_line1","city"]&limit_page_length=5'
curl -s -b cookies.txt 'https://<site>/api/resource/Customer?limit_page_length=5'
curl -s -b cookies.txt 'https://<site>/api/resource/Item/<any item>' | grep -E 'valuation_rate|last_purchase_rate'
curl -s -b cookies.txt 'https://<site>/api/resource/Sales Order/<own SO>' | grep -E 'valuation_rate|gross_profit'
```
If any of these return other companies' rows or cost fields, it's confirmed.

**Fix**
1. Add `permission_query_conditions` and `has_permission` hooks for `Customer`, `Contact`, `Address` in a new module `illumenate_lighting/illumenate_lighting/portal/master_scope.py`:
   - Internal users and staff with any capability (`portal/staff.py::allowed`): unrestricted (return `""` / `True`).
   - Dealer / website users: **Customer**: their own company (`Actor.customer`) plus Customers referenced by projects they can read (`customer`, `architect`, `lighting_designer`, `general_contractor` on readable `ilL-Project`) plus Customers they created (`owner = user`, which is how `get_allowed_customers_for_project` already scopes). **Contact/Address**: rows whose Dynamic Link points at one of those Customers, or whose `owner = user`.
   - Never return `""` (unrestricted) for a website user.
2. Register both hooks in `hooks.py` next to the existing entries.
3. Item: if Step 1 shows cost fields, set `permlevel: 1` on `valuation_rate`, `last_purchase_rate` (and any other cost field) through a **Property Setter patch** in `illumenate_lighting/patches/` (do not edit ERPNext JSON), and do not grant Dealer permlevel 1. Same for `Sales Order Item.valuation_rate` / `gross_profit` if exposed.
4. Make sure every portal page still works. The portal mostly uses `frappe.get_all` and whitelisted endpoints that are unaffected, but `frappe.get_list` callers (e.g. `project.py`, `drawings.py`) are affected by design.

**Acceptance:** as a Dealer, the curls in Step 1 return only own-company rows and no cost fields. Portal journeys (new project with stakeholder pickers, order intake with addresses/contacts, account page contacts/addresses) still work.

**Tests:** unit tests in `tests/portal_unit` for `master_scope` conditions (dealer, non-dealer company member, staff, guest), modeled on existing access tests (`test_portal_access_matrix.py`).

---

### SEC-4 (P1): Public lead webhooks accept unauthenticated, unthrottled writes

**Evidence:** `api/webflow_leads.py:59` `create_lead_from_webflow` and `:261` `create_lead_from_webflow_webhook` are `allow_guest=True, methods=["POST"]` with no secret check and no `rate_limit`. The docstring says they're called by n8n. Error paths return `str(e)` to the caller.

**Fix**
1. Require a shared secret header (e.g. `X-ILL-Webhook-Secret`) compared with `hmac.compare_digest` against a password field on `ilL-Webflow-Settings` (add `lead_webhook_secret` as a `Password` field if no suitable field exists). Reject with `frappe.AuthenticationError` and HTTP 401.
2. Add `@rate_limit(limit=30, seconds=60)` (from `frappe.rate_limiter`) keyed by IP as a second line of defense.
3. Replace `str(e)` responses with the `_safe_error`-style generic message and log the traceback.
4. Update the n8n workflow JSON in `n8n_workflows/` to send the header, and document it in `docs/WEBFLOW_LEAD_INTEGRATION_GUIDE.md`.

**Acceptance:** POST without the header returns 401 and creates no Lead. With the header it works. The 31st request in a minute is throttled.

---

### SEC-5 (P1): Collaborator management bypasses the invitation model and trusts client user lists

**Evidence**
- `templates/pages/collaborators.html:270` `addCollaborator()` and `saveCollaborators()` post the **entire** list to `api/portal.py::update_project_collaborators` (~2540), which **deletes and re-appends all rows** (`project.collaborators = []`) for any `user` strings the client sends. It doesn't check that the users exist, are enabled, are Website Users, or belong to the company, and it skips the recipient-acceptance invitation (`portal/accounts.py:314 invite`).
- Two different removal semantics: the list save **deletes** rows, while `remove_project_collaborator` **deactivates** them.
- Full-list replace means two managers editing at once overwrite each other.

**Fix**
1. Replace the full-list endpoint with granular operations in a new `portal/collaborators.py`: `set_access_level(project, user, level, expected_modified)`, `deactivate(project, user, expected_modified)`, and `invite(...)` (wraps `accounts.invite`). Server-side, accept only users that are (a) already active collaborators, or (b) same-company enabled Website Users. External users go through `invite` only.
2. Keep `update_project_collaborators` as a deprecated wrapper that rejects any user not already on the list or in the company, and never deletes rows (deactivate instead).
3. The page calls the new endpoints. Each change updates the row in place with a toast; no reload.

**Acceptance:** a crafted call with an arbitrary email returns a permission error. Removing a collaborator leaves an inactive row with history. Two concurrent edits don't erase each other.

---

## 4. Phase 2: Reliability & correctness (P1)

### REL-1 (P1): Handled errors commit partial writes

**Evidence:** `api/portal.py::_safe_error` (line ~30) logs and returns `{"success": False}`. Per §0.2, Frappe then **commits** on POST. Endpoints that catch without rolling back include `delete_schedule_line`, `duplicate_schedule_line` (saves the schedule, then `line_documents.clone` can fail and leave a duplicate line without documents), `move_schedule_line`, `create_project`, `update_project`, `archive_project`, `unarchive_project`, `rename_schedule`, `delete_schedule`, `update_project_collaborators` (save, then `add_comment`), `toggle_project_privacy`, `create_customer`, `create_contact`, `update_configured_fixture_on_schedule`. A few already roll back (`add_schedule_line`, `update_schedule_line`, `create_support_ticket`, `create_schedule_sales_order`).

**Fix**
1. In `_safe_error`, as the **first** statement: `if getattr(frappe.local, "request", None) and frappe.local.request.method in ("POST", "PUT", "DELETE"): frappe.db.rollback()`. Then log with `frappe.log_error(..., defer_insert=True)` so the log survives.
2. Remove the now-redundant explicit `frappe.db.rollback()` calls before `_safe_error` (optional, harmless if left).
3. Do **not** add rollbacks inside functions decorated with `@atomic_build`; they manage their own transaction.

**Acceptance:** a unit test that forces `add_comment` to raise inside `update_project_collaborators` asserts `frappe.db.rollback` was called and no Error Log is lost (`defer_insert=True`).

---

### REL-2 (P2): Make every mutating endpoint POST-only

**Evidence:** 53 whitelisted mutating functions accept GET:
- `api/portal.py` (24): `add_schedule_line, delete_schedule_line, duplicate_schedule_line, move_schedule_line, update_schedule_line, save_configured_fixture_to_schedule, create_project, update_project, archive_project, unarchive_project, create_schedule, rename_schedule, delete_schedule, update_project_collaborators, toggle_project_privacy, update_schedule_status, create_customer, update_user_profile, save_notification_preferences, save_portal_preferences, remove_project_collaborator, create_contact, update_configured_fixture_on_schedule, create_schedule_version`
- `doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py` (6): `create_new_version, create_sales_order, create_sales_order_result, request_quote, duplicate_line, move_line`
- `api/webflow_schedule.py` (5), `api/webflow_attributes.py` (4), `api/desk_configurator.py` (2), `api/exports.py` (2), `api/manufacturing_generator.py` (2), `api/quote_from_schedule.py` (2), `doctype/ill_document_request/ill_document_request.py` (2), `api/extrusion_kit_configurator.py`, `api/reconciliation.py`, `api/webflow_configurator.py`, `api/webflow_portal.py` (1 each).

Because GET is rolled back (§0.2), these are mostly *silent no-ops* over GET rather than CSRF holes, but they're a trap and bad hygiene.

**Fix:** add `methods=["POST"]` to each. Before changing one, grep its callers. `frappe.call`/`frappe.xcall` default to POST and are safe; check `fetch(...)`, `window.open`, `<a href="/api/method/...">` and the Webflow embed scripts (`docs/WEBFLOW_SPEC_SHEET_EMBED_SCRIPT.txt`, `public/js/webflow_*.js`) for GET usage.

**Tests:** add a unit test that imports each module and asserts every whitelisted function whose name starts with a mutating verb is registered as POST-only (inspect `frappe.allowed_http_methods_for_whitelisted_func` in the test double, or parse the decorators with `ast`).

---

### REL-3 (P1): Schedule lines are addressed by positional index (race-prone)

**Evidence:** `delete_schedule_line`, `duplicate_schedule_line`, `move_schedule_line`, `update_schedule_line` in `api/portal.py` (~1712–1975) and `duplicate_line`/`move_line` in the schedule doctype take `line_idx`. Lines also carry a stable `line_key` (assigned in `ilLProjectFixtureSchedule.validate`). If another tab, user, or Desk edit inserts, deletes or reorders a line between page load and the click, the action hits the **wrong line**. Saves are last-write-wins with no `expected_modified` check.

**Fix**
1. Accept `line_key` (preferred) **or** `line_idx` (deprecated) in each endpoint, and resolve with the existing `portal/configuration.py::resolve_line(schedule, line_key)`.
2. Accept `expected_modified`. If it's given and differs from `schedule.modified`, throw a `frappe.ValidationError` with the message "This schedule changed since you opened it. Reload to see the latest version." `portal/quotes.py::request_quote` already uses this pattern.
3. Update `schedule.html` to render `data-line-key` per row and send `line_key` + `expected_modified` (embed `{{ schedule.modified | string | tojson }}` and refresh it from each response).
4. Return the updated `modified` in every response.

**Acceptance:** with two tabs open, deleting line A in tab 1 and then deleting "line B" in tab 2 deletes B (or refuses with the reload message). It never deletes C.

---

### REL-4 (P1): Schedule status menu offers an impossible transition and kills offers silently

**Evidence**
- `templates/pages/schedule.html:1172` shows "QUOTED" to dealers/internal users. `PORTAL_SETTABLE_STATUSES` includes `QUOTED` (`ill_project_fixture_schedule.py:50`), but `allowed_portal_transitions` (~1575) never lists QUOTED as a target, so the click **always fails** with "Cannot change status from READY to QUOTED".
- Leaving QUOTED (`transition_schedule_status`, ~1625) auto-versions and locks the quoted schedule. The issued offer then fails `portal/offers.py::_current` (~279: `schedule.is_locked or _scope(...) != offer.schedule_hash` → "The schedule revision changed; Sales must issue an updated offer"). The offer **still shows as Open** in `/portal/quotes` and nobody is warned.
- The dropdown shows raw codes (`DRAFT`, `READY`) while the badge uses friendly labels.

**Fix**
1. Remove `QUOTED` from `PORTAL_SETTABLE_STATUSES` and the dropdown item.
2. Before leaving QUOTED, the page must warn when an open offer exists: "Quote {offer} (valid until {date}) will no longer be acceptable. Continue?" Add `open_offer` (name, valid_until) to the schedule page context from `ilL-Quote-Offer` where `schedule = name and state = 'ISSUED'`.
3. In `transition_schedule_status`, when auto-versioning from QUOTED, mark open offers for the old schedule as `SUPERSEDED` (add the state to `ilL-Quote-Offer` if missing; update `portal/offers.py::offer_status` and `OFFER_FILTERS`) and post an internal comment on the quote request so Sales sees it.
4. Use `schedule_status_label()` for dropdown labels.
5. Desk side: in `ill_project_fixture_schedule.js` `refresh`, if the schedule has an ISSUED offer, show `frm.dashboard.set_headline_alert(...)` warning that edits will invalidate it.

**Tests:** unit-test `allowed_portal_transitions` no longer exposes QUOTED. Test that leaving QUOTED supersedes the open offer. Add a UI test that the confirm appears when `open_offer` is set.

---

### REL-5 (P1): Staff-created projects have no owner company

**Evidence:** `doctype/ill_project/ill_project.py:41-44` sets `owner_customer` from the **creating user's** contact. Staff have no customer link, so a project created by Sales for a dealer has `owner_customer = None` and is invisible to the dealer's team (`access.py::_project_visibility_sql` keys on `owner_customer`). The portal `create_project` gives System Managers no owner-company field, and Desk (`ill_project.js:9`) only lets System Manager edit `owner_customer` (not `ilL Sales Review`).

**Fix**
1. `create_project`: when the actor is internal or `allowed("sales")`, accept `owner_customer` (required for staff). Validate that it's a Customer with at least one Dealer contact.
2. `ill_project.js`: allow `owner_customer` editing for System Manager **and** sales capability roles (`ilL Sales Review`, `ilL Order Approver`). Mirror the server check in `_validate_owner_customer_change` using `portal.staff.allowed("sales")`.
3. On the Desk form, show an intro warning if `owner_customer` is empty: "No dealer company: only the creator can see this project in the portal."
4. Patch: list projects with empty `owner_customer` in a report (don't auto-fix).

---

### REL-6 (P1): Login loses the deep link (email links land on the wrong page)

**Evidence** (guest handling per page):
- Bare `/login` (destination lost): `account, drawing_detail, drawings, ill_projects, ill_support, order_detail, orders, portal, support_detail`.
- `PermissionError` page (no redirect at all): `collaborators, configure (schedule), configure_sheet, edit_fixture, project, schedule`.
- Redirect to the list instead of the item: `quote_detail` → `/portal/quotes`.
- No check: `quote_request_detail, product_verification, system_design, resources, products_catalog, product_detail`. Verify each handles guests correctly (some should be public).

**Fix**
1. Add `portal/web_guard.py::require_login()` that redirects guests to `/login?redirect-to=<urlencoded full path + query>` (mirror `configure.py`'s existing logic) and raises `frappe.Redirect`.
2. Call it at the top of every authenticated page controller and delete the bespoke guest checks.
3. For a logged-in user without access, render a friendly 403 or 404 (portal-styled, "This item isn't available to your account", with links to Overview/Support) instead of the Frappe error page.

**Acceptance:** opening `/portal/orders/SO-0001` logged out → login → lands on `SO-0001`.

---

### REL-7 (P2): Dead and accidentally public templates

**Fix**
1. Delete `templates/pages/configure_old.html` (no controller, no references, served at `/configure_old`).
2. Delete `templates/pages/configure_multisegment.html` (its `.py` always redirects). Keep the `.py` adapter.
3. Move `templates/pages/spec_submittal_cover.html` to `templates/print/spec_submittal_cover.html` (non-routable) and update `api/spec_submittal.py:1012`.
4. Remove the dead notification bell code (`public/js/portal.js` `initNotifications`/`renderNotifications`, and `api/portal.py::get_portal_notifications` at ~3220, which has wrong logic: it counts schedules by `customer` (end client) instead of owner company and calls "To Deliver" orders "ready to ship"). UX-1 replaces it.
5. Fix the stale comment in `hooks.py`: "Product Catalog (System Manager only)".

---

### REL-8 (P2): Drawings list uses its own scoping

**Evidence:** `templates/pages/drawings.py:47-53` builds filters from `owner_customer` / `owner` instead of the shared `ilL-Document-Request` permission predicate used by `_scoped_request_count` (the dashboard counts). Lists and counts can disagree. Collaborators on a project may not see requests for that project.

**Fix:** use `frappe.get_list("ilL-Document-Request", ...)` (applies `permission_query_conditions`) or the same predicate function as `_scoped_request_count`. Add pagination (the projects dropdown is capped at `limit=50`; replace it with a searchable select).

---

### REL-9 (P2): `get_allowed_customers_for_project` correctness and performance

**Evidence:** `api/portal.py:85-210`.
- Only `System Manager` gets all customers; sales-capability staff don't (inconsistent with `access.py`, where sales staff are effectively internal).
- "Customers linked to any contact at the user's company" means a shared contact (e.g. a GC contact linked to two dealers) leaks the other dealer's customers into the dropdown.
- An N+1 `get_value` per customer.

**Fix:** use `portal.staff.allowed("sales")` for the all-customers branch. Drop the transitive contact clause, keeping own company + Customers owned by company users + Customers already used on readable projects. Fetch names in one `frappe.get_all(..., filters={"name": ["in", names]})`.

---

### REL-10 (P2): Small correctness fixes

| ID | Where | Problem | Fix |
|---|---|---|---|
| REL-10a | `schedule.html:1049` | Verification warning renders **above** the portal nav and outside `.container`. | Move it inside the container under the header. |
| REL-10b | `ill_projects.html`, `project.html`, `collaborators.html` JS | `r.message.error` throws when `r.message` is undefined (network/server error). | Use the shared call wrapper (UI-3). |
| REL-10c | `portal.html` dashboard | "Notifications" links to `/portal/account/notifications`, which renders Account but doesn't scroll. | Link to `/portal/account#notifications`. |
| REL-10d | `schedule.html:1126`, `portal/notifications.py:127` | Hard-coded `sales@illumenate.lighting`. | Use `portal/status.py::SALES_EMAIL`. |
| REL-10e | `api/portal.py:2954` support ticket | Issue description written as Markdown (`**Category:**`) into an HTML Text Editor, so staff see literal asterisks. | Build HTML with `frappe.utils.escape_html` per value. |
| REL-10f | `project.py` | N+1 `frappe.db.count` per schedule for line counts. | One grouped `SELECT parent, COUNT(*) ... GROUP BY parent`. |
| REL-10g | `access.py` | `get_actor()` hits the DB several times and is re-created per check (N+1 in loops such as `can_read_configured_record`). | Memoize per request: `frappe.local` cache keyed by user. |
| REL-10h | `duplicate_schedule_line` | Missing the `is_locked` early check its siblings have (validate catches it, but the message differs). | Add the same early check. |

---

## 5. Phase 3: Portal ↔ Desk integration (P1, the "ties into our Desk" work)

### DESK-1 (P1): Notify staff when a dealer does something

**Evidence:** no staff notification exists for: new quote request (`portal/quotes.py::request_quote`), new order intake (`portal/order_intake.py`), order change request (`portal/order_changes.py`), account request (`portal/accounts.py::request_change`), support ticket (`api/portal.py::create_support_ticket`), or offer response (`portal/offers.py::respond`). Staff only find work by checking Workspace queues (`portal/queues.py`). Document requests are the exception (they auto-assign and create a Task).

**Fix**
1. Add `portal/staff_notifications.py` with `notify_staff(capability, doc, subject, body, assignee=None)`:
   - Recipients: the assignee if set, else every enabled System User holding the capability's roles (`portal/staff.py::CAPABILITIES`).
   - Channel 1: **Notification Log** (`frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert", "document_type": doc.doctype, "document_name": doc.name, "subject": subject, "email_content": body}).insert(ignore_permissions=True)`). This lights up the Desk bell.
   - Channel 2: optional email to the shared inbox (`SALES_EMAIL`) through the same outbox (add a `staff_inbox` preference/recipient type to `portal/outbox.py` rather than calling `frappe.sendmail`).
   - Idempotent on `(doctype, name, event)`.
2. Call it after each submission above (after the insert succeeds, inside the same transaction so it rolls back together).
3. Include customer name, project, schedule and a Desk link (`/app/<doctype-slug>/<name>`) in the body.

**Acceptance:** submitting a quote request as a dealer creates Notification Log rows for sales staff (or the assignee) and one inbox email. Resubmitting the same idempotent request doesn't duplicate them.

### DESK-2 (P1): Auto-assignment and SLA for commercial requests

**Evidence:** `ilL-Document-Request` auto-assigns from `ilL-Request-Type.default_assignee_user/role` (`ill_document_request.py:177-203`, always the first user of the role, with no round-robin). Quote requests, order intakes, order changes and account requests are never auto-assigned, so `assigned_to` stays empty.

**Fix**
1. Add a Single doctype `ilL Portal Routing Settings` (or fields on an existing settings doctype) with, per queue (`quotes`, `orders`, `order_changes`, `accounts`, `support`): default assignee user, fallback role, SLA hours.
2. On insert of each request, set `assigned_to` (round-robin among enabled users of the role by fewest open items) and `due_date = now + SLA`.
3. Fix document requests' role assignment to use the same round-robin helper.

### DESK-3 (P1): Dealer replies on unassigned requests reach nobody

**Evidence:** `portal/conversations.py:285-310` `_notify`. When a dealer posts, `recipients = [doc.get("assigned_to") or doc.get("ill_support_owner")]`. If that's empty, nobody is notified.

**Fix:** when the recipient is empty, call `notify_staff(capability_for(doc.doctype), ...)` (DESK-1). Also use the item's real subject ("New reply on quote request QR-0042 from Acme Lighting") instead of the generic "A reply is available in your portal conversation".

### DESK-4 (P1): Make the portal conversation visible on Desk forms

**Evidence:** `public/js/desk_conversation.js` only adds a "Portal conversation" button that opens a dialog. There's no unread indicator, no preview, nothing inline.

**Fix**
1. On `refresh` of the forms listed in `desk_conversation.js`, render the thread **inline** in a dedicated HTML field or `frm.dashboard` section (reuse `window.PortalConversation(root)`).
2. Show an unread badge: "2 new customer messages", computed from `ilL-Portal-Message` rows after the last staff message.
3. Add a list-view indicator (`*_list.js` `get_indicator`) for "Waiting on staff" vs "Waiting on customer" using the existing `ill_next_action_by` where present.

### DESK-5 (P1): Desk forms need context and portal links

**Fix**
1. Add an "Open in portal" button to `ilL-Project`, `ilL-Project-Fixture-Schedule`, `ilL-Quote-Request`, `ilL-Quote-Offer`, `ilL-Order-Intake`, `ilL-Document-Request`, `Issue` (portal-originated) and `Sales Order` (when `ill_fixture_schedule` is set), opening `/portal/...` in a new tab.
2. `portal/queues.py` quotes queue: the projected fields are only `name, state, assigned_to, due_date, modified`. Add `customer`, `project`, `schedule`, `requested_by`. Do the same for `orders` (`customer` via Sales Order).
3. `public/js/quote_request.js`: "Prepare Quotation" prompts for Company every time. Default it to `frappe.defaults.get_user_default("Company")`, or skip the prompt when only one Company exists.
4. `doctype/ill_project/ill_project.js:26,31` hides **Collaborators unless the project is private**, but collaborators matter for non-private projects too (external architects and designers). Always show the table.

### DESK-6 (P1): Portal-created Issues lack Customer/Contact/Project

**Evidence:** `api/portal.py::create_support_ticket` (~2908) sets only `raised_by`, `subject`, `description`, `priority`, `ill_portal_order`.

**Fix:** set `customer` = actor's company, `contact` = the user's Contact, and an optional project link (add `ill_project` as a custom field if needed) so the Issue is filterable on Desk and appears on the Customer dashboard. Let the support form pick a project as well as an order.

### DESK-7 (P1): Request types configured on Desk never appear in the portal

**Evidence:** `ilL-Request-Type` has `portal_label`, `portal_icon`, `portal_description`, `sort_order`, `show_project_field`, `show_reference_field`, `show_fixture_field`, `show_item_field`, `show_priority_field`, `show_due_date_field` and a `custom_fields` table. `api/document_requests.py` exposes `get_request_types` (~161) and `get_request_type_fields` (~222), and `create_portal_document_request` accepts `custom_fields`. But `templates/pages/drawings.html:182-199` **hard-codes four types** (`shop_drawing`, `spec_sheet`, `installation`, `ies_file`) and `api/portal.py::_request_type_for_drawing_type` maps them by name. Custom fields are never collected.

**Fix**
1. Render the type picker from `get_request_types()` (active, sorted, with `portal_label`/`portal_icon`/`portal_description`).
2. On selection, fetch `get_request_type_fields(type)` and render the extra fields and show/hide flags dynamically.
3. Submit through `api/document_requests.py` (the newer endpoint) with `custom_fields`. Keep `create_drawing_request` as a compatibility wrapper.

**Acceptance:** creating a new active Request Type "Photometric Layout" with a required custom field "Ceiling height" on Desk makes it appear in the portal with that field, and the value is saved on the request.

### DESK-8 (P2): Shipment tracking is entered in a misleading field

**Evidence:** `portal/orders.py:28` `DELIVERY_TRACKING_FIELD = "vehicle_no"` (a documented product decision). Desk users see "Vehicle No", which nobody will think to use for a UPS tracking number, so notifications show nothing.

**Fix:** add custom fields on Delivery Note: `ill_carrier` (Select: UPS, FedEx, USPS, Freight, Other) and `ill_tracking_number` (Data), placed near `transporter_name`. Read them first and fall back to `vehicle_no`/`lr_no` for old records. Generate carrier tracking URLs in the portal (`https://www.ups.com/track?tracknum=...` etc.). Update `notifications.py::notify_shipment` accordingly.

### DESK-9 (P2): Desk "Customer" master pollution and duplicate end clients 🟨 DECISION

**Evidence:** dealers create end clients, architects, designers and GCs as ERPNext **Customer** records (`api/portal.py::create_customer` ~2758). `create_customer` refuses if a Customer with that exact name exists (`frappe.db.exists("Customer", name)`). Two dealers bidding on the same GC (common in lighting) means the second dealer **can't create or select it**, and the error reveals the record exists. Meanwhile the ERPNext Customer list fills with non-buying parties.

**Options for the owner**
- **A (recommended):** introduce `ilL-Project-Party` (dealer-scoped: `owner_customer`, `party_name`, `role` [End Client / Architect / Lighting Designer / GC], contact info). Project stakeholder fields link to it. Promote to a real Customer only when Sales quotes or bills that party directly. Migration: create Parties from existing Customers referenced by project role fields that have `owner` = a website user.
- **B:** keep Customer, but name portal-created customers with a dealer suffix/series and dedupe within the dealer only.
- **C:** keep as is and let staff merge duplicates manually.

### DESK-10 (P2): Offer expiry reminders

**Fix:** daily scheduler job `portal/offers.py::remind_expiring()`. For ISSUED offers whose `valid_until` is 3 days or 1 day away, `notify_user(..., "notify_quotes", ...)` the buyers (idempotent `event_key`), and add the item to the staff quotes queue as "Expiring soon".

---

## 6. Phase 4: Portal shell & design system (P2, biggest perceived-quality win)

### UI-1: One portal layout for every authenticated page

**Fix**
1. Create `templates/includes/portal_layout.html` (or `templates/portal_base.html`) that extends `templates/web.html` and provides:
   - the portal navigation (`includes/portal_navigation.html`);
   - blocks `portal_breadcrumbs`, `portal_header` (eyebrow, title, lead, actions, using the existing `.ill-hero` markup from `orders.html`), `portal_content`, `portal_script`;
   - a container with consistent width and padding (`main.container.ill-commerce`).
2. Convert pages to extend it, in this order: `portal.html`, `ill_projects.html`, `project.html`, `collaborators.html`, `resources.html`, `configure.html`, `configure_tape.html`, `edit_fixture.html`, `schedule.html`, `account.html`, `drawings.html`, `drawing_detail.html`, `ill_support.html`, `support_detail.html`, `products_catalog.html`, `product_detail.html`.
3. Navigation (`includes/portal_navigation.html`):
   - add **Drawings** (`/portal/drawings`, sections `portal/drawings`) and **Resources**;
   - give Products, Product Finder, Support and Account `aria-current` (they currently never highlight);
   - make it collapse into a horizontal scroller or menu below 768px;
   - optionally show counts ("Quotes 2") from UX-1's action data.
4. Page titles: `{% block title %}` must use `_()` and a consistent "Section · ilLumenate Portal" format (e.g. `ill_projects.html` has a raw `Projects`).
5. Standardize routes: add `/portal/schedules/<schedule>/lines/<line_key>/edit` for edit fixture (keep `/portal/edit_fixture` as a redirect).

**Acceptance:** every authenticated portal page shows the same header, nav and container. Visual check at 375px, 768px and 1280px.

### UI-2: Move inline CSS into the SCSS bundle and use tokens only

**Fix**
1. For each page's `<style>` block, create a partial `public/css/pages/_<page>.scss` scoped under a page class (`.ill-page-schedule ...`), import it from `illumenate_web.bundle.scss`, and delete the inline block.
2. Replace hard-coded hex colors (139 in `schedule.html`, 25 in `products_catalog.html`, 12 in `product_detail.html`, 2 in `portal.html`) with existing `--ill-*` tokens from `_portal_brand.scss`. Add a token if one is genuinely missing.
3. Reduce the 23 `!important` utility overrides in `_portal_brand.scss` once pages no longer depend on Bootstrap utility colors.
4. Add a check to `tools/check_portal_templates.py`: fail on `<style>` blocks longer than 20 lines in page templates and on hex colors in page templates.

### UI-3: One client-side interaction kit (stop the msgprint + reload pattern)

**Evidence:** `location.reload` after success in `schedule.html` (6), `project.html` (5), `collaborators.html` (2), `account.html` (1). There are 32 `msgprint` calls in `schedule.html` alone, raw `confirm()` in `collaborators.html`, and three different HTML-escape helpers (`schedule.html::_escapeHtml`, `product_catalog.js::escapeHtml`, `product_detail.js::_escHtml`).

**Fix:** add `public/js/portal_ui.js` (imported in the web bundle) exposing `window.PortalUI`:
- `call(method, args, {busy: buttonEl, successToast})`: a promise wrapper around `frappe.call` (POST). It normalizes `{success:false,error}` and HTTP errors into one rejected `Error` and toggles the button spinner/disabled state.
- `toast(message, tone)`: wraps `frappe.show_alert`.
- `confirm({title, body, confirmLabel, tone})`: a promise around a portal-styled modal (focus-managed). Replaces `confirm()` and `frappe.confirm`.
- `escape(str)`: one escape helper.
- `fieldErrors(form, errors)`: inline validation messages under fields instead of modal pop-ups.
Then migrate pages: update the DOM in place after success (status badge, row removed, name changed) instead of reloading. Keep a reload only for structural changes (e.g. auto-versioning navigates to the new schedule).

**Tests:** a JSDOM test for `PortalUI.call` covering success, `{success:false}`, an HTTP 417 with `_server_messages`, and a network error.

### UI-4: One status vocabulary everywhere

**Fix:** pass label/class helpers (already in `portal/status.py`) into every template. Replace:
- raw `{{ project.status }}` (`ACTIVE`, `ARCHIVED`) in `portal.html`, `ill_projects.html`, `project.html`; add `project_status_label/class` to `status.py`;
- JS maps in `schedule.html` (`changeStatus` ~4199, version history ~4720) with labels injected from the server (`{{ status_labels | tojson }}`);
- raw "DRAFT/READY" dropdown text (see REL-4).

### UI-5: Empty, loading and error states

**Fix:** use one `.ill-empty` component (exists in `_portal_commerce.scss`) and a skeleton loader for async sections (export history, version history, account records, which currently show "Loading..." text). Each async section needs an error state with a Retry button instead of a red alert.

### UI-6: Front-end performance

**Evidence**
- `hooks.py:38` loads **Font Awesome 4.7** (2016, unmaintained) from cdnjs on every page.
- `public/css/portal.css` `@import`s Google Fonts (render-blocking) and ships `Manrope-Variable.ttf` (TTF, not woff2).
- `illumenate_web.bundle.js` includes about **350 KB** of configurator code (`public/js/configurator/*`) on **every** website page, including login and public pages.

**Fix**
1. Split the web bundle: keep `portal_core.bundle.js` (portal.js, portal_ui.js, uploads, dialog, conversation) global, and load `configurator.bundle.js` only on configurator, schedule and edit pages via `{{ include_script("configurator.bundle.js") }}` in those templates.
2. Convert fonts to woff2 and self-host Poppins 400/600 (drop the Google `@import`). Add `<link rel="preload">` for the two primary weights.
3. Replace Font Awesome 4.7 with self-hosted SVG icons (Frappe ships `frappe.utils.icon`/SVG sprites) or FA 6 free, self-hosted. This is a large mechanical change: do it last and in its own PR, with a mapping table `fa-x` → new icon.

### UI-7: Accessibility pass

**Fix**
- Every icon-only button needs an `aria-label` (archive/unarchive/rename/delete buttons on projects and project pages only have `title`).
- Modals: `aria-labelledby`; focus management already exists in `portal.js` (keep it).
- Use `role="status"`/`aria-live` for async results.
- Respect `prefers-reduced-motion` for the `.portal-card:hover` transform.
- Colour contrast: check gold badges (`--ill-gold-200` on `--ill-gold-ink`).
- Form labels: `<label for>` on all inputs (many `project.html` labels lack `for`).
- Run `axe-core` in the existing Playwright suite (`tests/portal_e2e`) on each page.

---

## 7. Phase 5: Flow improvements (P1/P2)

### FLOW-1 (P1): Replace the Overview card grid with an Action Center

**Evidence:** `portal.html` is mostly static marketing cards ("Create and manage lighting projects..."). The hero repeats the logo. The useful data (counts) is buried in small badges, and nothing tells a dealer what needs their attention.

**Fix:** new `portal/action_center.py::for_user(user)` returns ordered action items, each with title, context, due date, deep link and tone:
1. Offers awaiting response (ISSUED, not expired), soonest expiry first, with "Expires in N days".
2. Order requests needing information (`ilL-Order-Intake.state == INFORMATION_NEEDED` / `CHANGES_PROPOSED`) and orders with `needs_action` (already computed in `portal/orders.py`).
3. Drawings awaiting the dealer's approval/review (`ill_next_action_by == "Customer"`).
4. Support tickets and conversations waiting on the customer.
5. Schedules with unconfigured lines (DRAFT with pending lines).
6. Pending invitations the user sent (unaccepted, expiring).
Layout: header "Good morning, {name}" without the logo hero; "Needs your attention" list (empty state: "You're all caught up"); a "Recent activity" row (projects, orders); quick actions (New project, Configure product, Request drawing). Remove the static description cards.

**Tests:** unit-test each action source with fixtures. Add a UI test for the empty state.

### FLOW-2 (P1): Schedule page shows the commercial thread and a guided next step

**Evidence:** after "Request Quote", the schedule page shows nothing about the request, its state or the resulting offer. The header has five same-weight buttons (Add Line, Design System, Create New Version, Request Quote, Convert to Sales Order), and "Request Quote" and "Convert to Sales Order" are both green.

**Fix**
1. Add a **progress stepper** at the top: Build → Ready → Quote requested → Quoted → Order requested → Ordered, highlighting the current step from `schedule.status` plus related records.
2. Add a **"Commercial" panel** listing quote requests (`ilL-Quote-Request` for this schedule: state, assigned staff, last message), offers (`ilL-Quote-Offer`: state, valid until, link to `/portal/quotes/<offer>`) and the order (`sales_order` link and status).
3. One **primary** action per state:
   - DRAFT → "Mark ready" (disabled with a reason listing unconfigured lines);
   - READY → "Request quote" (primary), with "Order directly" secondary (dealers only);
   - QUOTED → "Review quote" (primary, deep link to the offer);
   - ORDER_REQUESTED/ORDERED → "View order".
   Move "Create new version" and "Change status" into an overflow (⋯) menu.
4. Show an "Unconfigured lines: N" banner with a jump-to-first link.

### FLOW-3 (P1): Projects list that scales

**Evidence:** `ill_projects.py` loads **all** projects (`frappe.get_list` without limit) and hides archived ones client-side. There's no search, no sort and no schedule counts. Archive/unarchive buttons show for users who can't edit (the server rejects, but the UI offers it).

**Fix:** server-side search (name, customer), status filter (Active / Archived / All), sort (recent, name), pagination (20/page), mirroring `orders.html` (`.ill-toolbar`, `.ill-records`, `.ill-pager`). Show per project: schedules count, last activity, owner company badge, a privacy badge, and the next step from FLOW-2's logic (e.g. "Quote ready"). Only render archive actions when `can_edit_project` is true.

### FLOW-4 (P1): Invitations that actually arrive, and work for new users

**Evidence**
- `portal/accounts.py:314 invite()` creates the invitation and returns `invite_url`, but **sends nothing**. The UI (`public/js/portal_accounts.js:41`, `ill_project_fixture_schedule.js:571`) shows a read-only input and says "Send this one-use link to …".
- `accept_invitation.html` tells new users to "use the site's Sign Up option" (which may be disabled in Website Settings) and to "return to this link after signing in", opening `/login` in a new tab. It doesn't detect whether the user is already signed in.
- The Collaborators page has **no** "invite by email" action, so external architects and designers (the main use case) can't be invited from the portal.
- `api/portal.py::_send_collaborator_invite_email` (~3320) is dead code that calls `frappe.sendmail` directly.

**Fix**
1. In `invite()`, after insert, send the link through the outbox (`notify_user` needs a user; add an `email_invitation(email, subject, body, event_key)` path to `portal/outbox.py` for non-users, still logged in `ilL-Portal-Delivery`). Keep returning `invite_url` so the inviter can also copy it.
2. If the email has no User, create a **disabled-until-accept** Website User or use Frappe's `user.send_welcome_mail_to_user()` / reset-password flow so the recipient sets a password from the email. Accept with the token after password set (`redirect_to=/portal/accept-invitation#<token>`; keep the token in `sessionStorage` across the login hop).
3. Rewrite `accept_invitation.html`:
   - signed in as the invited email → show the project or company name and one "Accept" button;
   - signed in as a different user → explain and offer "Sign out and continue";
   - signed out → "Sign in" / "Create your account" buttons that return here with the token preserved.
4. Collaborators page: add "Invite by email" (email, name, VIEW/EDIT) calling `invite_project_collaborator`, plus a "Pending invitations" section with Resend and Revoke (`accounts.revoke_invitation` exists).
5. Delete `_send_collaborator_invite_email`.

### FLOW-5 (P1): Dealer onboarding from public pages

**Evidence:** `request_dealer_access.html` sends visitors to `/portal/account#companyManagement`, which requires login. Guests are redirected to bare `/login` and the anchor is lost. Copy is hard-coded English (no `_()`), and the icon is an emoji. Users with no company link who reach `/portal/projects/new` see an empty "Customer" select and a "New" button that fails for non-dealers.

**Fix**
1. Guests: show an inline **"Apply for dealer access"** form (company, name, email, phone, website, territory, message). It creates an `ilL-Account-Request` (type "Dealer application") via a guest endpoint protected by `rate_limit` plus a honeypot field, and notifies staff (DESK-1).
2. Signed-in users without a company: show the application form prefilled, not the account page.
3. `/portal/projects/new` for users without a company: show "Your account isn't linked to a company yet" with the application CTA instead of a broken form.
4. Wrap all strings in `_()`; use an SVG icon.

### FLOW-6 (P1): Configuration access for EDIT collaborators 🟨 DECISION

**Evidence:** `templates/pages/configure.py` redirects anyone without `can_view_catalog()` (dealers and staff only) to "Request dealer access". An EDIT collaborator (e.g. the lighting designer) can add lines to a schedule they can edit, but clicking **Configure** bounces them.

**Options:** (A, recommended) allow configuration when a `schedule` query parameter is present and the user `can_edit_schedule(schedule)`, while **hiding pricing/MSRP** for non-dealers (the configurator already has `can_view_pricing` concepts on the schedule page). (B) Hide Configure buttons for users who can't configure and explain why in a tooltip.

### FLOW-7 (P2): Company-wide support visibility 🟨 DECISION

**Evidence:** `portal/support.py::_conditions` shows a user only the tickets they raised. A dealer's purchasing manager can't see a colleague's open ticket about the same order.
**Option:** Dealers see all tickets raised by members of their company (and tickets linked to the company's orders). Non-dealer members keep "own only".

### FLOW-8 (P2): Project creation form clarity

**Evidence:** `project.html` labels the end client "Customer" and defaults it to the dealer's own company. There's also an "Owner company" concept (`owner_customer`) the user never sees. Create and edit each have their own duplicate "new customer" and "new contact" modals (4 modals, about 300 lines).

**Fix:** rename the label to **"End client"** with help text "Who is this project for? Choose your own company if it's internal stock or a showroom." Group stakeholders under a collapsible "Project team (optional)". Use one shared "new party/contact" modal component for create and edit. Show the owner company read-only ("Visible to: Acme Lighting team") next to the privacy toggle, with plain-language privacy help.

### FLOW-9 (P2): Version noise on the project page

**Evidence:** `project.py` lists every schedule version (`ORDER BY version_parent, version DESC`). Locked old versions clutter the list.
**Fix:** show only the latest version per `version_parent`, with "v3 · 2 earlier versions" expandable inline.

---

## 8. Product decisions needed from the owner (collect answers before the dependent tasks)

| # | Question | Blocks | Recommendation |
|---|---|---|---|
| D1 | Should end clients, architects, designers and GCs stay ERPNext **Customers**, or become dealer-scoped **Project Parties**? | DESK-9, FLOW-8, SEC-3 (scope of Customer reads) | Project Parties (option A). |
| D2 | May EDIT collaborators configure products (without pricing)? | FLOW-6 | Yes, without pricing. |
| D3 | Should dealers see all support tickets for their company? | FLOW-7 | Yes for Dealer role; no for non-dealer members. |
| D4 | Staff notification channel: Desk bell only, or also email to `sales@`? | DESK-1 | Both; email via outbox to the shared inbox. |
| D5 | Should invitations auto-create the Website User (with a set-password email) when none exists? | FLOW-4 | Yes. |
| D6 | Default assignees and SLA per queue (quotes, orders, changes, accounts, support). | DESK-2 | Owner provides names and hours. |
| D7 | Carrier list for tracking links. | DESK-8 | UPS, FedEx, USPS, Freight (no link), Other. |

---

## 9. Suggested PR sequence

| PR | Tasks | Size | Notes |
|---|---|---|---|
| 1 | SEC-1 + checker rule | S | Ship immediately. |
| 2 | SEC-3 (verify, then scope hooks + permlevel patch) | M | Needs staging verification first. |
| 3 | SEC-4 | S | Coordinate the n8n header change. |
| 4 | REL-1 + REL-2 | M | Pure server; broad but mechanical. |
| 5 | REL-6 (`require_login` + friendly 403/404) | S | |
| 6 | REL-4 (status menu, offer supersede, Desk warning) | M | |
| 7 | REL-3 (line_key + expected_modified) | M | Touches `schedule.html` JS; do it before UI-2 moves code around. |
| 8 | SEC-5 + FLOW-4 (collaborators + invitations) | L | |
| 9 | DESK-1 + DESK-2 + DESK-3 | L | Needs D4, D6. |
| 10 | DESK-4 + DESK-5 + DESK-6 | M | |
| 11 | DESK-7 (dynamic request types) | M | |
| 12 | UI-3 (PortalUI kit) + REL-10 small fixes | M | Foundation for UI work. |
| 13 | UI-1 (layout + nav) | L | Convert pages one or two per commit. |
| 14 | FLOW-1 (Action Center) | M | |
| 15 | FLOW-2 (schedule stepper + commercial panel) | M | |
| 16 | FLOW-3 (projects list) + FLOW-9 | M | |
| 17 | UI-2 (CSS extraction) + UI-4 + UI-5 | L | Mechanical; split per page. |
| 18 | SEC-2 escaping sweep + checker | M | Can run in parallel with 13–17. |
| 19 | FLOW-5, FLOW-8, REL-5, REL-7, REL-8, REL-9, DESK-8, DESK-10 | M | |
| 20 | UI-6 (bundles, fonts, icons) + UI-7 (a11y) | L | Last; icons are the biggest diff. |
| — | DESK-9, FLOW-6, FLOW-7 | — | After decisions D1–D3. |

---

## 10. Acceptance scenarios (run on staging after each phase)

1. **Hostile names:** create a project named `x');alert(1);//` and a schedule named `<img src=x onerror=alert(1)>`. Browse every page as owner, collaborator and company member. No script runs; names display literally.
2. **Dealer data isolation:** as Dealer A, the REST calls in SEC-3 return only A's data.
3. **Quote loop:** dealer requests a quote → sales staff get a Desk bell and inbox email → the request is auto-assigned → staff reply in the inline Desk conversation → the dealer gets an email deep link → login returns to the request → staff issue a Quotation → the dealer sees it in the Action Center and on the schedule's Commercial panel → the dealer accepts → an order request appears in the staff queue.
4. **Offer invalidation:** with an open offer, the dealer chooses "Back to draft" → sees the warning → confirms → the offer shows "Superseded" and Sales is notified.
5. **Two-tab race:** delete/move lines in two tabs → the correct line is affected or the user is told to reload.
6. **Invitation:** a dealer invites an external designer (no account) → the designer receives an email → sets a password → accepts → sees the project with EDIT → can configure (if D2 = yes) without pricing.
7. **Request types:** staff add a new Request Type with a custom field → it appears in the portal → the submitted value shows on the Desk form → the default assignee gets a Task/notification.
8. **Staff-created project:** sales staff create a project for Dealer B on Desk with Owner Company = B → B's dealers see it in the portal.
9. **Visual consistency:** every authenticated page shows the same nav/header at 375px, 768px and 1280px; axe reports no serious violations.
10. **Deep links:** every email template's link, opened while logged out, returns to the right page after login.

---

## 11. Out of scope / don't touch

- Pricing, BOM, manufacturing, QBO sync and Webflow publication logic (unrelated to this pass).
- The System Designer (`/portal/design`) and the Catalog Builder internals, beyond adopting the shared layout/nav.
- Historic docs in `docs/` other than updating the guides named in tasks (`WEBFLOW_LEAD_INTEGRATION_GUIDE.md`, `B2B_STAFF_OPERATIONS.md` for new staff notifications and routing, `DEALER_ROLE.md` for the new master scoping).
- Don't edit ERPNext/Frappe core JSON. Use patches with Property Setters / Custom Fields.
- Don't skip, disable or loosen existing tests to make a change pass.
