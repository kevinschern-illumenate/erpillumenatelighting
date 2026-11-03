# Dealer experience hardening plan — November 2026

Assessment date: 2026-11-03. Baseline: `1d8950f` ("Fix syntax error in request_spec_sheet function headers").
This plan is assessment-only. No application code was changed while writing it.

Goal: make the B2B dealer portal and the staff authoring/Desk tools feel professional, reliable and fast,
with a strong emphasis on **configuring products and adding pictures/products**, without breaking any
existing route, API, document, permission or historical record.

## Owner decisions (2026-11-03)

| # | Decision | Plan impact |
|---|---|---|
| D1 | Each template type's **`hero_image` is the main product image**. | 5.1, 5.2, 5.4, 3.7. All six template types already have it: Fixture, Tape-Neon, LED-Sheet, Extrusion-Kit, Driver, Controller. |
| D2 | **Add HEIC support.** | 4.2 adds the `pillow-heif` dependency and server-side conversion. |
| D3 | **Tape/neon lines may be repriced** under unified rounding. | 6.3 has no legacy-rounding flag. Unissued lines reprice; issued quotes/orders stay frozen (guardrail 5). |
| D4 | **Do not modify Webflow preview origins for now.** | 1.3 is deferred. `webflow_auth.py` CORS is unchanged. |
| D5 | **All dealers get the new features.** | No pilot cohort. Flags remain as default-on kill switches (guardrail 4, Phase 9). |

---

## 1. Baseline evidence (what was actually checked)

| Check | Result |
|---|---|
| `python3 -m compileall -q illumenate_lighting tools` | Pass — no syntax errors (latest commit fixed the last one) |
| `node --check` on all 163 tracked non-vendor JS files | Pass — 0 failures |
| JSON parse of all 224 app JSON files (DocTypes, fixtures) | Pass |
| Every module in `patches.txt` (70 entries) exists | Pass |
| `python -B -m unittest discover -s tests/portal_unit` | 1,142 run, **1,115 pass**; all 27 errors are `ModuleNotFoundError` (jsonschema, PIL, pypdf, reportlab, yaml, jinja2) — environment only, no assertion failures |
| `tools/fixture_builder/tests` | 12 run, 4 errors — all missing `yaml` |
| Ruff | Not installable in this workspace (no PyPI). `b2b-contracts.yml` installs it; `linter.yml` runs it through pre-commit **only on pull requests** |

Conclusion: the tree is syntactically healthy. Most risk is in **behaviour, UX consistency, maintainability
and unverified Cloud acceptance**, not in obvious breakage.

### Audit claims that were checked and **rejected** (do not schedule work for these)

| Claim | Reality |
|---|---|
| `/portal/configure-kit` is a 404 | `hooks.py:183-184` redirects it to `/portal/configure?category=Extrusion%20Kit`. Only a browser smoke test is needed. |
| Dealers cannot duplicate a schedule line | `schedule.html:982,3069` → `api/portal.py:1675 duplicate_schedule_line` → `ill_project_fixture_schedule.py:1328 duplicate_line`. Exists. |
| Internal notes may leak to dealers | `portal/conversations.py:65,93,128,257-258,307` filters on `visibility == "Customer"` and rejects non-staff `Internal` posts server-side. |
| Upload validation is extension-only | Client is extension-only, but `portal/file_validation.py:24-59` enforces size, `%PDF-` signature, page count, and PIL decoding with a pixel cap. |
| Unconfigured-line check is client-only | Server enforces it in `ill_project_fixture_schedule.py:182-189`. |
| `portal/conversations.py`, `staff.py`, `queues.py`, `action_center.py` are missing | They exist under `illumenate_lighting/illumenate_lighting/portal/`. |

---

## 2. Non-breaking guardrails (apply to every work item)

1. **Additive schema only.** New fields are added with defaults and `no_copy` where appropriate. Fields are
   never renamed or dropped in this program; deprecated fields (e.g. `ilL-Webflow-Product.tape_spec`) are hidden
   and read-only first, then removed in a separate release after a data check.
2. **Patches are idempotent and guarded** (`has_column`/`exists` checks, like the existing patches), listed in
   `patches.txt`, and run twice in CI (`ci.yml` already double-migrates).
3. **Whitelisted API signatures are frozen.** New parameters must be optional, accept Frappe form strings (see the
   blank-index regression in `DEPLOY_AUDIT_2026_10_22.md`), and keep the old response keys. New behaviour lives on new
   endpoints. Desk/n8n/Webflow callers are external consumers.
4. **Kill switch for every dealer-visible change.** Reuse `portal/site_flags.py` with flags that are **on for all dealers
   by default** (D5). They are not used for pilot gating; they exist so a feature can be switched off without a deploy
   if it misbehaves.
5. **Historical documents are immutable.** Never rewrite issued builds, packets, quote offers or publication jobs
   (`build_immutability.py`, publication revisions). New logic applies to new records only.
6. **Server is authoritative.** Every client-side QoL feature (bulk edit, import, presets) must call server
   endpoints that re-run the same validation/permission path as single-line edits (`portal/access.py`).
7. **Extract, don't rewrite.** When splitting monoliths (`schedule.html`, `edit_fixture.html`, `desk_dialog.js`),
   move code verbatim into modules first (behaviour-identical commit), add tests, then improve.
8. **Definition of done per item:** unit tests (`tests/portal_unit`), UI tests (`tests/portal_ui/*.test.cjs`) where
   the item touches JS, `node --check` for every changed DocType script (`desk_scripts.test.cjs` pattern),
   `tools/check_portal_templates.py` for templates, installed-site test where the Frappe dispatcher is involved,
   and a docs update.
9. **Release discipline:** every change goes through a PR so `linter.yml` and the upgrade rehearsal run. Pushing
   directly to `main` bypasses both (`DEPLOY_AUDIT_2026_10_22.md`, "Why regressions escaped").

---

## 3. Phase plan overview

| Phase | Theme | Est. effort | Depends on |
|---|---|---|---|
| 0 | Safety net, CI and release hygiene | 3–4 days | — |
| 1 | Correctness and security fixes | 1 week | 0 |
| 2 | Portal foundation: modularize, one API/error/loading layer, query batching | 2–3 weeks | 0 |
| 3 | Dealer schedule & configuration QoL | 3–4 weeks | 2 |
| 4 | Pictures and uploads for dealers | 2 weeks | 2 |
| 5 | Product and media authoring for staff | 3–4 weeks | 0 (parallel to 2–4) |
| 6 | Configurator consistency and performance | 3 weeks | 1 |
| 7 | Desk / internal tooling | 2 weeks | 2 |
| 8 | Visual, accessibility and mobile polish | 2 weeks (rolling) | 2 |
| 9 | Cloud acceptance and all-dealer rollout | ongoing | each phase |

