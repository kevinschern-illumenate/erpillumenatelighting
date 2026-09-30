# Frappe Cloud deployment recovery and stabilization plan — September 29, 2026

This plan covers the Frappe Cloud deployments of `illumenate_lighting` to
`illumenatelighting.v.frappe.cloud` and the regressions introduced since the last
clean state. It is written as a hand-off: an implementing agent can execute
Phases 2–4 in this repository. Items marked **OWNER** need Frappe Cloud dashboard
access or a business decision and cannot be done from the repository.

Assessed revision: `main` at `a88f5e4` (September 28, 2026).
Last clean merge before the September work: `12c76df` (PR #255, August 24, 2026).

---

## Current status (September 29, from dashboard evidence) — read this first

This section supersedes anything below that says deployments are failing.

- **The deploy pipeline is working.** Bench group *ilLumenate Production - V16* deployed `a88f5e4`
  (latest `main`) successfully, Sep 28 5:00–5:07 PM. App commits: frappe `012667b`, erpnext `fb78e58`,
  hrms `c0a04b8`, crm `a6dfe8b`, print_designer `7beaad2`. The site is **Active** on that bench.
- **The site's update history is clean after two morning failures.** Site → Updates shows:
  - Migrate at 7:20 AM and 8:01 AM: *Recovered* (the Number Card and `Workspace.type` failures, now fixed);
  - Migrate at 10:05 AM and **10:47 AM: Success** (10:47 was `786a521`, which added the
    `b2b_commercial_schema` patch);
  - then **Pull** updates, all Success, at 11:53 AM, 1:18, 1:49, 4:11, 4:35, 4:54 and 5:06 PM.
- **Pull was the correct choice.** Frappe Cloud migrates only when the diff touches `*/patches.txt`,
  `*/hooks.py`, `*/fixtures/`, `*/*/custom/` or a DocType/Workspace/Report JSON (`press`
  `app_release_difference.is_migrate_needed`). No such file changed in `786a521..a88f5e4`, so the
  database schema matches the running code.
- **The v15→v16 upgrade is already done.** Summary item 2 below describes the earlier retries, not the
  current state.
- **The red job is automatic and non-blocking.** It is *Update Bench Configuration* at 5:33 PM
  (§3.0), not a failed deploy or site update.
- ✅ **Backups restored (Sep 29).** The last successful migration (10:47 AM, `786a521`) had written
  workspace snapshots to `private/backups/ill-workspace/`. Frappe's backup cleanup tries to `os.remove()`
  every non-file entry in `private/backups` regardless of age, so backups failed with
  `IsADirectoryError` from then on (§3.3). The OWNER ran dashboard **Actions → Migrate** on `a88f5e4`
  (its `before_migrate` relocates the directory), then a manual backup, and **both succeeded**. Phase 1
  §5.1 is complete. §5.2 remains only for the non-blocking bench job (§3.0).
- ✅ **Phase 2 implemented (Sep 29)** on branch `claude/frappe-deploy-assessment-wn7rcq`, commit
  `db06599`, verified on a local bench at production's exact Frappe/ERPNext commits:
  - 6.1 File hook: `portal/private_file.py`. 6.2 Sales Order gate: `portal/order_review.py`
    (`_portal_governed`). 6.3 Hooks: `portal_workspace.py`, `private_storage.py`.
    6.4 `api/permission_debug.py` deleted. 6.5 `portal/site_flags.py`. 6.6 `.github/workflows/ci.yml`,
    `.github/scripts/upgrade_rehearsal.py`, `tools/check_portal_templates.py`.
  - New installed-site module `api/test_deploy_regressions.py`. It **fails on the old code**: attachment
    uploads raise `PermissionError` even for a System Manager. It passes with the fixes.
  - Fresh install plus two migrations pass. So do the existing `test_migration_assets` (10) and
    `test_configurator_transport` (7) modules, 245 portal unit tests (Python 3.11 and 3.14), and every
    B2B contracts step.
  - The upgrade rehearsal passed. It installed `a88f5e4`, seeded production's
    `private/backups/ill-workspace` (reproducing "Backup failed … may be corrupted"), migrated twice to
    `db06599`, then confirmed the folder was relocated, the workspace customization kept and a backup
    succeeded.
  - No file in this change triggers a Cloud *Migrate*, so it deploys as a **Pull**. The 6.3 hook changes
    take effect at the next migration.
  - Owner decision defaults applied: portal-intake-only approval gate, invalid rollout config treated
    as absent, v15 CI removed.
- ✅ **Phase 3 and Phase 4 code implemented (Sep 30)** on branch `claude/confident-ptolemy-dq65eg`. Every
  Phase 2 fix was re-checked on `main` at `4131713` (PRs #260–#270 did not touch them) and still holds.
  - 7.3 `ill_project._get_user_customer`: user-linked Contacts decide, email-only matches are a fallback.
    It resolves every case the previous code resolved, with the same answer.
  - 7.1 `portal/role_audit.py` (`report`, `dealers`; bench execute only) and a role assignment checklist in
    `docs/B2B_STAFF_OPERATIONS.md`. `dealers()` also lists the Dealer users 7.2 would move off Desk.
  - 7.4 and 7.5: the three Webflow list parameters accept `frappe.call`'s JSON strings. Parameters whose
    body already normalizes blanks now accept them too. Verified against production Frappe's own
    `typing_validations.py` with pydantic 2.12. The installed-site transport test now covers non-`None`
    defaults and JSON-encoded lists and dicts. It lists the 28 remaining strict parameters in
    `KNOWN_STRICT`; no portal or Desk caller sends those blank.
  - 7.6 `commercial_lineage.validate` skips rows where neither side carries configured lineage. Lineage
    typed onto a plain row is still replaced from its source.
  - 7.7 and 7.8 are in their own commit because they edit `hooks.py`: the deploy that carries it runs a
    **Migrate**, not a Pull. The Custom Field fixture is filtered to this app's module, and
    `/portal/configure-kit` redirects to `/portal/configure`.
  - 8.1: `output/` and `tools/configurator_ui/dist-preview/` (built by Vercel) are no longer tracked, and
    `diff_bbb8605.txt` is deleted. 8.4: the backup repair and acceptance docs point here, with the
    `bypass_unlink.so` note corrected.
  - §6.1 acceptance: `test_deploy_regressions` now performs the real System Manager featured-image upload
    to an `ilL-Webflow-Product`.
- 🔴 **Remaining (OWNER):**
  - Run `role_audit.report` and assign roles (7.1).
  - Decide on Dealer Desk access using `role_audit.dealers` (7.2).
  - Untrack `.repowise/`, `.mcp.json` and `.codex/` **from your own checkout**. Run
    `git rm -r --cached .repowise .mcp.json .codex`, add them to `.gitignore`, then commit. Doing this from
    another clone would delete your working copies on the next pull (8.1).
  - Branch protection and deploy discipline (8.2, 8.3).
  - Confirm the stopped Postmark campaign scheduler (§4.1).
  - Run the staging rehearsal (Phase 5).

---

## 0. Rules for the implementing agent

1. Work on a feature branch and open one PR per phase (2, 3, 4). Never push to `main` directly.
2. Do not touch the Cloud site from code. Do not reset Patch Log, delete workspace snapshots,
   enable `developer_mode`, or set `ill_portal_acceptance` on production.
3. Production runs **Frappe 16.35.0** (`012667b9c4e7f66d5e1ff5858d2e922331d4300a`), ERPNext 16.36.1,
   HRMS 16.20.0, CRM 1.85.1, Print Designer 1.6.7 and Python 3.14. Verify framework behavior against
   that Frappe commit, not against v15 or `develop`.
4. Before each PR: `ruff check` on changed files; `python -B -m unittest discover -s tests/portal_unit`;
   and both GitHub workflows green (Phase 2.6 makes this possible).
5. Keep fixes minimal and behavior-preserving except where a section says to change behavior.
6. Order matters: finish Phase 2 before the next production deploy. Phase 3 can follow in a second deploy.

---

## 1. Executive summary

1. **The failing "Update Site Configuration" step does not run any app code.** In Frappe Cloud's agent,
   that job only reads and rewrites `sites/<site>/site_config.json` (details in §3). When it fails, the
   usual cause is the state the site was left in by earlier failed updates: site directory not on the
   bench Frappe Cloud expects, an unparsable `site_config.json` on that bench, a stale lock, or a full disk.
   Only Frappe Cloud support (or bench SSH) can fix that. **Get the job's output first (Phase 0).**
   *Update (Sep 29):* the failing job on screen turned out to be the **bench-level** *Update Bench
   Configuration*. It is also automatic and runs no app code, and its traceback is visible only to
   support (§3.0).
2. **The earlier failed attempts were two upgrades at once.** The site moved from Frappe/ERPNext **v15 to
   v16** and took about **87,000 lines of new app code** (1,672 files changed since `12c76df`) in the same
   migration. When a migration fails, Cloud restores the touched database tables. Files under `private/`
   are *not* restored, so each retry started from a slightly different state. *Update (Sep 29):* the
   upgrade has since succeeded (Current status above).
3. **The fresh-site install is healthy.** On the latest `main`, the GitHub CI v16 job installs the app on a
   fresh v16 site and runs `bench migrate` twice successfully. Locally, all 231 portal unit tests pass on
   Python 3.14. Every Python file compiles, every JSON file parses, and all 110 dotted paths in `hooks.py`
   resolve. So the remaining deployment risk is in **site state and upgrade-only code paths**. On a fresh
   install Frappe marks all patches as done without running them, so CI has never executed the 11 new
   patches.
4. **Critical v16 regression: File permissions.** In the deployed Frappe v16 build, a `has_permission` hook
   returning `None` means **deny**; v15 treated `None` as "no opinion". The app's File hook returns `None` for
   create/write/delete and for any file not attached to a portal DocType. Result: **every non-Administrator
   user, System Managers included, is denied creating, editing or deleting attachments**, and is denied
   doc-level read of most private files. This is the File-upload problem the last two commits
   (PRs #257/#258) were trying to diagnose.
5. **Critical workflow regression: Sales Order submit.** Any Sales Order with `ill_fixture_schedule` set now
   has to pass the full dealer-portal approval workflow. The normal ERPNext path *Quotation → Create →
   Sales Order* copies that field, but creates no portal intake. Those orders now **cannot be submitted at
   all**: "This order has no portal intake…". Only System Manager or the new `ilL Order Approver` role may
   approve even portal orders.
6. **CI has been red on every recent commit**, for fixable harness reasons (§2.6), so real regressions were
   hidden in the noise.
7. **Correction to existing docs:** `bypass_unlink.so` in `private/backups` is **Frappe Cloud's own**
   streaming-backup shim (an `LD_PRELOAD` helper compiled by the agent and normally deleted afterwards).
   It is not a security concern. See §3.4.

---

## 2. What changed, and what has already been fixed

### 2.1 Timeline

| When | Commits | What landed |
| --- | --- | --- |
| Aug 24 | `12c76df` (PR #255) | Last reviewed merge. Schedule → Sales Order conversion fixes. |
| Sep 10–25 | `015a020` … `bc295d6` ("big fable changes", "new features", "SHEETS AND FIXES", "BIG FIX") | B2B dealer portal: 22 new DocTypes, 11 new patches, File and Email Queue class overrides, new `has_permission`/query hooks, Sales Order/Quotation/Work Order/Delivery Note/Sales Invoice/Issue doc events, 5-minute scheduler jobs, workspace `before/after_migrate` hooks, desk/web asset bundles, configurator rewrite. |
| Sep 28 | `c9b9ffd` … `24bd0bb` (mostly "asdf"), PRs #256–#258 | Cloud repair rounds, documented in `docs/*_2026_09_28.md`, plus a temporary File permission diagnostic endpoint. |

Nearly all September work was pushed straight to `main` without review, and CI was red throughout.

### 2.2 Repairs already in `main` (keep them)

| Repair | Where | Status |
| --- | --- | --- |
| Number Card fixtures moved to the app-level `fixtures/` dir | `illumenate_lighting/fixtures/number_card.json` | Done. Verified by CI migrate. |
| Controller class names for 3 orphaned DocTypes | `ilLChildGroupMember`, `ilLChildGroupAllocation`, `ilLConfiguratorSession` | Done. |
| `Workspace.type` mandatory on v16 | `portal_workspace.merge_workspace` | Done. |
| `naming_rule` `random` → `Random` (2 DocTypes), report column type, QBO Link defaults | DocType JSON | Done. |
| Workspace snapshot/evidence dirs moved out of `private/backups` | `private_storage.py` (commit `b219f5c`) | Done in code. **Cloud still has the old dir** if any build from `bc295d6` through `140db15` ever migrated there (§3.3). |
| Missing commercial custom fields on existing sites | patch `b2b_commercial_schema` | Done. Runs only on the next successful migrate. |
| Stock scope returns "unknown" instead of throwing | `pricing_utils.py` | Done. |
| Blank numeric override parameters on configurator APIs | linear/tape/neon/webflow APIs | Done for 6 parameters (see §4.5 for the rest). |

### 2.3 Verified in this assessment

- ✅ CI "Server (version-16)" on `a88f5e4`: fresh install, `bench build`, two migrations, and the
  `test_migration_assets` and `test_configurator_transport` modules all pass.
- ✅ 231 portal unit tests pass on Python 3.14 (`tests/portal_unit`).
- ✅ All 110 dotted paths in `hooks.py` resolve; all `doctype_js` files exist.
- ✅ DocType schema changes since `12c76df` are additive only: no field type changes, no new unique or
  required fields on existing DocTypes, no removed fields.
- ✅ Frappe v16 pins `Pillow~=12.3.0` and `pypdf==6.15.0`, which satisfy the app's `>=` requirements.
- ❌ CI "Server (version-15)" fails in test bootstrap, not app code:
  `LinkValidationError: Could not find Warehouse Type: Transit`.
- ❌ "B2B local contracts" fails with `FileNotFoundError: .tools/portal-template-…`, because
  `tools/check_portal_templates.py:281` writes into a `.tools/` dir that doesn't exist on a clean checkout.

---

## 3. The "Update Site Configuration" failure

### 3.0 Update (September 29): the job on screen was *Update Bench Configuration*

The owner's dashboard showed a **bench-level** job, not the site-level job described in §3.1–3.2:
- Bench group *ilLumenate Production - V16* (status Active) → Jobs → **Update Bench Configuration**, *Failure*.
- Created Sep 28, 2026 5:33 PM by `Administrator`, duration 0 s.
- Steps: *Update Bench Configuration* ✅ and *Bench Setup NGINX* ✅ (no output); *Generate Docker Compose
  File*, *Update Bench Memory Limits* and *Deploy Bench* not run.

What this means:
- **Frappe Cloud starts this job itself.** In press, `Bench.on_update` calls `Agent.update_bench_config()`
  whenever a bench's `config` or `bench_config` changes. That includes worker and memory rebalancing
  (`Bench.allocate_workers`, run from the server's auto-scaling) when benches are deployed or sites move,
  and edits in the bench group's Config or Env tabs. `Administrator` as creator means it was automatic;
  it ran about 30 minutes after `a88f5e4` was merged, consistent with post-deploy rebalancing.
- **No app code runs in it.** The agent's `Bench.update_config_job` rewrites `common_site_config.json`
  and the bench config, regenerates nginx, then regenerates `docker-compose.yml` (or updates supervisor and
  runtime limits) and restarts the bench. Nothing in this repository can make it fail or fix it.
- **"No Output" everywhere is expected for this failure shape.** Both recorded steps succeeded. The
  exception happened in the agent's job body *between* steps, and the agent stores that traceback on the
  **job record** (`job_record.failure({"traceback": …})`), which the customer dashboard does not display.
  Only Frappe Cloud support can read it.
- **Impact:** the new bench config (workers, memory limits, env) was written but the containers were not
  recomposed or restarted with it. The bench itself is Active. This job alone does not run or fail a
  site migration.

Next evidence needed (OWNER):
1. The bench group's **Deploys** tab: status of the latest deploy and its `illumenate_lighting` commit.
2. **Sites → the site → Jobs/Updates**: status of the latest *Update Site Migrate* and any
   *Recover Failed Site Migrate*, with the output of any red step.
3. Dashboard **Notifications** (26 unread at the time): failed-update notices usually carry the error.

Ask support for the job-level traceback of this job, and to re-apply the bench config (§5.2 item 0).

### 3.1 What that step is

In Frappe Cloud's agent (`frappe/agent`, `agent/site.py`), the job `Update Site Configuration` runs a
single step:

```python
@step("Update Site Configuration")
def update_config(self, value, remove=None):
    new_config = self.get_config(for_update=True)   # filelock + json.load(site_config.json)
    new_config.update(value)
    ...
    self.set_config(new_config)                     # write temp file, rename, copy
```

The HTTP route (`POST /benches/<bench>/sites/<site>/config`) first resolves the site through
`Bench.valid_sites`. That call parses **every** site's `site_config.json` on the bench, and raises
`SiteNotExistsException` if the site directory isn't on the bench Frappe Cloud has on record.

Frappe Cloud (`press`) queues this job when:
- a Site Config key is added or changed in the dashboard;
- **Activate** is used on a Broken or Inactive site. This sets `maintenance_mode: 0`, which is what
  happens after a failed update leaves the site Broken;
- a site is deactivated or suspended (`maintenance_mode: 1`), or its host name is changed.

No `bench` command and no app code runs in this job. An app bug cannot make it fail. A site left in a
bad physical state by the earlier failed updates can.

### 3.2 Failure signatures and what to do

| Output in the failed job | Meaning | Who fixes it |
| --- | --- | --- |
| `SiteNotExistsException`, "does not exist on bench", `Path … is not a directory`, `site_config.json does not exist` | After a failed **Update Site Migrate** the site directory was moved to the new bench, and **Recover Failed Site Migrate** did not move it back (or the reverse). Cloud's record and disk disagree. | **Frappe Cloud support**: reconcile the site's bench record with its physical location. |
| `Error parsing JSON in <dir>`, `JSONDecodeError`, `InvalidSiteConfigException` | A `site_config.json` on that bench is invalid, possibly **another** site's (the agent validates all of them). | Support, or bench SSH: restore from `site_config.json.bak`. |
| Lock timeout on `site_config.json.lock` | A crashed job left a lock. | Support. |
| `No space left on device` / `OSError: [Errno 28]` | Disk full. | Clear old backups, raise plan storage, or support. |
| Dashboard error before any job (e.g. "blacklisted", "developer mode", invalid value) | Bad key or type typed into Site Config. | OWNER: fix the value (§5.3). |

**Most likely here:** earlier updates failed at **Backup Site** (`IsADirectoryError`, §3.3) and at
**Migrate** (after_migrate errors). A recovery that did not finish leaves the site *Broken*, and
reactivating it triggers exactly this job. Don't keep clicking Update or Activate; each attempt can leave
more partial state. Collect the output (Phase 0) and hand it to support with the §5.2 request.

### 3.3 The `private/backups/ill-workspace` trap

- Commits `bc295d6` (Sep 25) through `140db15` wrote workspace snapshots to
  `sites/<site>/private/backups/ill-workspace/`. The fix to `private/ill-workspace/` arrived in `b219f5c`
  (Sep 28, 16:23).
- On deployed Frappe v16, every `bench backup` (`new_backup`) first calls
  `delete_temp_backups(older_than=23)`, which runs `os.remove()` on each entry of `private/backups`
  for which `is_file_old()` is true. For anything that isn't a regular file, `is_file_old()` takes its
  "does not exist" branch and **returns True regardless of age**. So `os.remove(<directory>)` raises
  `IsADirectoryError` on **every** backup, from the moment the directory exists.
  - Affected: scheduled backups, manual *Schedule Backup*, and offsite backups (agent job *Backup Site*).
  - Not affected: the pre-update backup of a *Migrate* update, which dumps tables directly with
    `mysqldump` (step *Backup Site Tables*).
  - The last successful migration (10:47 AM Sep 28, `786a521`) still used the old path, so backups are
    failing now.
- The corrected code (`b219f5c`, deployed) relocates the directory in `before_migrate`, which runs in
  any `bench migrate`. Two ways to trigger it:
  - the dashboard **Actions → Migrate** (§5.1). The schema is already current, so this migration has
    nothing else pending;
  - support moves the directory by hand (§5.2).
- Keep the whole directory, including `pending.json` and every snapshot. It may hold the only copy of
  workspace customizations from an interrupted migration.

### 3.4 `bypass_unlink.so`

This file is Frappe Cloud's own. The agent's streaming backup (`Site.backup(streaming=True)`) compiles
`lib/bypass_unlink.c` into `private/backups/bypass_unlink.so` and `LD_PRELOAD`s it. The shim makes
`unlink()` a no-op for paths containing `%stream%`. The agent deletes it in a `finally:` block, so a
leftover copy means a streaming backup was interrupted. Support can remove it; it is not a compromise
indicator. **Implementing agent:** correct the paragraph about it in
`docs/FRAPPE_CLOUD_BACKUP_REPAIR_2026_09_28.md`.

---

## 4. Phase 0 — Collect facts (OWNER, about 30 minutes, before anything else)

Record the answers in the Phase 1 support ticket and give them to the implementing agent.

1. **The failed job's output.** Dashboard → Site → *Jobs* (or *Updates* → the failed update → expand the
   failed step). Copy the full output of the step marked failed, plus the job name (e.g. "Update Site
   Configuration", "Update Site Migrate", "Recover Failed Site Migrate").
2. **Site status and location.** Dashboard → Site → Overview: status (Active/Broken/Recovering/Inactive),
   the bench group, and the bench (release) it's on. Bench group → *Deploys*: the currently deployed
   `illumenate_lighting` commit hash and the Frappe/ERPNext versions of that bench.
3. **Which framework version the site runs now.** Log in as a System Manager → Help → About. Or visit
   `/api/method/frappe.utils.change_log.get_versions`. If it says v15, every retry is still a v15→v16
   upgrade.
4. **Site Config keys.** Dashboard → Site → *Site Config*. List every key starting with `ill_`, plus
   `maintenance_mode`, `pause_scheduler`, `keep_backups_for_hours`. Note each key's type (String, Boolean,
   JSON, Number).
5. **Backups.** Dashboard → Site → *Backups*: when did the last successful backup finish? Try
   *Schedule Backup* once. If it fails with `IsADirectoryError`, §3.3 applies.
6. **Disk usage.** Dashboard → Site → Overview → storage and database usage versus plan limits.
7. **Other app updates bundled into the pending deploy** (ERPNext/HRMS/CRM/Print Designer commit changes).
   Note them. Don't bundle framework bumps with app deploys (Phase 5).

### 4.1 Findings so far (September 29)

**Site Config (item 4) — collected.** The dashboard shows: `installed_apps`, `encryption_key` (masked),
`user_type_doctype_limit` (`{}`), `allow_cors` (Webflow staging and `illumenate.lighting`), and
`n8n_campaign_webhook_url`.
- **It is complete for production.** The dashboard lists only keys added through Frappe Cloud. Database
  credentials and other server-generated keys live only in the server-side `site_config.json` and are
  never shown; the site could not load without them.
- The app needs **no** `ill_*` keys to behave as before. Every one is optional and its absence is the
  intended production default (see the table below).
- None of the risky values from §5.3 are present: no `ill_portal_pilot_users`,
  `ill_portal_enabled_families`, `ill_portal_acceptance`, `maintenance_mode` or `developer_mode`. So §6.5
  is hardening, not an active outage.
- These dashboard values cannot explain the *Update Site Configuration* failure, which points again to
  server-side state (§3.2). The dashboard does not show the on-disk file, so a corrupted server-side
  `site_config.json` is still possible.
- **Installed-app order is `frappe, illumenate_lighting, erpnext, hrms, crm, print_designer`.** Frappe
  reads the real order from the database (`db.get_global("installed_apps")`); this key most likely mirrors
  it. If so, this app's patches and `after_migrate` hook run **before** ERPNext's, HRMS's and CRM's in every
  migration, including before ERPNext's own v16 data patches during the v15→v16 upgrade. Don't try to
  reorder apps on production. The CI upgrade-rehearsal job (§6.6) must reproduce this order: install
  ERPNext first, then set the `installed_apps` global to this order before migrating.
- `n8n_campaign_webhook_url` is **unused**. Its only reader, `email_campaign_scheduler.run_scheduled_campaigns`,
  lost its scheduler entry in commit `1e99926` (August 12), and nothing else calls it. Scheduled Postmark
  campaigns have not fired since then. OWNER: confirm that's intended; if so, the key and module can be
  removed (Phase 3).
- `allow_cors` only affects Frappe's built-in CORS. The app sets CORS itself for the longer
  `ALLOWED_ORIGINS` list in `illumenate_lighting/illumenate_lighting/utils.py:17-25`, so no change is
  needed.
- A staging site, `stagingillumenatelighting.v.frappe.cloud`, is already referenced in
  `ALLOWED_ORIGINS`. OWNER: if it is on its own bench group, reuse it for §5.4 and Phase 5.

Optional app keys (leave absent on production unless the row says otherwise):

| Key | Absent means | Set only when |
| --- | --- | --- |
| `ill_portal_stock_company` | Stock uses the company named exactly "ilLumenate Lighting" and its enabled, non-group warehouse named "ilL-Stores". | The Company's name differs. Otherwise fix the Company or Warehouse, not the config. |
| `ill_portal_enabled_families` | All four families available, as before. | Restricting families (type JSON, a list). |
| `ill_portal_pilot_users` | All authorized dealers, as before. `[]` would lock dealers out. | Running a named pilot (type JSON, a list). |
| `ill_portal_fixture_groups` | Grouped fixtures off. | After group acceptance (type Boolean). |
| `ill_portal_acceptance` | Acceptance seeding disabled. | Never on production. |
| `qbo_webhook_secret` | The secret is read from ilL-QBO-Settings → Webhook Secret. | Not needed if that field is set. |
| `host_name` | Links in background emails use the site name. | A custom domain is primary. Set it with Domains → *Set Primary*, not by hand. |

---

## 5. Phase 1 — Restore backups and stabilize (OWNER, about 15 minutes)

### 5.1 Restore backups now (self-serve)
The site is Active and current (see Current status), so there is nothing to unblock. The urgent item is
the backup failure (§3.3).

1. Dashboard → Site → **Backups**. Confirm recent backups show as failed (or are missing) since
   Sep 28 morning. If you have an older successful backup, download a copy of it now.
2. Dashboard → Site → **Actions → Migrate**. Leave *Skip failing patches* **unchecked**.
   - This runs `bench migrate` with the deployed `a88f5e4` code. Its `before_migrate` moves
     `private/backups/ill-workspace` to `private/ill-workspace` intact.
   - Nothing else is pending: no patch or schema change since the successful 10:47 AM migration, and
     the hooks are the ones that passed then.
   - This action takes no backup first. That is unavoidable while backups are broken, and it is why
     step 1 comes first.
3. Once it succeeds, Backups → **Schedule Backup** (with files). It must finish successfully. Then
   download the database, private-files and config parts and keep them off-site.
4. If the Migrate job fails, don't retry. Copy the red step's output and send the §5.2 request.

Also:
- Leave the red *Update Bench Configuration* job (§3.0) to support; it doesn't block anything.
- Don't deploy new `main` commits to production until the Phase 2 fixes are merged and rehearsed.

### 5.2 Support request (only if §5.1 step 2 fails, or to clear the bench job)

> Bench group *ilLumenate Production - V16*: the automatic **Update Bench Configuration** job created
> Sep 28, 2026 5:33 PM failed with no step output. Both recorded steps (Update Bench Configuration,
> Bench Setup NGINX) succeeded, so the error is in the job-level traceback, which we can't see. Please
> share it and re-apply the bench configuration (docker compose / memory limits / restart).
>
> Site `illumenatelighting.v.frappe.cloud`: backups fail with `IsADirectoryError`, because
> `frappe.utils.backups.delete_temp_backups()` calls `os.remove()` on the directory
> `private/backups/ill-workspace`, which our app created. [If applicable: our dashboard Migrate, which
> would relocate it, failed with: `paste output`.] Please **move** (not copy, not delete)
> `private/backups/ill-workspace` → `private/ill-workspace`, and, if present,
> `private/backups/b2b-release` → `private/b2b-release`. Preserve `pending.json` and every snapshot. If a
> destination already exists, keep both and tell us; don't merge. A leftover `bypass_unlink.so` in
> `private/backups` is from your streaming backup and can be removed. Then run a full backup and confirm
> it succeeds.

### 5.3 Site Config hygiene (OWNER)
- On **production**, remove `ill_portal_acceptance` if it was set. It enables test-fixture seeding tools.
- `ill_portal_enabled_families` and `ill_portal_pilot_users` must be type **JSON** holding a list, or be
  absent. An empty pilot list (`[]`) **locks every dealer out** of new configurations. Absent means
  "everyone as before". A String-typed value currently makes every configurator request raise (§6.5).
- `ill_portal_fixture_groups` must be type **Boolean** (false until group acceptance). As a String,
  `"false"` is read as *enabled* by two call sites (§6.5).
- `ill_portal_stock_company` is optional (defaults to "ilLumenate Lighting").

### 5.4 Stand up a staging copy (OWNER, needed for Phase 5)
Create a **private bench group** for staging. Pin Frappe/ERPNext/HRMS/CRM/Print Designer to the same
commits as production's target, and point `illumenate_lighting` at a `staging` branch. Create a site from
the fresh production backup (database, public and private files, config). Disable outgoing email and the
scheduler on it. All deploy rehearsals happen there first.

---

## 6. Phase 2 — Code fixes required before the next production deploy (implementing agent)

**How each fix reaches production.** Frappe Cloud runs a *Pull* update (new code, no `bench migrate`, no
backup) unless the diff touches `*/patches.txt`, `*/hooks.py`, `*/fixtures/`, `*/*/custom/` or a
DocType/Workspace/Report/Print Format/Page JSON. Any of those makes it a *Migrate*.
- 6.1, 6.2, 6.4, 6.5, 6.6 and 7.3–7.6 only touch Python, JS and workflow files, so they ship as Pull
  updates.
- 6.3 ships as Pull, but its code takes effect only at the next migrate.
- 7.7 edits `hooks.py`, so it forces a Migrate.
- Batch any Migrate-triggering change separately, after §5.1 has restored working backups.
- Never add a patch whose effect a Pull deploy would silently skip. If a fix needs data or schema
  changes, give it a new `patches.txt` entry so Cloud migrates.

### 6.1 [P0] File `has_permission` hook breaks on v16

**Evidence.** In the deployed Frappe v16 (`frappe/permissions.py`, `has_controller_permissions`):

```python
for method in reversed(methods):
    controller_permission = frappe.call(method, doc=doc, ptype=ptype, user=user, debug=debug)
    if not controller_permission:          # v16: None or False → deny
        return bool(controller_permission)
return True
```

Frappe v15 used `if controller_permission is not None: return bool(...)`, so `None` meant "no opinion".
`illumenate_lighting/illumenate_lighting/portal/private_file.py:7-48` (`portal_file_permission`, registered
for `"File"` at `hooks.py:265`) returns `None` at line 9 for every ptype other than
read/select/print/export, and at line 34 for any file not attached to a portal DocType. On v16 that denies
File create/write/delete to **every user except Administrator**, and denies doc-level read of other private
files. There's no System Manager bypass: controller checks run before role permissions in
`get_doc_permissions`. Introduced in `bc295d6` (Sep 25).

The other 14 `has_permission` hooks in `hooks.py` always return booleans (checked by AST scan). Only the
File hook has this problem.

**Change.**
1. Split the function into `_portal_file_decision(doc, ptype, user) -> bool | None` (current logic), and
   a hook `portal_file_permission` that never returns `None`:
   ```python
   def portal_file_permission(doc, ptype="read", user=None, debug=False):
       decision = _portal_file_decision(doc, ptype, user)
       if decision is not None:
           return decision
       # No portal opinion: defer to Frappe's own File rule. v16 treats a falsy hook result as a
       # denial, and on v15 a bare True here would short-circuit Frappe's File hook.
       from frappe.core.doctype.file.file import has_permission as file_has_permission
       return bool(file_has_permission(doc, ptype=ptype, user=user))
   ```
2. `PortalFile.is_downloadable` keeps using `_portal_file_decision` (None → `super()`).
3. Add a guard test in `tests/portal_unit` that AST-scans every `has_permission` hook in `hooks.py` and fails
   on a bare `return`, `return None`, or a path that can fall off the end. This prevents a repeat.
4. Add an installed-site regression module
   (`illumenate_lighting/illumenate_lighting/api/test_file_permissions.py`, v16 `IntegrationTestCase`),
   and add it to the v16 CI step. Users: a non-Administrator **System Manager**, and a **Sales User**
   with Sales Order write. Assertions:
   - both can insert a File attached to a Sales Order they can write;
   - the System Manager can insert a File attached to an `ilL-Webflow-Product` (the diagnostic's scenario);
   - both can read and delete their own attachment;
   - the Sales User is denied a private File attached to a Sales Order they cannot read;
   - portal-owned files (`ilL-Order-Intake`, `ilL-Quote-Offer`, `ilL-Export-Job`, `ilL-Portal-Upload`,
     `ilL-Document-Request`) keep their current allow/deny decisions.

**Acceptance.** New tests pass on v16 CI. The debug endpoint's scenario (System Manager uploading a
featured image to `ilL-Webflow-Product`) succeeds.

### 6.2 [P0] Sales Order approval gate blocks normal ERPNext flows

**Evidence.** `portal/order_review.py`:
- `before_submit` (line 166), `on_submit` (222) and `validate_order` (400) run for every Sales Order with
  `ill_fixture_schedule` set.
- `before_submit` calls `_load()`, which throws "This order has no portal intake…" (line 137) when no
  `ilL-Order-Intake` exists.
- The Quotation custom field `ill_fixture_schedule` (`patches/consolidate_section_label_field.py:77`) is
  not `no_copy`. So ERPNext's *Quotation → Create → Sales Order* copies it, but creates no intake.
  `quote_from_schedule.py:133-142` sets it on Quotations built from schedules.
- Even with an intake, only `System Manager` or `ilL Order Approver` (a new role that nobody holds yet)
  may submit.
- Draft Sales Orders created before this deploy that link to a schedule are also stuck.

**Change.** Apply the portal approval workflow only to portal-originated orders, meaning orders with an
`ilL-Order-Intake` row. Everything else gets native ERPNext behavior, as before September.
1. Add a helper, e.g. `_intake_name(order) -> str | None`
   (`frappe.db.get_value("ilL-Order-Intake", {"sales_order": order.name}, "name")`).
2. `before_submit` and `on_submit`: return early when there's no intake (instead of the
   `ill_fixture_schedule` check).
3. `validate_order`: keep stamping `ill_delivery_confirmed_by/on` for all orders. Apply `_staff()` checks
   and the "past date" / "submitted promise" rules only to intake orders. The amendment branch (clearing
   offer and promise) also applies only to intake orders.
4. Dealers can't bypass review this way: `DEALER_PERMISSION_MATRIX` gives Dealers no Sales Order
   `submit`, and portal conversions always call `capture()`
   (`ill_project_fixture_schedule.py:491-493`, `offers.py:335-356`).
5. Tests (installed-site, v16):
   - a Quotation with `ill_fixture_schedule` → `make_sales_order` → submit as a user with Sales Order
     submit permission (no ilL roles) succeeds;
   - an intake order still requires acknowledgment and approver;
   - amending a non-intake order works for a Sales Manager.

**Acceptance.** The same Sales Order flows that worked on August 24 work again for users with only
standard ERPNext roles.

### 6.3 [P0] Migration hooks must never abort `bench migrate`

**Evidence.** The `after_migrate` workspace restore has already failed a production migration twice
(missing Number Cards, then `MandatoryError: type`). Each failure costs a full rollback.
`private_storage.private_state_directory` raises `FileExistsError` when both the legacy and new dirs exist,
from inside `before_migrate` (`portal_workspace.py:52,55`), which also aborts the migration.

**Change.**
1. `portal_workspace.before_migrate` and `after_migrate`: wrap the bodies in `try/except Exception`. On
   failure, `frappe.log_error(title="ilL workspace preservation", ...)` and return. Never re-raise. Keep
   `pending.json` whenever the merge didn't complete, so the next migration retries it.
2. `after_migrate`: if `pending.json` names a snapshot that doesn't exist, log it and leave `pending.json`
   in place. Don't throw.
3. `private_storage.private_state_directory`: when **both** the legacy and new dirs exist, don't raise.
   Move the legacy directory intact to `private/<name>/legacy-<UTC timestamp>/` (a new, unique path, so
   nothing is merged or overwritten), then log a warning that a person should review it. This clears
   `private/backups` so backups work again. Keep the file and symlink refusals, but log and return the
   destination instead of raising, when called from the migration hooks.
4. Unit tests in `tests/portal_unit/test_private_storage.py`:
   - conflict case relocates into `legacy-*` and preserves both trees byte-for-byte;
   - a hook exception doesn't propagate;
   - a missing snapshot keeps `pending.json`.

**Acceptance.** A migration with a corrupted `pending.json`, a missing snapshot, or both dirs present
completes. The Error Log explains what was skipped.

### 6.4 [P0] Remove the temporary diagnostic endpoint

Delete `illumenate_lighting/illumenate_lighting/api/permission_debug.py` (added in PRs #257/#258) once 6.1
is merged. It is labelled temporary, and 6.1 fixes the problem it was diagnosing.

### 6.5 [P1] Make site-config flags tolerant of how Frappe Cloud stores them

**Evidence.**
- `templates/pages/configure.py:34`, `api/desk_configurator.py:245` and
  `portal/release_evidence.py:145` use `bool(frappe.conf.get("ill_portal_fixture_groups"))`, so the String
  `"false"` counts as enabled.
- `api/fixture_group_bom.py:147` and `api/fixture_group_configurator.py:220` use `parse_bool`, so the UI can
  show group mode while the server rejects it.
- `portal/rollout.py:8-12` raises `ValueError` on every configurator request if
  `ill_portal_enabled_families` or `ill_portal_pilot_users` is stored as a JSON **string**.

**Change.**
1. Add `conf_flag(key, default=False)` (using `configuration_contract.parse_bool`, logging and returning
   the default on invalid input) and `conf_list(key)` (accepting a list or a JSON-encoded string of a
   list). Put them in a small module such as `illumenate_lighting/illumenate_lighting/portal/site_flags.py`.
2. Use them at all five `ill_portal_fixture_groups` reads and in `rollout._list`.
3. Invalid list values: log to the Error Log and treat as *absent*, which preserves availability, instead
   of raising.

**OWNER decision:** confirm "invalid → absent (fail open)". The alternative is "invalid → block new
configurations with a clear message".

### 6.6 [P0] Get CI green and make it test the upgrade path

1. **B2B local contracts:** before the `TemporaryDirectory(... dir=ROOT / ".tools")` at
   `tools/check_portal_templates.py:281`, add `(ROOT / ".tools").mkdir(exist_ok=True)`. Or add
   `mkdir -p .tools` to `.github/workflows/b2b-contracts.yml`.
2. **Server (version-15):** production is v16 and code now relies on v16 behavior. Remove v15 from the
   matrix in `.github/workflows/ci.yml`, or mark it `continue-on-error: true`. If kept, fix bootstrap by
   completing ERPNext setup before tests: add `before_tests` in `hooks.py` pointing at ERPNext's
   `erpnext.setup.utils.before_tests` (verify that function exists on the pinned ERPNext) or an app
   wrapper around it.
3. **Server (version-16):** add the new modules from 6.1 and 6.2. Optionally run the full suite once
   `before_tests` is in place.
4. **New job: upgrade rehearsal (v16).** This is the gap that let every production failure through.
   1. Check out the app at `PREVIOUS_DEPLOYED_SHA`, a repo variable. Set it to the commit production
      actually runs from Phase 0; otherwise use `12c76df`.
   2. Install it on a fresh v16 + ERPNext site. Seed minimal data: a Customer, a schedule-linked Quotation
      and Sales Order, an Issue, a Workspace customization (extra custom block), and a legacy
      `private/backups/ill-workspace/` with `pending.json` plus a snapshot.
   3. Check out `HEAD` and run `bench migrate` twice, so all 11 new patches **actually execute**.
   4. Then run: `bench --site test_site backup` (proves `private/backups` is clean), the 6.1/6.2 tests, and
      a check that the workspace kept the custom block.
   5. If practical, also install HRMS, CRM and Print Designer at the production commits, to mirror
      production's `after_migrate` ordering.
   6. Reproduce production's installed-app order (§4.1): `frappe, illumenate_lighting, erpnext, hrms,
      crm, print_designer`. Install normally, then set the `installed_apps` global to that order before the
      HEAD migration.

**Acceptance.** Both workflows green on the Phase 2 PR. The upgrade-rehearsal job passes, and fails if 6.1,
6.2 or 6.3 is reverted.

---

## 7. Phase 3 — "Works like before" regressions (implementing agent + OWNER decisions)

These are deliberate B2B design changes, but each changes existing staff or dealer behavior. For each:
confirm with OWNER, then either restore the old behavior or keep it and document the required setup.

### 7.1 [P1] Staff need the new job roles
- New roles: `ilL Sales Review`, `ilL Order Approver`, `ilL Engineering`, `ilL Catalog Publisher`,
  `ilL Integration`, `ilL Support`, `ilL Operations` (`portal/staff.py:6-14`,
  `patches/b2b_portal_foundations.py:70-80`).
- **No users get these roles automatically.** Only System Manager is treated as internal
  (`ill_project.py:10`). Staff who used standard ERPNext roles (Sales User/Manager, Stock User…) lose:
  - portal project and schedule visibility;
  - approval of portal orders;
  - Webflow "Mark Pending" (`webflow_export.trigger_sync` now calls `require("catalog")`);
  - catalog authoring, drawing review, and support queues.
- **Deliverable:** a Bench-only System Manager helper, `portal/role_audit.py::report()`, that lists enabled
  System Users and which capability each has or lacks. Plus a checklist in `docs/B2B_STAFF_OPERATIONS.md`
  mapping each person to roles.
- **OWNER:** assign roles on production right after the deploy (staging first).

### 7.2 [P1] Dealer access changes
- `b2b_portal_foundations` sets `Role Dealer.desk_access = 0` (line 82). Dealer users whose only
  desk-granting role was Dealer lose Desk, and become Website Users the next time their User record is
  saved.
- `dealer_permissions.DEALER_PERMISSION_MATRIX` revokes every Dealer permission not listed on 8 ERPNext
  DocTypes. For example, Sales Order is read/create/print only.
- **OWNER:** confirm dealers should be portal-only. If some dealers relied on Desk, list them before the
  deploy.

### 7.3 [P1] Dealer → Customer resolution returns nothing when ambiguous
- `ill_project._get_user_customer` (line 148) now returns `None` when a user's Contacts (matched by `user`
  **or** `email_id`) link to more than one Customer. Before September, the Contact linked by `user` won,
  then the first Customer link. Affected dealers silently lose their company's projects, schedules and
  orders.
- **Change:**
  1. Prefer Contacts whose `user` field equals the user. Consider email-only matches only when there are
     none.
  2. Among the chosen Contacts, if exactly one Customer is linked, use it.
  3. Keep `None` only for genuine ambiguity. Also add a Bench-only audit, `portal/role_audit.py::dealers()`,
     that lists Dealer users with 0 or more than 1 resolved Customer, so staff can fix Contact links.
- Tests in `tests/portal_unit` for all three branches.

### 7.4 [P2] Webflow sync endpoints reject Desk calls (pre-existing, but now user-visible)
- `webflow_export.trigger_sync(product_slugs: list, category_slugs: list)` (line 824),
  `webflow_attributes.trigger_attribute_sync(doc_names: list)` (1150), and
  `get_product_attribute_references(product_slugs: list)` (1713): `frappe.call` JSON-stringifies arrays
  (`request.js` in v16), and Frappe's pydantic validation rejects a string for `list` **before** the
  function body's own `json.loads` runs. Verified locally with pydantic: `Union[list, None]` rejects
  `'["slug"]'`. The "Mark Pending" button in `ill_webflow_product.js:96` is affected.
- **Change:** annotate these as `str | list | None`, and keep the existing `json.loads` normalization.

### 7.5 [P2] Other whitelisted parameters that reject blank form values
- Frappe validates whitelisted-method annotations during requests. A scan (excluding modules with
  `from __future__ import annotations`, which Frappe skips: `desk_configurator.py`,
  `configured_product_builder.py`, `webflow_brand.py`) found **48 int/float** and **29 bool** parameters
  that reject `""`. jQuery sends `null` and empty inputs as `""`.
- **Change:** extend the existing test
  `test_configurator_transport.test_all_optional_numeric_whitelist_parameters_accept_form_blanks`:
  cover parameters with non-`None` defaults (e.g. `qty: int = 1`) and `list`/`dict` annotations
  (JSON-string input). Fix failures by widening annotations to `str | int | None` (etc.) and normalizing
  inside. Prioritize endpoints called from portal/desk JS with optional inputs.

### 7.6 [P2] `commercial_lineage.validate` runs on every Delivery Note and Sales Invoice
- `portal/commercial_lineage.py:34-62` is hooked on all DN/SI `validate`. It throws when the source order
  has a different customer or company, isn't submitted, or has a different `item_code`. It also overwrites
  lineage fields from the source row on every save.
- **Change:** skip rows whose source row carries no configured-lineage fields (no `ill_configured_*`,
  `ill_fixture_schedule`, `ill_schedule_line_id`). Standard ERPNext stock and invoicing then behaves as
  before. Keep the checks for configured rows. Add a test with a plain stock Item DN from a Sales Order.

### 7.7 [P2] Unfiltered `Custom Field` fixture export
- `hooks.py:181-207` exports `{"dt": "Custom Field"}` with no filter, plus `Item` and `Workspace`. Anyone
  running `bench export-fixtures` would write **every app's** custom fields into
  `illumenate_lighting/fixtures/`. Since the Number Card move, that directory is imported on every
  migrate, so it would overwrite ERPNext, HRMS and CRM fields.
- **Change:** filter Custom Field to `[["module", "=", "ilLumenate Lighting"]]`, or remove the entries the
  app doesn't intend to ship. Add a comment that `fixtures/` is live on every migrate.

### 7.8 [P3] Dead route
`hooks.py:110-111` routes `/portal/configure-kit` to a `configure_kit` page that doesn't exist (404).
Remove the rules or add a redirect to `/portal/configure`.

---

## 8. Phase 4 — Repository hygiene and deploy pipeline (implementing agent + OWNER)

1. **Stop shipping local tool caches.** Frappe Cloud copies the whole repository into every build image.
   - Remove `.repowise/` (1,235 files, about 140 MB, including SQLite `wiki.db`/`-wal` and pickles).
   - Remove `tools/yaml_builder_ui/.npm-cache/` (about 10 MB).
   - Remove `diff_bbb8605.txt` and `output/` (generated CSVs).
   - Use `git rm -r --cached` and add all of them to `.gitignore`.
   - Decide whether `tools/configurator_ui/dist-preview/` (about 10 MB) should be built rather than
     committed.
   - `.mcp.json` and `.codex/config.toml` contain only local Windows paths (no secrets found), but they
     belong in local config.
2. **Branching.** Protect `main`: require PRs and green CI. Use a `staging` branch for the staging bench
   group, promote to `main` by PR, and tag production releases (`release-2026-10-xx`). Replace "asdf"
   commit messages with descriptive ones.
3. **Deploy one thing at a time.** App deploys should not include Frappe/ERPNext/HRMS/CRM/Print Designer
   version bumps. Framework upgrades get their own staging rehearsal.
4. **Update the existing repair docs** (`docs/FRAPPE_CLOUD_BACKUP_REPAIR_2026_09_28.md`,
   `docs/B2B_CLOUD_ACCEPTANCE.md`) to point at this plan, and correct the `bypass_unlink.so` note (§3.4).

---

## 9. Phase 5 — Staging rehearsal and production cut-over (OWNER + implementing agent)

1. Merge Phase 2 into `staging`. Deploy to the staging bench group and update the staging site (which was
   restored from production).
2. Confirm on staging:
   - the update log shows every new patch executing, `Executing after_migrate hooks…` with no traceback,
     and no new Error Log entries titled "ilL workspace preservation";
   - `bench backup` / *Schedule Backup* succeeds, and `private/backups` holds only backup files.
3. **Smoke test on staging.** Use real non-Administrator users for each item.
   - [ ] System Manager uploads an attachment to a Sales Order, an Item image, and an
         `ilL-Webflow-Product` featured image; opens and deletes a private attachment.
   - [ ] Sales User: Quotation from a fixture schedule → Create Sales Order → **Submit**. Then Delivery
         Note → Sales Invoice from that order.
   - [ ] Work Order from a configured Sales Order (manufacturing generator runs; no drawing hold unless a
         request is flagged `required_for_manufacturing`).
   - [ ] Desk "Configure & Add Fixture" dialog on a Quotation, for each of the four families.
   - [ ] Dealer: `/portal` dashboard, projects, schedule page (stock label shows or says "unavailable"),
         configurator save to schedule, orders list and order detail.
   - [ ] Webflow product "Mark Pending" (after 7.4) as a Catalog Publisher.
   - [ ] A normal ERPNext notification email reaches the Email Queue and sends (mail sink).
   - [ ] The ilLumenate Lighting workspace opens with all six number cards and its custom blocks.
   - [ ] Error Log: no new errors after one hour with the scheduler enabled.
4. Assign staff roles on staging (7.1) and repeat the relevant checks as those users.
5. Production:
   1. Pick a maintenance window and confirm a successful fresh backup (Phase 1).
   2. Deploy the exact commit that passed staging.
   3. Update the site.
   4. Run the same smoke test.
   5. Assign roles.
   6. Watch the Error Log.
6. **Rollback:** restore the matched pre-update backup (database, files, config) together with the previous
   app commit. Never run old code against a database that newer code has migrated.

---

## 10. Owner decisions needed (defaults in bold)

| # | Decision | Default |
| --- | --- | --- |
| 1 | Portal approval workflow applies to | **Only orders with a portal intake (§6.2)** |
| 2 | Invalid rollout list config | **Treated as absent and logged (§6.5)** |
| 3 | Keep the v15 CI job | **Remove; production is v16** |
| 4 | Dealers lose Desk access | Confirm (currently yes) |
| 5 | Staff role mapping | Owner supplies names → roles |
| 6 | `tools/configurator_ui/dist-preview` committed | **Build it instead of committing it** |

---

## Appendix A — How findings were verified

- Frappe v16 behavior: read at the deployed commit `012667b9…`, in `frappe/permissions.py`
  (`has_controller_permissions`), `frappe/utils/backups.py` (`delete_temp_backups`),
  `frappe/core/doctype/file/file.py`, `frappe/utils/typing_validations.py`, `frappe/__init__.py`
  (`whitelist`) and `frappe/public/js/frappe/request.js`. Compared with `version-15` for the permission
  hook semantics.
- Frappe Cloud behavior: read in `frappe/agent` (`agent/site.py`, `agent/server.py`, `agent/bench.py`,
  `agent/web.py`, `lib/bypass_unlink.c`) and `frappe/press` (`press/agent.py`, site and site_update
  DocTypes).
- CI: GitHub Actions runs 36500862803 ("CI") and 36500862764 ("B2B local contracts") on `a88f5e4`.
- Local: Python 3.14 compile of all modules, JSON parse of all app JSON, `ruff` (F821/F811/E9/F7), the
  `tests/portal_unit` suite (231 tests, OK), an AST scan of `has_permission` hooks and whitelisted
  annotations, a DocType schema diff `12c76df..HEAD`, and hooks.py reference resolution.
- Not verified: the live Cloud site's state, data or logs (no access from here), and a full upgrade
  migration against a copy of production data (Phase 5 covers it).
