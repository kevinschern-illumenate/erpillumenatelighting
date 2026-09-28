# September 28 Cloud backup cleanup repair

The update of `illumenatelighting.v.frappe.cloud` fails at **Backup Site** with
`IsADirectoryError` for `private/backups/ill-workspace`. Frappe's
`delete_temp_backups()` tries to unlink that directory as a file before starting
the database dump. The generic corruption message does not establish database
or site configuration corruption. See the
[Frappe backup implementation](https://github.com/frappe/frappe/blob/version-16/frappe/utils/backups.py).

The app's workspace migration hook created this directory to retain workspace
customizations across migration retries. Its `pending.json` may identify the
only original snapshot from an interrupted migration. **Preserve the entire
directory, including the pending pointer and every snapshot.**

## Immediate recovery when SSH is unavailable

Open a ticket with [Frappe Cloud support](https://support.frappe.io/) and include
the traceback and the following request:

> Site: illumenatelighting.v.frappe.cloud. The app update fails at Backup Site
> because `frappe.utils.backups.delete_temp_backups()` calls `os.remove()` on
> `private/backups/ill-workspace`, raising `IsADirectoryError`.
>
> Please preserve and move the entire site directory from
> `private/backups/ill-workspace` to `private/ill-workspace`, outside Frappe's
> backup cleanup directory. Keep `pending.json` and all referenced snapshots
> intact. If `private/backups/b2b-release` also exists, move it intact to
> `private/b2b-release`. Do not overwrite or nest into an existing destination;
> if both copies exist, preserve both and report the conflict before proceeding.
>
> The backup listing also contains `bypass_unlink.so`. Please identify its
> origin and whether it is used by this bench. It is not the directory that
> triggered this traceback, and our app repository has no reference to it.
>
> Coordinate the move with deployment of the app's corrected storage paths,
> then take a fresh backup including database, public/private files and site
> configuration, and retry the Cloud app update/migration. Please do not delete
> workspace snapshots, bypass the backup, or reset Patch Log.

Do the move while no migration or evidence capture is running. Deploy this fix
before running another workspace migration: the old hook would recreate the
old directory and would not read the relocated pending snapshot. An app
migration patch alone cannot unblock the initial Cloud backup, because that
backup runs first. The local repository change has not modified the Cloud site.

The workspace snapshots and release evidence live outside `private/files`;
Frappe's normal files archive does not include these app-state directories.
Retain a separate private copy through the repair, migration and any site move.
If Cloud moves this site between benches/servers, ensure the relocated app-state
directories reach the destination before migration runs. Never publish them
under `public/files`.

## Permanent app correction

- Workspace snapshots now use `private/ill-workspace`.
- Release checkpoints and acceptance manifests now use `private/b2b-release`.
- The shared storage helper relocates a legacy directory intact when first
  accessed with the corrected code. It refuses conflicting destinations,
  unexpected files and symlinks. It never merges or deletes snapshot contents.
- Existing pending snapshots remain authoritative until the complete migration
  transaction commits; workspace merge behavior is unchanged.

Once Cloud reports a successful backup and migration, verify the ilLumenate
Lighting workspace retains its custom blocks and destinations, all six shipped
financial cards open, and no app directories remain under `private/backups`.

Local regressions in `tests/portal_unit/test_private_storage.py` exercise real
temporary directories and simulated Frappe/database boundaries: relocation,
cleanup isolation, conflict preservation, legacy pending restore through commit,
new snapshots, and release checkpoint read/write compatibility. These do not
certify a live Cloud backup or migration.

Validation for this repair: all **228 portal unit tests passed** using the
repository's `.venv` Python, including six new storage regressions. Ruff checks
passed for all five changed/new Python files, and formatting checks passed for
the new helper and regression module. The Cloud backup and migration remain
unverified until the operator completes the recovery above.