Priority labels: **P0** = do before dealer-facing expansion; **P1** = high value; **P2** = polish.

---

## Phase 0 — Safety net and release hygiene

| # | Pri | Item | Detail | Done when |
|---|---|---|---|---|
| 0.1 | P0 | Run lint on every push | `linter.yml` runs only on `pull_request`. Add `push: branches: [main, develop]`, or add a pinned `ruff check` step to `ci.yml`. Keep the current 656-diagnostic baseline from `tools/check_b2b_changes.py` so only *new* diagnostics fail. | A push with a new Ruff error fails CI |
| 0.2 | P0 | Upgrade rehearsal on push to main | `ci.yml:111` runs the upgrade rehearsal only on PR/dispatch. Enable it on `push` to `main`, or protect `main` and require PRs. | Branch protection or CI change recorded |
| 0.3 | P0 | Dev/test dependency manifest | Unit tests need `jsonschema Pillow pypdf reportlab PyYAML Jinja2`. Add a `[project.optional-dependencies] test` group in `pyproject.toml` (match the list in `b2b-contracts.yml:24`) and a one-line test command in `README.md`. | The full suite runs from a clean checkout with one install command |
| 0.4 | P0 | Golden-path smoke test list | Turn the 10 most common dealer journeys (login → project → schedule → add/configure line → upload photo → request quote → accept → order → drawing reply → support ticket) into `tests/portal_e2e/portal.spec.cjs` cases if they aren't already among the 27. | Runs against the staging site before each release |
| 0.5 | P1 | Route inventory test | Add a test that builds the set of `website_route_rules` + `templates/pages/*` and checks that every route referenced in `desk_portal_links.js`, `shared_configurator.js` and `ill_document_request.py` resolves. This also covers the kit redirect. | Test fails if a referenced route disappears |
| 0.6 | P1 | Close remaining deploy-audit items | From `DEPLOY_AUDIT_2026_10_22.md` "Remaining application findings": (a) Webflow direct sync button hard-codes `brand: 'lighting_206'`; (b) completion polling can accept an earlier `Synced`; (c) v2 trigger role mismatch between Catalog Publisher and integration capability. Fix (a) by reading target brands from the product; fix (b) by polling a job id/revision; fix (c) by running `claim` in an enqueued worker under the integration user. Keep both permission checks. | Regression tests for each, plus a staging run |

