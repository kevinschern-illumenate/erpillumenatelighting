# Deployment and recent-change audit — October 22, 2026

The recent code contains reproducible application regressions, fixed in this
working tree. The reported Frappe Cloud **image build** failure has not been
reproduced or attributed to a specific command. These are separate conclusions.

## Scope and evidence

Audited main at `e2cdc35a2b43379977cfe2517d4efe97bac65198`, starting with
the newest commits and reviewing changes since
`bde7c7ec613c93343047f23d2bc03475f099c324` (before October 15). That range
contains 266 changed source/documentation files after excluding generated assets,
vendor assets and lockfiles. Static checks cover the whole tracked app; manual
review focused on packaging, migrations, hooks, publication, form transport,
schedule synchronization and recent power-allocation changes. This is not a
claim that every business workflow has been exercised against production data.

The local bench uses Python 3.14.7, Frappe 16.36.0, Node 24 and MariaDB 11.8.6.
The failed cloud build's exact app/framework revisions, Docker image and worker
environment are unavailable. No production deployment or data changes were made.

## Confirmed defects and fixes

| Defect | Evidence and impact | Local fix |
| --- | --- | --- |
| Webflow Product form cannot load | Commit `0af9d0f7d` (October 21) placed `frm.set_query(...)` directly inside the form-handler object. `node --check` fails at the original line 273 with `Unexpected token '.'`. The entire form script fails to parse. | Move query registration inside `refresh`. Add a test parsing every DocType script and exercise the query registration. |
| Schedule edits reject blank optional indices | Real Frappe argument validation rejects five parameters across delete, duplicate, move and update endpoints before the function body can resolve a valid stable line key. The installed-site transport suite reproduces the failure. | Accept form strings in the annotations; retain existing line lookup, validation, permission checks and stale-edit guards. The transport suite now passes. |
| Publication loses product documents | The October 20 `content_record` exclusions include `documents`, but publication used that hash filter to construct the actual outgoing payload. The n8n projection consequently receives no document list/spec-sheet link on this path. | Freeze the complete export; apply exclusions only to the approval-hash input. Regression coverage verifies documents survive, existing approval hashes remain identical, and the immutable payload hash detects a changed PDF URL. |
| Webhook delivery reports success on HTTP failure | The worker introduced in `236645e91` ignores HTTP 401/500 responses and swallows network exceptions. Its request timeout also equals the usual short-worker timeout. | Check HTTP status, log and re-raise request failures, and use a 120-second network timeout. Tests cover 401, 500, timeout and accepted responses without contacting n8n. |
| Publication dispatch races the database commit | Both v2 trigger endpoints enqueue a worker while the claim/new job remains uncommitted. A fast remote workflow can observe missing or old job state. | Use `enqueue_after_commit=True` in both endpoints. Regression coverage checks both dispatch paths. |
| Sync can freeze the form indefinitely | The two-minute timer starts only after the initial webhook responds. A hanging request never installs that timer; successful completion also leaves the old timer alive. | Start the deadline before fetch, abort the browser request on timeout, and clear polling/deadline on completion or failure. Tests cover a never-resolving request, HTTP failure and completion. |

The existing photometric migration fix remains intact: unit-bearing values such
as `6 ft` remain Data fields instead of being coerced into decimals.

## Remaining application findings

These need follow-up on the actual Webflow/n8n workflow, and are **not fixed** by
the narrowly scoped changes above:

1. **Wrong brand in the direct sync button.** The October 20 button always sends
   `brand: 'lighting_206'`, even when the product targets `illumenate` or multiple
   brands. The separate v2 trigger endpoints do iterate target brands. Confirm
   which workflow is deployed and make the button use the same brand selection
   and job contract before relying on it for other brands.
2. **Completion can reflect an earlier sync.** The button polls the product's
   top-level `sync_status` and accepts an already-existing `Synced` value. It has
   no current job identifier/revision check and does not poll per-brand status.
   The deadline fix prevents a frozen form but does not prove remote completion.
