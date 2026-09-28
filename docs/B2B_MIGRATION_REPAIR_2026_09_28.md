# September 28 Cloud migration repair

The owner deployed successfully to `illumenatelighting.v.frappe.cloud`. The supplied log shows ERPNext v16 patches and Python 3.14. All B2B patches completed, but the workspace restoration failed during `after_migrate` because six Number Card records were missing. The same log also reported three app DocTypes as orphaned.

## Fixes

1. Moved the existing six Number Card definitions to `illumenate_lighting/fixtures/number_card.json`. They were one directory too deep, under `illumenate_lighting/illumenate_lighting/fixtures`. Frappe reads fixtures from the app-level directory during both installation and migration, before the workspace restoration hook. The card definitions and names are unchanged. See [Frappe v16 fixture discovery](https://github.com/frappe/frappe/blob/version-16/frappe/utils/fixtures.py).
2. Corrected the controller class names to `ilLChildGroupMember`, `ilLChildGroupAllocation`, and `ilLConfiguratorSession`. Frappe derives the class name by removing spaces and hyphens from the DocType name, preserving capitalization. The old `Ill...` / `IlL...` names caused import failures. See [controller loading](https://github.com/frappe/frappe/blob/version-16/frappe/model/base_document.py) and [orphan cleanup](https://github.com/frappe/frappe/blob/version-16/frappe/model/sync.py).

The next schema sync should recreate the three missing DocType definitions and successfully load their corrected controllers. Frappe's orphan cleanup is documented in its source as retaining the underlying data tables; no manual deletion or table recreation is part of this repair. Actual site records have not been inspected remotely.

## Follow-on investigation

- Checked all 146 shipped DocTypes for exact controller class names, matching schema paths, Python package files and declared modules. Only the three reported DocTypes had naming errors.
- Checked all 62 child-table fields and 234 app-specific Link fields against the shipped schema. All targets resolve; child-table targets are marked as child tables.
- Checked every shipped workspace shortcut, link and Number Card target. The Sales Team Commissions report and Portal Operations page exist. The workspace declares no charts, quick lists or custom blocks that require additional seed records.
- Verified that retrying the workspace hook preserves the original site backup and custom blocks/shortcuts, consumes `pending.json` only after the migration transaction commits, and does not duplicate the six shipped card links.
- The module-level legacy fixtures directory also contains older product samples, custom fields and workflow exports. Those files were not automatically loaded before this repair. Only the six workspace cards are activated here; automatically importing all legacy exports would change existing business setup and requires a separate dependency/data review. They do not introduce a new migration step in this repair.

## Validation and retry

Local regression checks are in `tests/portal_unit/test_migration_assets.py` and run in the existing B2B contract CI job. They check the complete shipped schema and reproduce a failed workspace save followed by fixture availability and a successful retry. Framework/database boundaries are simulated locally.

On September 28, all **200 local portal unit tests passed**, including seven new migration regressions. The changed-file syntax/JSON/lint check passed with zero new diagnostics. The six relocated Number Card definitions were compared with the committed originals and are unchanged.

Deploy the updated app revision, then rerun **Migrate** in Frappe Cloud. Keep the site's existing `private/backups/ill-workspace/pending.json` and its referenced backup: they hold the workspace customization snapshot from the interrupted migration. No Patch Log reset or manual card creation is needed.

After migration, verify the ilLumenate Lighting workspace opens with all six financial cards and Portal Operations, and that `ilL-Child-Group-Member`, `ilL-Child-Group-Allocation` and `ilL-Configurator-Session` are no longer reported as orphaned. Inspect an existing configured group/session if the site has such records.

An additional installed-site regression module exercises real controller imports and Frappe link validation. On an isolated migrated test site:

```sh
bench --site TEST_SITE run-tests --app illumenate_lighting --module illumenate_lighting.illumenate_lighting.api.test_migration_assets
```

The original checks above were insufficient: they checked workspace links but missed a mandatory field during the complete save pipeline. The follow-up below supersedes the original validation limits.

## Follow-up: mandatory Workspace type and full-stack rehearsal

The next Cloud attempt failed with `MandatoryError: [Workspace, ilLumenate Lighting]: type`. In the deployed Frappe version, `Workspace.type` is mandatory. Neither the exported workspace nor an older site's saved workspace snapshot supplied it. Import defaults do not repair the snapshot that our `after_migrate` hook subsequently restores. See the [exact deployed Workspace schema](https://github.com/frappe/frappe/blob/012667b9c4e7f66d5e1ff5858d2e922331d4300a/frappe/desk/doctype/workspace/workspace.json).

The repair now:

- Exports `type: Workspace` and supplies that value when merging legacy snapshots whose type is absent, null or blank. Explicit `Workspace`, `Link` and `URL` types and their destinations are retained.
- Keeps the pending backup until Frappe commits the migration transaction. If a later app hook fails, the original snapshot remains available for the next attempt. This follows the [deployed migration transaction boundary](https://github.com/frappe/frappe/blob/012667b9c4e7f66d5e1ff5858d2e922331d4300a/frappe/migrate.py).
- Corrects two DocType `naming_rule` values from `random` to the supported `Random`, in `ilL-Child-Driver-Input-Protocol` and `ilL-Child-Profile Environment`.
- Corrects the stored Email Campaign Activity Summary Report Column type from `Percent` to `Float`; its label still says `Open Rate (%)`. Runtime report columns are unchanged.
- Removes site-specific Link defaults from QBO Settings (`paid_to_account` and `mode_of_payment`). A real fresh install exposed a LinkValidationError when those named records did not exist. Existing saved settings are retained.

The schema audit covers all 156 shipped migration asset files, including 146 DocTypes, against mandatory, Select, length and JSON constraints from the exact deployed Frappe schema. All Single DocTypes are also checked for hardcoded Link defaults. The six Number Cards and workspace use complete saves in the installed-site regression suite.

An isolated local Ubuntu Bench was built with Python 3.14.2, MariaDB 10.11.13 and separate Redis services. It uses the exact five upstream revisions provided by the owner:

| App | Commit | Reported version |
| --- | --- | --- |
| Frappe | `012667b9c4e7f66d5e1ff5858d2e922331d4300a` | 16.35.0 |
| ERPNext | `fb78e58b8c037bcff4f90b7361ad81ff7b1c42ba` | 16.36.1 |
| HRMS | `c0a04b80eeb721417b75cea758e831464d0da041` | 16.20.0 |
| CRM | `a6dfe8bf39e74c22b6212a43c8dadfb569c12154` | 1.85.1 |
| Print Designer | `7beaad298dd60467223c9a2b0360dd8c216a2b91` | 1.6.7 |

The application copy includes this repair. All six apps installed successfully. Two complete migrations passed. A separate upgrade scenario used the same installed-app order as the Cloud log, deliberately blanked the workspace type, preserved a pending legacy snapshot and custom block, and re-ran all eight B2B patches by resetting their Patch Log entries **only in the disposable test database**. That migration and its immediate retry passed, including verification of the restored type, custom block and committed backup receipt. Do not reset Patch Log on Cloud.

Final local results on September 28: **205 portal unit tests passed**, and **all four installed-site migration integration tests passed**. The latter validate every imported asset's field constraints, load every shipped DocType controller after orphan cleanup, save all six cards and the workspace, and reproduce the mandatory error before repairing legacy snapshots with absent/null/blank types. Changed-file Python syntax, JSON parsing and lint checks passed with zero new diagnostics. The complete migration and retry passed again with the final test module.

CI now rehearses two migrations on both Frappe v15 and v16. The existing full server test suite remains on v15; the new migration regression module also runs on v16 using its `IntegrationTestCase` API. GitHub Actions itself was not run locally. The legacy v16 test compatibility class eagerly prepares unrelated ERP fixtures (including optional Payment Gateway records), so the migration module uses the modern test class with a v15 fallback.

The rehearsal uses a fresh database plus explicit upgrade scenarios, not a copy of the Cloud database. It verifies the exact app stack and reported failure, but cannot certify unknown Cloud customizations or existing data. Cloud has not been modified from this workspace. Deploy the corrected app and rerun **Migrate**, keeping the existing pending workspace backup.