**Phase 0 status** (branch `feat/phase-0-safety-net`, PR #393):

| # | Status | Commits | Notes / deviations |
|---|---|---|---|
| CI | Done | `6209931`, `b424701` | Pre-existing main failures fixed first. The MariaDB client failed Setup with `TLS/SSL error: SSL is required`, so `~/.my.cnf` now sets `skip-ssl` for the CI service container. Three `desk_scripts.test.cjs` tests still mocked the retired webhook `fetch`. |
| 0.1 | Done | `844343e` | Deviation: `linter.yml` (pre-commit over the whole tree) fails on existing whitespace and import debt, so it stays PR-only. B2B contracts now lints every pushed commit range (`github.event.before`, else `HEAD^`) through the baseline-aware `tools/check_b2b_changes.py`, so only new Ruff diagnostics fail. |
| 0.2 | Done | `6209931` | The upgrade rehearsal also runs on push to `main` and uses the pre-push SHA as its base. |
| 0.3 | Done | `3c8a923` | `pip install -e ".[test]"`. `tests/portal_unit/test_dev_dependencies.py` keeps the extra in sync with CI. |
| 0.4 | Done (staging run pending) | `5793931` | Added three journeys. The first, project → schedule → photo upload → support ticket, also checks that a foreign dealer is denied. Offer accept-once and drawing change requests need staff-prepared records, so they skip with a reason until the manifest's `golden` block names them. Existing specs already cover configuring and saving lines and requesting quotes. CI only lists the specs. |
| 0.5 | Done | `f034566` | `tests/portal_unit/test_route_inventory.py` scans every `/portal` literal in the app, not only the three named files. |
| 0.6 | Done (staging run pending) | `b424701` | Sync requests every enabled target brand and polls `get_sync_progress(since=…)` per brand, so an earlier `Synced` no longer counts. Triggers `request` as the caller (catalog check). An after-commit worker `claim`s as the least-privilege `publication-worker@illumenate.lighting` user (integration check, created by patch `create_publication_worker_user`; override via site config `ill_service_users`). The trigger responses' `jobs` key now lists requested jobs rather than claimed ones. |

---

## Phase 1 — Correctness and security fixes

| # | Pri | Item | Where | Fix | Safety notes |
|---|---|---|---|---|---|
| 1.1 | P0 | Tape/neon run count placeholder | `api/tape_neon_configurator.py:4136` (`TODO: determine actual run count`) | Derive `runs_count` from the same run-splitting used by `tape_neon_power.py`/`linear_power.py` so the reported count matches the BOM/feeds | Display/report field only. Add tests for 1, 2 and N runs, and for runs limited by voltage drop versus watts. Old saved snapshots keep their stored value. |
| 1.2 | P1 | QBO webhooks run as Administrator | `api/qbo_sync.py:136`, `api/qbo_invoices.py:45` | Create a dedicated `QBO Integration` system user with the minimum DocType perms (install patch); `set_user` to it. Add a raw-body size cap before JSON parsing and reject a missing/empty secret. | Verify all sync write paths under the new user on staging first; fall back via site config flag. |
| 1.3 | — | **Deferred (D4)** — credentialed CORS by suffix | `api/webflow_auth.py:28` accepts any `*.webflow.io` / `*.vercel.app` | **No change for now.** Recorded as a known risk only. Revisit when the owner decides to restrict preview sites. | Do not touch `webflow_auth.py` CORS logic in this program |
| 1.4 | P1 | Guest endpoint hardening | All `allow_guest=True` endpoints (product finder public, public sheet, driver catalog, Webflow configurator/leads/auth, dealer applications, account requests) | Add `@rate_limit` where missing, payload-size caps and schema validation. Write a test that enumerates guest endpoints and asserts each has a rate limit. | No signature changes |
| 1.5 | P2 | f-string SQL in patch | `patches/copy_minimum_bend_to_side_bend.py:21` | Identifier comes from a fixed tuple, so this is low risk. Switch to `frappe.qb` to satisfy semgrep. | Patch has already run on existing sites; only fresh installs re-run it. |
| 1.6 | P1 | Broad `except Exception` swallowing catalog errors | `tape_neon_configurator.py:893,1417,1585,2335,2454`; `led_sheet_configurator.py:597`; `extrusion_kit_configurator.py:576,709,1211,1239,1250`; `templates/pages/schedule.py:749,909,949` | Narrow to expected exceptions, `frappe.log_error` with template/line context, and return a structured, dealer-readable error code (see 2.3) | Behaviour for the expected case is unchanged; unexpected cases become visible in the Error Log |
| 1.7 | P2 | Driver option N+1 | `api/driver_catalog.py:41,79` (`frappe.get_doc` per row, up to 200) | Bulk-load `ilL-Spec-Driver` parents and the `input_protocols` child rows with two `get_all` calls. Batch the `Item.disabled` lookup. | Pure refactor; add a test asserting identical output for fixture data |
| 1.8 | P2 | Hooks doing synchronous external work | `hooks.py` `doc_events` for Webflow sync/listing propagation | Audit each handler. Anything that does network I/O or touches many records moves to `frappe.enqueue(..., enqueue_after_commit=True)` with an idempotency key. | Keep cheap validation synchronous. Order-dependent handlers stay as they are. |

**Phase 1 status** (branch `feat/phase-1-correctness`, stacked on Phase 0):

| # | Status | Commits | Notes / deviations |
|---|---|---|---|
| 1.1 | Done | `ef5878b` | The TODO sat in `_calculate_accessory_qty`, which sizes `PER_RUN` mounting accessories. That endpoint has no tape spec inputs to re-split runs, so `get_mounting_accessories` gains an optional `runs_count` (form strings accepted, clamped to 1–1000, default 1). The tape step and the Webflow mounting call pass `computed.runs_count` from the configurator's run split. `tests/portal_unit/test_tape_run_count.py` covers 1, 2 and N runs, and watt- versus voltage-drop-limited splits. Saved snapshots are unchanged. |
| 1.2 | Done (staging run pending) | `f042b23` | Signed receivers use `qbo_sync.read_signed_json()`: a 256 KiB body cap (413), then HMAC (401; a blank secret never verifies), then JSON (400). They then call `become_integration_user()`, which switches to `qbo-integration@illumenate.lighting` (roles `ilL Integration` and `Accounts User`, created by patch `create_qbo_integration_user`). A missing or disabled user returns 503 and is logged. Rollback flag: site config `qbo_webhooks_run_as_administrator: 1`. Staging must confirm every write path (invoice/payment/bill link, frozen-account checks) under the new user. |
| 1.3 | Deferred (D4) | — | Not touched. |
| 1.4 | Done | `b7bb31d`, `52bd656` | All 25 unthrottled guest endpoints now have `@rate_limit` directly under `@frappe.whitelist`. Limits per IP per minute: 600 for read/configurator calls, 120 for `get_session`/`spec_sheet`, 300 for `get_user_context` (decorator only, CORS untouched per D4), 60 for `health_check`, 30 for `create_complex_fixture_session`. `get_related_products.limit` is clamped to 1–24. New `api/guest_payload.py` caps guest JSON at 64 KiB, and Webflow configurator `selections` must be an object. Both failures raise `JSONDecodeError` subclasses, so existing handlers keep their `"Invalid selections JSON"` response. `tests/portal_unit/test_guest_endpoints.py` enumerates every `allow_guest` function in the app. Deviation: "schema validation" is limited to size and object shape, because field-level validation already happens in each configurator's validator. |
| 1.5 | Done | `b22edc7` | Same WHERE semantics through `frappe.qb`. |
| 1.6 | Done | `27dfd85` | New `portal/errors.py` has `portal_error`/`PortalError` (2.4 scaffold) and the `failure()` boundary. Expected validation/permission errors keep their message and gain `error_code`. Unexpected errors are logged with context and traceback (`defer_insert`) and return a generic message with the Error Log reference (`error_code: internal_error`, matching `api/portal.py::_handle_error`). Save-to-schedule sites roll back partial writes on POST. Deviation: unexpected exceptions are still caught at the boundary instead of propagating, because frozen endpoints must keep the `{"success": False, "error"}` shape. `led_sheet_configurator.py:597` already rolls back and re-raises, so it is unchanged. Schedule display helpers still return `{}` so one broken record does not break the page; they now log tracebacks. |
| 1.7 | Done | `21b3564` | `_load_drivers` makes three `get_all` calls (specs, `ilL-Child-Driver-Input-Protocol`, `Item.disabled`). A missing spec still raises through `get_doc`. |
| 1.8 | Done (audit; no handler moved) | `9ae67ea` | No `doc_events` handler does network I/O. QBO bills already use `enqueue_after_commit`, mail goes through `portal.outbox`, and Webflow handlers only flag rows Pending for the publication worker. `manufacturing_generator.on_sales_order_submit` touches many records but stays synchronous. It is order-dependent, idempotent (`skip_if_exists`), runs permission checks as the submitting user, and reports to staff through msgprint. `tests/portal_unit/test_doc_events_audit.py` guards against new direct HTTP/sendmail calls in hook handlers. |

---

## Phase 2 — Portal foundation (prerequisite for most QoL work)

The schedule page is the dealers' main workspace: `templates/pages/schedule.html` (3,990 lines, about 26
`frappe.call`s inline) plus `schedule.py` (1,055 lines). The fixture editor is `edit_fixture.html` (1,492 lines).

| # | Pri | Item | Detail |
|---|---|---|---|
| 2.1 | P0 | Extract schedule JS verbatim | Move the inline script (roughly `schedule.html:1800-3990`) into `public/js/portal/schedule/{lines,actions,exports,packets,uploads,pricing,reorder}.js` loaded through `illumenate_web.bundle.js`. Pass server context through a single `<script type="application/json" id="schedule-context">` block instead of inline Jinja interpolation inside JS. Commit 1 must not change behaviour; prove it with `tests/portal_ui` plus a manual run of the golden path. |
| 2.2 | P0 | Same for `edit_fixture.html` and `configure_tape.html` | Reuse the existing `public/js/configurator/*` step modules. `configure_tape.html:140-315` duplicates unit controls from `includes/configurator_tape_neon_form.html`, so keep one. |
| 2.3 | P0 | One portal API layer | Add `PortalAPI.call(method, args, {button, form, retry})` on top of the existing `portal_ui.js`. It returns promises, sets a consistent loading state on the triggering button, maps server field errors to inline messages, and shows one toast style. Migrate callers gradually. `portal_call_compat.js` (global `frappe.call` patch) stays until the last caller has moved, then gets removed. |
| 2.4 | P0 | Structured errors from the server | New helper `portal_error(code, message, field=None, hint=None)` that raises a `frappe.ValidationError` subclass with `exc.portal_payload`. Configurators/schedule endpoints use it. Messages tell the dealer what to change ("Reduce this run to 16 ft or add a power feed"), not "Unable to check kit options" (`kit_steps.js:33,46`, `coordinator.js:548`). |
| 2.5 | P1 | Safe rendering helpers | Replace ad-hoc `innerHTML` with user data (`portal_ui.js:18`, `portal.js:45-61,90`, `order_detail.html:326`, `webflow_portal.js:233-277`, `portal_order_intake.js:9-17`) with a tagged-template `html\`\`` helper that escapes by default. Add jsdom tests that feed `<script>`/quotes/Unicode through each renderer. |
| 2.6 | P1 | Batch schedule context queries | `schedule.py:280-365, 568-730, 809-845` do per-line `get_value`s. Collect all template/finish/lens/driver/tape/item names first, then do one `get_all` per DocType and build dicts. Add a test that counts queries for a 50-line schedule (patch `frappe.db.get_value`/`get_all` in the unit doubles). |
| 2.7 | P1 | Other N+1s | `collaborators.py:45-46` (`exists` + `get_doc("User")` per collaborator), `templates/pages/portal.py:39-49,85` (per-project labels), `resources.py:37-48` (documents per product). |
| 2.8 | P1 | Status badge allow-list | `schedule.html:132-150` builds classes from server values. Map them through a fixed dict in Python. |
| 2.9 | P2 | URL-encode path segments | `schedule.html:113-126` uses `|e` in hrefs, so switch to `|urlencode` for document names. |

