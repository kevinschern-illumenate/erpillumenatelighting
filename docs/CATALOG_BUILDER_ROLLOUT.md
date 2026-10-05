# Catalog Builder release checklist

Session 5's **local checks are complete; live-site acceptance and production rollout are deferred**.
This record accompanies the [approved plan, §10](CATALOG_BUILDER_IN_ERPNEXT_PLAN.md#10-session-5--staging-rehearsal-production-rollout-vercel-decision).
A local bench with synthetic data does not establish readiness of the restored Cloud site.
The owner directed this session to use our own checks and leave the company's
staging environment untouched.

## Owner decisions — 2026-10-05

| Decision | Recorded value |
| --- | --- |
| Staging | `https://stagingillumenate.v.frappe.cloud` (owner reconfirmed) |
| Production | `https://illumenatelighting.v.frappe.cloud` |
| Intended Catalog Publisher on both sites | Kevin Yong Min Schern; exact User account and assignments not yet verified |
| Vercel | Keep offline drafting and add the production ERPNext builder link |
| Rehearsal scope | Isolated local checks only; do not use the company's staging environment |
| Local restore from an owner-provided backup | Discussed as an optional next check; no backup supplied or restored yet |
| Production window and fresh backup | Deferred with live-site acceptance and production approval |

An owner-provided database backup can support a separate local restore rehearsal
with real catalog data and customizations. Keep outbound jobs and email disabled
on that isolated restore. Public/private file archives are needed only to verify
attachments. This does not require access to the company's staging environment.

Sessions 1–4 remain draft PRs #280–#283. The Session 5 branch is stacked on Session
4. Session 4's fresh-install/upgrade CI, contract checks, and automated review
passed; repository-wide pre-commit lint still fails. Inspect each exact candidate's CI/review results before promotion and
explicitly resolve or document inherited failures. No branch merge, Cloud deploy,
production role change, or production import has been performed for this rehearsal.

## Local evidence — 2026-10-05

Frappe/ERPNext v16, isolated `test_site`, ordinary users holding only Catalog
Publisher plus framework defaults. Catalogs were derived from the illustrative
examples with unique `ZZTEST-` names, valid seeded external links, active specs,
profile finish variant codes, physical Nos/Meter stock units, and Sheet accessory
prices. These are synthetic engineering values, not approved product masters.

All seven passed Check and Import through the real browser UI. Every created
record was readable through the resource API and its linked Desk route. The
imported catalogs then passed their real configurator validation/resolution APIs
without creating configured builds. The following timings include local browser
HTTP and UI overhead; they are not Cloud performance measurements.

| Family | Created records | Check ms | Import ms | Desk links / configurator |
| --- | ---: | ---: | ---: | --- |
| Linear fixture | 24 | 451 | 275 | Passed |
| LED tape | 9 | 214 | 212 | Passed |
| LED neon | 9 | 176 | 205 | Passed |
| LED sheet | 10 | 199 | 216 | Passed |
| Extrusion kit | 19 | 176 | 217 | Passed |
| Driver | 5 | 161 | 164 | Passed |
| Controller | 5 | 156 | 165 | Passed |

Live-reference responses during those browser runs were 25–48 kB; initial page
plus reference loading was 313–984 ms. Session 2 separately measured 2,331
synthetic Items at 0.088 s / 511,327 bytes. Measure real restored staging data
against the <3 s / <2 MB target; these figures do not replace that measurement.

Local security checks: authenticated Dealer and ordinary Sales User received 403
on the builder page and all five APIs. Guest APIs returned 403; the Guest page
redirects to login, as implemented in Session 1 (the plan's blanket page-403
statement does not describe that intentional redirect). Missing CSRF was rejected;
`record(User)` and `record(Sales Order)` were refused; Catalog Publisher could not
create or modify audit receipts via the resource API. Logging out the shared
session produced the login/reload recovery message while retaining the draft.
The public ERP bundle contains no quoted `"exported_on"` snapshot key; its build
also rejects importing the reference snapshot.

The 48-record synthetic fixture rehearsal measured **552 ms Check / 183 ms Import**
inside the service. No timeout or background-job change was indicated locally;
the largest real staging family still needs its own measurement.

The installed-site regression suite covers final-batch failure after earlier
insert attempts, the 501-record refusal, seven family imports/resolution, and a
48-record fixture catalog. The preceding transaction suite covers Check rollback,
replay rejection, a changed/31-minute-old/other-user Check, row permissions, and
site-lock contention from a second database connection for Check and Import.
The expiry proof ages the stored receipt; it does not wait 31 wall-clock minutes.
Browser fixtures, their 81 imported records, seed data, nine temporary users, and
receipts were explicitly removed. Test fixtures remove only their owned records;
pre-existing canonical UOMs and Price Lists are reused without modification.

Reproduce only on an isolated test site with `allow_tests` enabled:

```sh
bench --site test_site run-tests --app illumenate_lighting --module illumenate_lighting.illumenate_lighting.api.test_catalog_import
bench --site test_site run-tests --app illumenate_lighting --module illumenate_lighting.illumenate_lighting.api.test_catalog_rehearsal
npm ci --prefix tools/yaml_builder_ui
npm test --prefix tools/yaml_builder_ui
npm run test:render --prefix tools/yaml_builder_ui
npm run build:erp --prefix tools/yaml_builder_ui
npm ci --prefix tests/portal_e2e
npm run test:browser --prefix tools/yaml_builder_ui
```

For the browser suite, install Playwright Chromium or set `BROWSER_EXECUTABLE` to
an existing Chromium executable. It uses controlled API responses and no site
credentials. Fresh-install and upgrade CI both run the installed-site rehearsals.

## Staging acceptance — deferred, not authorized for this session

The following is the plan's future release checklist, not work to perform under
the current local-only scope. Obtain a new direction before using staging.

1. Record the production backup used to restore staging, its timestamp, matching
   app/framework versions, and successful restore. Preserve private workspace
   backups as described in the [recovery plan](DEPLOYMENT_RECOVERY_PLAN_2026_09_29.md).
   Confirm outbound integrations/email and schedulers are appropriate for rehearsal.
2. Promote the reviewed Sessions 1–5 candidate to `staging` through a PR. Record
   the exact commit and deploy it with **Migrate**; Sessions 1 and 3 require schema,
   permission, hook, and workspace changes. Avoid unrelated framework upgrades.
3. Retain the update log: `catalog_builder_permissions` applied, after-migrate
   hooks succeeded, and no new **ilL workspace preservation** Error Logs. Verify
   the builder page, live reference, **Catalog Builder**, and **Catalog Imports**
   workspace shortcuts. Record reference load time and response bytes.
4. Identify Kevin's exact User account. Verify the Publisher role on a non-admin
   System User, including the [operator permission matrix](B2B_STAFF_OPERATIONS.md#catalog-builder-operations).
   Repeat the denial and audit-write tests with staging's actual role rules.
5. Author one real `ZZTEST-` catalog per family from live anchors in plan §10.4.
   Do not import unreviewed example values. Save each YAML and receipt privately.
   Check → Import → inspect every created record → verify the actual Portal/Desk
   configurator and relevant variant/length/component/price selections.
6. Repeat failure, two-browser contention, expired Check, session expiry, and
   501-record proofs on staging. For a last-batch failure, introduce the failure
   after a passing Check in an isolated rehearsal; a pre-validation missing-link
   rejection alone does not prove rollback of earlier insert attempts.
7. Time the largest realistic 30–60-record family. Investigate >60 s; queue work
   is a follow-up only if the actual request duration warrants it.
8. Delete only created rehearsal records in reverse result-batch order with an
   administrator, or retain and list their exact names in the evidence. Do not
   delete by a broad prefix. Keep receipts as evidence according to site policy.

| Family | YAML / Check receipt / Import receipt | Configurator evidence | Cleanup |
| --- | --- | --- | --- |
| Linear fixture | Pending | Portal fixture + Desk Configure & Add Fixture | Pending |
| LED tape | Pending | `/portal/configure-tape` | Pending |
| LED neon | Pending | `/portal/configure-neon` | Pending |
| LED sheet | Pending | `/portal/configure-sheet` | Pending |
| Extrusion kit | Pending | Fixture schedule kit line | Pending |
| Driver | Pending | Driver selection flow | Pending |
| Controller | Pending | Controller selection flow | Pending |

## Production approval and execution — not ready

After staging passes, prepare the `staging` → `main` PR with its exact tested
commit, evidence above, migration diff, successful backup identifiers, maintenance
window, Kevin's verified User ID, and the previous app commit. Present that concrete
release for the owner approvals required by plan §10.1 and §10.11.

Deploy that tested commit using **Migrate**. Verify migration/permission/workspace
logs and the builder/live reference; run one extrusion-kit **Check only** on
production. Confirm the agreed Publisher assignment and observe Error Logs for
one hour, recording new failures and their disposition. Publication stays separate.

Rollback restores the matched pre-update database, files, and config backup with
the previous app commit. Never run old application code against the migrated
database. Record the actual deploy, smoke result, role assignment, and observation
window here before marking Session 5 complete.