3. **Role mismatch in v2 trigger endpoints.** Each endpoint calls publication
   `request` (requires catalog capability) followed by `claim` (requires
   integration capability) under the same user. A Catalog Publisher alone cannot
   complete the path; System Manager or a user with both capabilities can.
   Preserve the approval/worker permission boundary when correcting orchestration;
   do not simply remove either check.

Existing immutable publication jobs retain their stored payloads. The document
fix applies to newly created jobs; it does not rewrite queued/running jobs or
reset approvals. Because requests are idempotent for a revision, requesting that
same revision again may return an existing job. Repairing an affected existing
job requires reviewing its state and remote result first.

## Validation

| Check | Result |
| --- | --- |
| All tracked app Python files | 764 parse successfully |
| All tracked non-vendor app JavaScript files | 134 pass `node --check` after the form fix; exactly one failed before it |
| Full `bench build` for Frappe, ERPNext and this app | Passed during investigation |
| `bench build --app illumenate_lighting` | Passed during investigation |
| Python wheel with normal isolated build dependencies | Passed |
| Binary dependency resolution for Python 3.14 (`pypdf`, `Pillow`, `jsonschema`) | Passed |
| Portal/service unit suite after fixes | 1,097 passed |
| Browser test files after fixes | 26 passed, including new Desk-script regressions |
| Installed-site CI modules | 82 tests across 15 modules, including three new regression tests; affected modules rerun successfully after fixes |
| Portal templates | 43 parsed; rendered pages/configurator modes and 58 embedded scripts checked |
| Existing photometric repair | 16 migration-asset tests passed, including real database DDL coverage |
| Patch formatting | `git diff --check` passed |

The initial system-design test run lacked `jsonschema` in the local bench.
Installing that already-declared dependency into an isolated test path made all
15 design tests pass. That setup issue is not evidence of a production defect.

Local diagnostic logs are under `/tmp/deploy-audit-*`. They are temporary and
are not required for the regression tests, which are in the repository.

## What the cloud message establishes

The user-visible message is only `image build failed`, and the output pane says
`No Output`. In the inspected public Frappe Press source:

- [`get_default_message`](https://github.com/frappe/press/blob/33448919dd614b6906257090d676f2cb1152c9d1/press/press/doctype/deploy_candidate/deploy_notifications.py)
  uses `Image build failed.` when it cannot identify a failed build step.
- [`JobStep.vue`](https://github.com/frappe/press/blob/33448919dd614b6906257090d676f2cb1152c9d1/dashboard/src/components/JobStep.vue)
  renders `No Output` when the step has no output text.

Those are fallback messages, not a package, syntax or migration diagnosis. The
public source version may differ from the hosted service. Successful local
builds do not rule out a cloud-specific dependency, checkout, image or worker
failure. The Desk syntax error also demonstrates why a successful asset build
does not establish that all application code works.

The next evidence needed is the failed build candidate's **builder/Agent Job
record**, including the first failing command/exit status and resolved revisions.
There is no authenticated Frappe Cloud connection in this workspace. A concise
support request, if the dashboard continues to show no output, is:

> The deployment for illumenatelighting.v.frappe.cloud failed during image
> building with “image build failed” and “No Output.” Please inspect the failed
> build candidate and builder/Agent Job record and provide the first failing
> command/exit status and resolved app/framework revisions. Local app packaging
> and the full Frappe asset build succeed; the dashboard exposes no diagnostic
> output.

This request has not been sent. The current evidence does not justify declaring
the cloud failure fixed or blaming the cloud infrastructure.

## Why regressions escaped

The default asset build omits separately loaded Desk form scripts. The new test
closes that gap and is picked up by the existing B2B browser-test workflow.
Local unit tests also do not substitute for Frappe's real request dispatcher:
the installed-site suite caught the blank-parameter regression.

The upgrade-rehearsal CI job currently runs on pull requests/manual dispatch,
not direct pushes to main. Recent direct commits therefore need explicit upgrade
validation as well as the fresh-install tests. GitHub's Vercel status is not
evidence that Frappe Cloud or the installed-site suites succeeded.