**Phase 2 status** (branch `feat/phase-2-foundation`, PR #395, stacked on Phase 1):

| # | Status | Commits | Notes / deviations |
|---|---|---|---|
| 2.1 | Done (verbatim extraction; manual golden-path run pending on staging) | `a160839`, `ec72089` | The inline script now lives in `public/js/portal/schedule/{context,lines,uploads,actions,packets,exports,reorder,versions,pricing,new}.js`. Server values and 40 translated strings come from one `<script type="application/json" id="schedule-context">` block. The only changed lines are the 72 Jinja interpolations. Deviation: the scripts are static classic `<script src>` files with a content-hash `?v=`, not part of `illumenate_web.bundle.js`. The esbuild bundle wraps code in an IIFE, which would hide the global functions that `onclick` handlers and other sections call. `check_portal_templates.py` checks that the context JSON parses and that its i18n keys match `scheduleText()` calls. |
| 2.2 | Done (verbatim extraction; manual edit-line run pending on staging) | `da7bb16`, `56a66a0`, `565ba66`, `ea50497` | The `edit_fixture.html` inline script moves to `public/js/portal/edit_fixture/page.js`, and the `configure_tape.html` boot moves to `public/js/portal/configure_tape/page.js`. Server values come from `#edit-fixture-context` / `#configure-tape-context` JSON blocks, and the four run-table headings use `editFixtureText()` with server translations. A new shared `portal/page_scripts.script_version(folder)` adds the content-hash `?v=`. `configure_tape.html` now renders `includes/configurator_tape_neon_form.html` instead of its stale copy, so one form remains. Deviations: same static-script approach as 2.1. The edit-fixture script stays one file and is not split into `public/js/configurator/*` step modules: those modules are the scoped classes the `/portal/configure` coordinator uses, while `edit_fixture` still runs its own global functions, so porting it is a behaviour change left for a later commit. The legacy `/portal/configure-tape` route redirects before rendering, so the include swap is not dealer-visible. |
| 2.3 | Scaffold done (callers migrate gradually) | `3404d0d` | `PortalAPI.call(method, args, {button, form, retry, ...})` sits on top of `PortalUI.call`. It keeps the triggering button busy, shows an inline field error or one toast, and retries only after transport failures. The kit steps now show the server's explanation. `portal_call_compat.js` stays until the last caller has moved. |
| 2.4 | Scaffold done | `3679729` | `portal_error()` attaches `{code, message, field, hint}` to the JSON error response as `portal_error` and msgprints like `frappe.throw`. `failure()` retracts both when it converts the error into the legacy `{success: False}` reply. Configurator call sites move to it with 2.2 and Phase 6. |
| 2.5 | Done | `95b1150` | `PortalUI.html\`\`` escapes every interpolated value and composes nested fragments and arrays; `PortalUI.raw()` marks trusted static markup. `plain()` now parses server text in an inert `DOMParser` document; the old detached `<div>` belonged to the live document, so `<img onerror>` could run. `portal.js` toasts and loading labels use text nodes, and the order-intake scope summary uses `html\`\``. Re-verified without change: `order_detail.html:326` (static dialog markup; values set via `.value`/`textContent`) and `webflow_portal.js:233-277` (static `<option>`, labels via `textContent`). jsdom: `tests/portal_ui/safe_render.test.cjs`. |
| 2.6 | Done | `eb94ac1` | New `portal/schedule_lookup.py`: `Lookup` prefetches each related DocType with one chunked `get_all` and loads each configured record once per request (a fixture was previously loaded up to three times: stock, display, MSRP). `prefetch_schedule()` warms it for the schedule page and the dealer pricing API (`api/portal.py`, same loop). The display and MSRP helpers take an optional `lookup` and fall back to the original per-row reads without one. `tests/portal_unit/test_schedule_batching.py` runs a 50-line schedule through both paths, asserts identical output, no `get_value`/`exists` calls and at most 18 `get_all`s. Deviation: `Item Price`/`ilL-Spec-Driver` "first match" now uses `modified desc` explicitly; it only differs if an item has duplicate Standard Selling prices. |
| 2.7 | Done | `ba06129` | `collaborators.py`: one `User` `get_all` instead of `exists` + `get_doc` per collaborator. `resources.py`: one documents query for all products, grouped in memory, order kept. Deviation: `templates/pages/portal.py` was already batched (`project_parties.labels()` is one query, and `_get_user_customer_name` runs once per page), so it is unchanged. Tests: `tests/portal_unit/test_page_batching.py`. |
| 2.8 | Done | `c3ab8c4` | `status.BADGE_TONES` + `badge_tone()` and the `ill_badge_tone` Jinja method (hooks `jinja.methods`). The schedule badges built from computed context (system-design tone/review, request/offer/order status classes) and the project system-design badge go through it; the schedule/project status helpers already map through fixed dicts. The template checker renders a hostile `status_class` and asserts every `badge-*` class is allowed; a unit test checks every `*_STATUS_META` class is an allowed tone. |

---

## Phase 3 — Dealer schedule and configuration quality of life

All items ship to every dealer (D5), each with a default-on `site_flags` kill switch.

| # | Pri | Feature | Design | Reuses |
|---|---|---|---|---|
| 3.1 | P0 | **Durable draft autosave** | Today a line draft only lives in `sessionStorage` (`schedule.html:1860-1861,3035-3036`) and vanishes with the tab. Add `ilL-Configurator-Session`-backed drafts (the DocType exists) keyed by user+schedule+line_key, saved with debounce, plus a persistent "Saved / Saving… / Unsaved" indicator and a "Restore draft from <time>" prompt. Keep sessionStorage as an offline fallback. | `ill_configurator_session`, `api/configurator_session.py` |
| 3.2 | P0 | **Configure similar / copy configuration** | Line duplicate already exists. Add "Copy to another schedule/project" and "Configure similar" (opens the configurator pre-filled from the line's canonical inputs with nothing saved until the dealer confirms). Copy line documents through `portal/line_documents.py:113 clone`. Never copy built Item/BOM or price; recompute them (same policy as reorder in the implementation status). | `duplicate_line`, `configuration_reopen.py`, `line_documents.clone` |
| 3.3 | P0 | **Bulk edit** | Row checkboxes with select-all, plus a sticky action bar: set quantity, room/location, designation/type, notes; delete; move; "Request drawings for selected". One server endpoint `bulk_update_lines(schedule, line_keys, changes, expected_modified)` that loops through the same single-line validator inside one transaction with optimistic concurrency. All or nothing, with per-line error report. | Existing stale-edit guards in `api/portal.py` |
| 3.4 | P1 | **Schedule import (CSV/XLSX)** | Downloadable template (Type, Qty, Location, Description, Part Number, Notes, Length). Upload → column-mapping screen → server dry-run that returns per-row status (ok / needs configuration / error) → commit. Lines without a decodable part number come in as "Unconfigured" so the existing readiness logic picks them up. Export CSV already exists (`schedule.html:1068-1073`, `api/exports.py`), so make the import template round-trip with it. | `exports.py`, `is_unconfigured` |
| 3.5 | P1 | **Paste / decode a part number** | New `decode_part_number(pn)` that walks the existing part-number builder rows (`ill_child_pn_builder_row`) in reverse to rebuild selections. Ambiguous or obsolete segments are reported, never guessed. Used by the import (3.4), an "Add by part number" box on the schedule, and the product finder. | PN builder child table, `group_part_number.py` |
| 3.6 | P1 | **Favorites / company presets** | New `ilL-Configuration-Preset` (owner, customer, family, canonical inputs JSON, label, shared_with_company). Add "Save as preset" in every configurator and "Start from preset" in Add Line. Store canonical normalized inputs (`configuration_contract.py`), and re-validate on use so stale presets surface a clear message. | `configuration_contract` normalization |
| 3.7 | P1 | **Visual Add Line picker** | Card grid with thumbnail, family, key specs, search/filter (already called for in `B2B_PORTAL_PRODUCT_AUDIT_AND_ROADMAP.md:354`), "Recently used" and presets. Each card shows the template's `hero_image` through the 5.4 resolver (D1). | `product_projection.py`, `includes/product_type_chooser.html` |
| 3.8 | P1 | **Live price + availability in configurator** | One summary panel per configurator: part number, price breakdown (when the dealer's pricing visibility allows it), stock/lead-time class from `item_availability.py` and `ill_attribute_lead_time_class`, all labelled "estimate" until quoted. | `pricing_utils.py`, `item_availability.py` |
| 3.9 | P1 | **Stale configuration badge** | When a line's stored dependency revision (`configuration_contract.py:167-173`) differs from the current template/spec revision, show "Catalog updated — review" with a one-click re-validate. Never change the line automatically. | Dependency revisions already hashed |
| 3.10 | P2 | Undo for destructive actions | Delete/move/bulk actions show a 10-second "Undo" toast backed by server soft-delete (keep the row JSON in the action receipt; restore re-inserts with the same line_key). |
| 3.11 | P2 | Schedule activity timeline | Read-only timeline built from `Version` + portal events (`ilL-Portal-Event`) for line add/edit/delete, status changes and exports, filtered to dealer-visible events. |
| 3.12 | P2 | Collaborator conflict notice | If `modified` changed since page load (the guard already exists), show "Updated by <user> at <time> — reload / compare" instead of a generic error. |
| 3.13 | P2 | Keyboard and power-user aids | `/` focuses search, `n` adds a line, `Esc` closes dialogs, arrow keys move between rows. Show a help overlay on `?`. Add a keyboard alternative to drag reorder (`_schedule.scss:132-170`). |
| 3.14 | P2 | Persist pricing toggle | Store "show pricing" per user in `ilL-Portal-User-Settings` (DocType exists) instead of inline toggle state (`schedule.html:209-220`). |

---

## Phase 4 — Pictures and uploads for dealers

Current state: one shared `public/js/portal_uploads.js` (PDF/JPEG/PNG, 20 MiB, 10 files, sequential `fetch`,
no progress/preview). Server validation is solid (`portal/file_validation.py`). Upload entry points include
`drawings.html:99`, `ill_support.html:222`, `schedule.html:1407,1601`, `portal_order_intake.js`, and
`portal_line_documents.js`.

| # | Pri | Item | Design |
|---|---|---|---|
| 4.1 | P0 | **Shared upload widget** | `PortalUploader` component with a drag-and-drop zone and "Browse" button, a per-file row (thumbnail for images, PDF icon + page count after upload, name, size), XHR upload with progress bar, cancel, retry, and remove, plus bounded concurrency of 3. Enforce per-file 20 MiB / 10 files (unchanged), add an aggregate cap, and show clear reasons for rejection. Replace every file input above; server endpoints stay the same. |
| 4.2 | P0 | **Phone photos that just work, including HEIC (D2)** | **Client:** read EXIF orientation and normalize. If a JPEG/PNG is >4096 px or >8 MiB, downscale with canvas to ≤4096 px JPEG q≈0.85 before upload (stays under `MAX_IMAGE_PIXELS = 40_000_000`). Accept `.heic/.heif` and `image/heic`/`image/heif` in `portal_uploads.js`, `portal_order_intake.js:17` and `portal_line_documents.js:9`, sending HEIC to the server unchanged (Chrome/Edge/Firefox can't decode it in the browser). **Server:** add `pillow-heif` to `pyproject.toml` `dependencies` and call `pillow_heif.register_heif_opener()` lazily inside `file_validation.py`. Accept HEIC only when the `ftyp` box brand is `heic/heix/hevc/heim/heis/mif1/msf1`, decode with Pillow under the same pixel cap, apply `ImageOps.exif_transpose`, strip EXIF (including GPS), and **store a converted JPEG** (q≈0.9) as the File every browser and the PDF/packet pipeline can read. Optionally keep the HEIC original privately for traceability. The 20 MiB cap applies to the uploaded bytes. **Deploy check:** confirm a `pillow-heif` wheel exists for the Frappe Cloud Python/arch (the bench uses Python 3.14) **before** merging, because a failed wheel build breaks the image build (`DEPLOY_AUDIT_2026_10_22.md`). If it is unavailable, pin a version that has wheels or ship behind a guarded import that rejects HEIC with a clear message. **Tests:** HEIC fixture accepted and converted; orientation fixed; GPS stripped; a renamed non-HEIC `.heic` rejected; oversized pixel count rejected. Update `b2b-contracts.yml:24` installs. |
| 4.3 | P1 | **Purpose and captions** | Optional `purpose` (Site photo, Reference image, Existing fixture, Drawing markup, Logo, PO, Other) and `caption` on `ilL-Portal-Upload` / `ilL-Line-Document` (additive fields). Group by purpose in the line/project document panels. |
| 4.4 | P1 | **Server thumbnails** | After validation, generate a 480 px WebP thumbnail (Pillow is already a dependency) stored privately next to the original. Serve it through the existing private-file guard (`portal/private_file.py`). Lists show thumbnails, with a lightbox for the full image. Backfill for existing uploads runs as a background job and is optional. |
| 4.5 | P1 | **Project/line photo gallery** | On project and line detail pages, show a gallery tab: grid, lightbox with captions, download original, and "attach to drawing request". Read-only for viewers; edit for collaborators with mutation rights (`portal/access.py`). |
| 4.6 | P1 | **Dealer logo self-service** | `Customer.dealer_logo` exists (`patches/add_customer_dealer_logo.py`) and is used on System Designer title blocks (`system_design/designs.py:143`). Add upload/replace on `/portal/account` (company tab) with a live preview of how it appears on the title block and on exports/packets. |
| 4.7 | P1 | HEIC for staff uploads too | Staff attach images through native Desk File upload. Add a File `before_insert`/`validate` hook that converts HEIC to JPEG with the same helper as 4.2, limited to images attached to template `hero_image`/`image`, Webflow Product image fields and gallery rows, so hero images are always browser-viewable. |
| 4.8 | P2 | Duplicate detection | SHA-256 the content (the File doc already stores `content_hash`). Warn "This photo is already attached to Line 12" instead of storing it twice. |


**Phase 4 status** (branch `feat/phase-4-uploads`, stacked on Phase 2):

| # | Status | Commits | Notes / deviations |
|---|---|---|---|
| 4.1 | Done (manual phone/desktop run pending on staging) | `028b547` | `public/js/portal_uploader.js` progressively enhances the existing inputs instead of replacing them. `input.files` mirrors the accepted files and `PortalUploads.uploadAll(input, ...)` delegates to the widget, so every caller and the upload endpoint stay unchanged. The aggregate cap is 100 MiB. It is client-only; the server still enforces 20 MiB/10 files. Kill switch `ill_portal_upload_widget`, published to scripts as `#ill-portal-flags` from `portal_base.html`. jsdom tests in `tests/portal_ui/portal_uploader.test.cjs`. |
| 4.2 | Done | `7afa79c`, `028b547` | Server: `file_validation.normalize_upload()` (ftyp major-brand sniffing, lazy guarded `pillow_heif` import, 20 MiB raw / 40M pixel caps, `exif_transpose`, JPEG q90 with the ICC profile only). Only `portal.files.upload` calls it, behind kill switch `ill_portal_heic_uploads`. `validate_content` and the packet/offer/literature callers are unchanged and keep rejecting HEIC. Client: only JPEGs with an EXIF rotation and photos over 4096 px or 8 MiB are re-encoded, so ordinary photos keep full quality. Deviations: the original HEIC is not kept (the optional part), and orientation is fixed client-side only when re-encoding (the server-stored JPEG keeps its EXIF orientation as before). Wheel check (D2): pillow-heif 1.8.1 ships `cp314` manylinux_2_28 wheels for x86_64 and aarch64. Frappe Cloud images are Ubuntu 22.04 (glibc 2.35), so it is pinned `>=1.8.1,<2`. The CI Server job installs it on Python 3.14 with Pillow 13. |
| 4.3 | Done | `2927ab8`, `1a8cc43`, `e72f9a4` | Optional `purpose` (blank default rather than "Other", since it is optional) and `caption` (max 280 chars, control characters stripped) on both doctypes. `files.upload` and `line_documents.attach` accept them as optional params, and the new `line_documents.annotate` edits them under the schedule concurrency token. The line-documents dialog and the project Photos tab group by purpose. Kill switch `ill_portal_upload_purpose`. |
| 4.4 | Done | `2927ab8`, `1a8cc43`, `e72f9a4` | `portal/media.py` makes a 480 px WebP (q80, `exif_transpose`, pixel cap, no metadata) after the File is attached. It is a private File linked from the new read-only `ilL-Portal-Upload.thumbnail`, and `private_file.py` authorizes it through the original file's rule. Failures are logged and never block the upload. Backfill via the System Manager-only `media.enqueue_thumbnail_backfill`. Kill switch `ill_portal_thumbnails`. |
| 4.5 | Done | `2927ab8`, `1a8cc43`, `e72f9a4` | `media.gallery` (project or line scope; image line documents only) and `media.attach_to_request` (write on schedule and request, same project, open request, sha dedupe, 10-file cap; copies the bytes into a new private upload). Project page has a lazy-mounted Photos tab; edit/attach controls only where `can_edit`. Deviation: there is no separate line detail page, so the line-documents dialog serves as the line gallery (thumbnails + lightbox). Kill switch `ill_portal_gallery`. jsdom: `tests/portal_ui/portal_gallery.test.cjs`. |
| 4.6 | Done | `2927ab8`, `1a8cc43`, `e72f9a4` | `accounts.set_dealer_logo(file_id=None, remove=None)` takes the caller's own staged upload, re-encodes it to PNG within 1200x600 and publishes it as a **public** File (the System Designer and exports read it without a portal session; the original stays private). Previous logo Files are kept so issued drawings are unchanged. The `/portal/account` company card has upload/replace/remove with a title-block preview. Deviation: packets don't use `dealer_logo` today, so the preview covers the title block only. Kill switch `ill_portal_dealer_logo`. |
| 4.7 | Done | `2927ab8`, `1a8cc43`, `e72f9a4` | `PortalFile.before_insert` converts HEIC to JPEG with `file_validation.normalize_upload` **before** Frappe saves the bytes (a `doc_events` hook would run too late). It is limited by `attached_to_doctype`/`attached_to_field` to template `hero_image`/`image`, Webflow Product image fields and gallery rows. `ilL-Fixture-Template` has no `image` field, so only `hero_image` is covered there. Kill switch `ill_desk_heic_conversion`. |
| 4.8 | Done | (this commit) | New read-only `line_documents.find_duplicates(schedule_name, line_key=None, hashes=None)` (portal read access via `schedule_context`; at most 10 SHA-256 digests) reports active line documents with the same bytes and their line label. Before uploading, the line-documents dialog hashes the files with `crypto.subtle` and warns "already attached to Line {0}"; the dealer can still upload. `attach()` no longer stores a second document with the same sha256 on the **same** line unless it is the chosen primary, and returns a new `duplicates` key (old keys unchanged). HEIC files are not hashed on the client because the server converts them, so their bytes differ. Kill switch `ill_portal_upload_duplicate_check`. Tests: `tests/portal_unit/test_line_documents.py::DuplicateDetection`. |

---

## Phase 5 — Product and picture authoring for staff

Current state: adding a product touches about 4–8 forms (family template → spec rows/mappings → `ilL-Webflow-Product`
with 74 fields → media child rows → publication job). Images exist in several places with no rule for which one
wins: template `image` **and** `hero_image` (tape/neon, sheet, kit templates), `ilL-Webflow-Product.featured_image`,
`dimensions_image`, `series_family_image`, and gallery rows (`image` required; `alt_text`, `caption`, `display_order`
optional). Portal display falls back from the first gallery image to featured to template (`templates/pages/configure.py:330-451`).
Readiness (`api/product_readiness.py:228-389`) is strong on engineering but checks only `featured_image` for media.

| # | Pri | Item | Design |
|---|---|---|---|
| 5.1 | P0 | **Media readiness checks** | Extend `product_readiness.evaluate()` with *warnings* first (so nothing currently publishable is blocked): **source template has no `hero_image` (D1)**; hero image URL not public/approved; hero image under 1200 px wide or a non-web format (TIFF/BMP); gallery image missing `alt_text`; gallery image URL not public/approved (the same check documents already get); missing dimensions image for linear families. Ship a "templates without hero image" report first so staff can fill gaps. Then promote **missing hero image** to an error for new publications. |
| 5.2 | P0 | **Hero image + gallery manager on template and Webflow Product forms** | On **each of the six template forms**, the `hero_image` field gets a large preview card labelled "Main product image — shown to dealers and on Webflow", with drag-drop replace, a size/dimension badge, an alt-text field (new additive `hero_image_alt` Data field on each template) and a warning when empty. On the Webflow Product form, add a gallery manager (custom HTML field + `ill_webflow_product.js`): multi-file drag-drop into the gallery table, drag to reorder (writes `display_order` and `idx`), inline alt text, thumbnails and delete. The product form shows the inherited template hero image read-only with an "Edit on template" link, because `set_dynamic_hero_image` (`ill_webflow_product.py:306-333`) already copies it on save. Uses `frappe.ui.FileUploader` so File permissions stay native. |
| 5.3 | P1 | **Clone product / clone template** | "Duplicate as new product" button on `ilL-Webflow-Product` and each family template. Server method copies fields and child rows, clears Webflow IDs, sync/publication state, slugs and timestamps, asks for a new name/slug, optionally reuses media (link the same File) or skips it, and opens readiness. Build on `frappe.copy_doc` plus an explicit exclude list kept next to the authoring field register (`docs/B2B_AUTHORING_FIELD_REGISTER.md`). |
| 5.4 | **P0** | **One canonical image rule: template `hero_image` is the main image (D1)** | **Gap today:** Webflow Product already inherits the template `hero_image` (`ill_webflow_product.py:306-333`), but portal pages ignore it. `templates/pages/configure.py:330-448` uses gallery #1, then `featured_image`, then the template's legacy `image`. Dealers can therefore see a different picture from Webflow. **Fix:** one batch resolver `resolve_product_images(doctype, names)` in `product_projection.py` returning `{primary, primary_alt, gallery[]}` with precedence **template `hero_image` → Webflow `featured_image` → gallery #1 → template `image` (legacy)**. Gallery images become *additional* images, de-duplicated against the primary. Use it in `configure.py` (fixture/tape-neon/sheet/kit/driver pickers), product catalog/detail, product finder, Add Line picker (3.7), schedule line thumbnails and exports. **Backfill (optional, staff-reviewed):** a report of templates where `hero_image` is empty but `image` or a Webflow gallery image exists, with a one-click "Use this as hero image" action. No automatic overwrite. **Non-breaking:** template `image` and Webflow `featured_image` remain and keep working as fallbacks. Webflow publication payloads stay unchanged (`hero_image` is already exported in `webflow_export_v2.py:352`). |
| 5.5 | P1 | **New Product wizard (Desk page)** | Steps: family → start from blank or clone → identity and marketing copy → link/create source template (with existing preflight) → media (5.2 component) → documents/spec sheet → readiness (5.1) → save as draft or request publication. The wizard only orchestrates existing DocTypes and APIs (`catalog_builder.records`, `product_readiness.preview`, publication request); it adds no new data model. |
| 5.6 | P1 | **Readiness dashboard** | Desk page/report listing all products with traffic-light columns (Identity, Source, Specs, Images, Alt text, Docs, Spec sheet, Publication, Webflow sync), filters by family/brand, and click-through to the failing field. Extends the existing `design_readiness` / `submittal_readiness` page pattern. |
| 5.7 | P2 | **Bulk media manifest import** | Extend Catalog Builder Check → Import with an optional media manifest (`product_slug, role, file_url_or_zip_path, alt_text, display_order, is_primary`). Dry-run reports per row; the commit attaches files and fills the gallery. Keep the existing batch limits, locks and receipts (`catalog_builder.py:159-357`). |
| 5.8 | P2 | **Image processing on staff upload** | When an image is attached to a gallery/featured field: create WebP derivatives (e.g. 480/1200/2400), strip EXIF GPS, and record width/height. Runs as an `after_insert` enqueue on File for the relevant attached DocTypes. Publication payloads may then reference derivatives once the n8n workflow accepts them (contract change, behind a flag). |
| 5.9 | P2 | Schema tidy-up | Hide `tape_spec` (deprecated, `ill_webflow_product.json:204-220`) when empty. Collapse irrelevant source-link fields per product type through `depends_on`. Make sync/publication status fields read-only. |

---

## Phase 6 — Configurator consistency and performance

| # | Pri | Item | Detail |
|---|---|---|---|
| 6.1 | P1 | Cross-family contract tests | One parametrized test module that runs fixture, tape/neon, sheet, kit and driver through the same assertions: unit round-trip (mm canonical, display unit preserved), rounding (sum-then-round), price breakdown keys, error shape (2.4), receipt idempotency, reopen equality. This is the safety net for 6.2–6.4. |
| 6.2 | P1 | Single persisted-unit policy | Persist engineering lengths in mm with a separate display unit. Route `configuration_reopen.py:62-80` and the family engines through `configuration_contract.py:94-111` conversions. Read paths must keep accepting old snapshots. |
| 6.3 | P1 | Unify tape/neon pricing rounding with `pricing_utils.py` (repricing approved, D3) | `tape_neon_configurator.py:132-248` rounds individual adders. Switch to the shared sum-then-round rule. No legacy flag is needed. **Scope of repricing:** draft/unquoted schedule lines get the new price on their next recalculation or open. **Never** change issued Quotations, accepted offers, Sales Orders or frozen pricing snapshots (`ill_child_pricing_snapshot`, guardrail 5). Before release, run a read-only report over saved tape/neon lines listing old versus new totals so sales knows which open quotes will differ. Add tests for rounding equivalence with fixture pricing. |
| 6.4 | P1 | Server-validated LED sheet options | `led_sheet_steps.js:50-59,202-243` matches options in the browser against embedded data. Add a server cascading-options endpoint like the other families, and keep the client matcher only for instant feedback. |
| 6.5 | P1 | Option projection cache | Cache read-only option projections in `frappe.cache` keyed by `(template, catalog_revision)`, with invalidation on template/spec/mapping save (hooks) and on publication. Bulk-load specs in `tape_neon_configurator.py` / `extrusion_kit_configurator.py` loops (lines listed in the configurator audit). |
| 6.6 | P2 | Visual run/segment preview | SVG preview of segments, feed points, jumpers, profile/lens cut lengths and sheet tiling, generated from the computed build that already exists. Read-only, so there is no engineering risk. |
| 6.7 | P2 | Compare two configurations | Side-by-side part number, dimensions, run plan, driver plan, price and availability. Pure read of two snapshots. |
| 6.8 | P2 | Finish grouping-plan gates | Remaining items in `CONFIGURATOR_GROUPING_ALIGNMENT_PLAN.md:69,134-138,170-174,186-216` (leader cable BOM ownership, canonical identity). Keep group save behind its existing site flag until these are accepted. |

---

## Phase 7 — Desk and internal tooling

| # | Pri | Item | Detail |
|---|---|---|---|
| 7.1 | P1 | One route contract | Create `portal/routes.py` with a `PORTAL_ROUTES` dict and expose it to JS through `boot_session`/`extend_bootinfo`. Replace literals in `desk_portal_links.js:4-13`, `shared_configurator.js:377`, `ill_document_request.py:279,338`. Covered by test 0.5. |
| 7.2 | P1 | "Open in portal" / "Open in Desk" everywhere | Extend `desk_portal_links.js` (injected in `hooks.py:60-75`) to `ilL-Order-Change`, `ilL-Drawing-Review`, `ilL-Portal-Message`, `ilL-Account-Request`, `ilL-Portal-Invitation`. For Sales Orders without `ill_fixture_schedule`, show a disabled button with the reason instead of hiding it. Add an "Open in Desk" link on portal pages, visible to staff only, using the same contract. |
| 7.3 | P1 | Internal-note clarity | Notes are already separated (`conversations.py`). In the Desk composer, make the visibility toggle explicit: default **Internal**, a yellow banner while it is set to *Customer*, and "Send to dealer" as a separate button. Add a test that a dealer session never receives `Internal` rows from any portal serializer (orders, quotes, drawings, support, schedule). |
| 7.4 | P1 | Staff action center polish | `portal/action_center.py` + `queues.py` + the `ill_portal_operations` page: one inbox with assignee, due/SLA badge, age, dealer, and quick actions (assign to me, reply, mark waiting on dealer). Add a daily overdue digest via `staff_notifications.py`. |
| 7.5 | P1 | Split `desk_dialog.js` (1,348 lines) | Verbatim extraction into `desk/dialog/{state,family_steps,pricing,save}.js`, then move any pricing/validation decision that is not already server-checked into the server save path. |
| 7.6 | P2 | Simplify the schedule form script | `ill_project_fixture_schedule.js` (614 lines, worst health score). Extract `get_unconfigured_lines` handling, collaborator UI and conversion buttons into helpers. The server already validates (`.py:182-189`), so the client check stays only as an early warning. |
| 7.7 | P2 | Workspace refresh | Number cards for "Quotes awaiting staff", "Drawings awaiting review", "Orders needing acknowledgment", "Products not ready", "Failed publish jobs", each linking to a filtered list. Use the preserved-merge approach already in `portal_workspace.py`. |

---

## Phase 8 — Visual, accessibility and mobile polish (rolling)

1. **Design tokens and components.** Consolidate `_portal_brand.scss`, `_portal_commerce.scss`, `portal.css` and inline
   styles (e.g. `schedule.html:106-110,416`) into tokens (color, spacing, radius, type scale) and components (badge,
   card, table, empty state, toolbar, dialog, toast, uploader).
2. **Consistent page chrome.** Every page gets breadcrumbs, a title with a primary action, an empty state with a next
   action, and the same pagination/sort/filter bar (drawings already paginates on the server; quotes/orders/projects should match).
3. **Accessibility (WCAG 2.2 AA).** `aria-label` on icon buttons; one dialog component with a focus trap, Escape and focus
   return (replace manual modals such as `order_detail.html:326`); full tab semantics (`project.html:409-421`);
   `role="status"` toasts; contrast-check badge colors (`_portal_brand.scss:551-573`); replace `href="#"` controls
   with buttons (`schedule.html:160-173`, `account.html:30-39`). Add axe-core to the Playwright suite.
4. **Mobile and tablet.** Schedule table becomes a card list below 768 px; 44 px touch targets; sticky bulk-action bar;
   camera capture (`accept="image/*" capture="environment"`) in the uploader on phones.
5. **Notification center.** Unread badge in the portal nav using the existing event ledger.

---

## Phase 9 — Acceptance and rollout

1. Each phase ships behind flags to a **staging** site restored from a production backup, and goes through the upgrade rehearsal
   and the browser golden path (0.4).
2. Release to **all dealers** (D5) after staging passes. Because there is no pilot cohort, staging validation (golden
   path, upgrade rehearsal, accessibility and mobile checks) is mandatory for every phase. Watch the Error Log and support
   tickets for 48 hours after each release, and use the kill switch on any regression. Success metrics: median time to
   configure and add a line, support tickets per 100 lines, uploads that failed or were retried, and HEIC conversions that failed.
3. Still-open Cloud acceptance items from `B2B_PORTAL_IMPLEMENTATION_STATUS.md` ("What still needs to be done") stay
   release gates: fresh/upgrade migration, native downloads, permission matrix, notifications/SMTP, PDF renderer,
   and restore proof.
4. Rollback means turning off the flag. Schema is additive, so no down-migration is needed.

---

## 4. Recommended first sprint (about 2 weeks)

1. 0.1–0.3 CI/lint/test dependencies, and 0.6 deploy-audit leftovers.
2. 1.1 tape/neon run count, 1.2 QBO integration user, 1.4 guest rate-limit test.
3. 2.1 verbatim extraction of schedule JS, with 2.3/2.4 API and error layer scaffolding.
4. 5.4 hero-image resolver plus the missing-hero-image report, then 5.1 media readiness **warnings** and the 5.2 hero image card.
5. 4.1 shared uploader with 4.2 HEIC support, first on support tickets, then on all upload surfaces. Verify the `pillow-heif` wheel on Cloud first.

## 5. Decisions

All open decisions were resolved on 2026-11-03. See **Owner decisions** at the top (D1–D5).
Remaining follow-ups: restricting Webflow preview origins (1.3) is deferred until the owner revisits it.
