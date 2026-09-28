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
- Verified that retrying the workspace hook preserves the original site backup and custom blocks/shortcuts, consumes `pending.json` only after a successful save, and does not duplicate the six shipped card links.
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

The Cloud migration retry and this installed-site test have not been run from the local Windows workspace.
