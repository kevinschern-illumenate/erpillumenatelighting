# Photometric migration repair

The reported migration fails during DocType synchronization, when MariaDB tries
to change `mounting_height`, `light_level`, and `beam_diameter` on
`ilL-Child-Photometric-Data` to `decimal(21,9)`. Existing display measurements such
as `6 ft` cannot be converted under strict SQL mode. An `after_migrate` hook or
post-model-sync patch would run too late to fix this failure.

The child DocType defines these measurements as `Float`, which conflicts with
the existing unit-bearing text in the site's database. The repair changes the
three measurements to `Data` and updates the controller's type annotations.
The existing product projection passes these display values through without
numeric calculations; keeping their units
avoids silently changing their meaning. `display_order` remains an integer.

The parent template's photometric layout, chart fields, and shared schema
definitions are preserved. The legacy Webflow Product copy/backfill rules are
unchanged.

Catalog Builder's generated schema, bundled assets, and tape/neon examples are
updated together. Example measurements include their feet/footcandle units so
they pass the text-field import validation and retain their meaning.

Deploy this revision of `illumenate_lighting` through the site's normal Frappe
Cloud deployment process, then retry migration. For a bench-managed deployment,
after updating the app code:

```sh
bench --site illumenatelighting.v.frappe.cloud migrate
```

No data-cleanup SQL, unit stripping, SQL-mode relaxation, or skipped patches are
needed. Existing text is retained, including blanks and annotations. Sites that
already have numeric columns can migrate back to text while retaining the stored
numeric values; units previously discarded cannot be reconstructed.

Regression coverage in `api.test_migration_assets.TestPhotometricMigration` uses
isolated MariaDB tables and Frappe's schema-sync code to exercise the original
conversion failure, preserved rows on retry, repeated synchronization, already
numeric columns, and fresh tables. The local unit suite also checks DocType
packaging, field-order consistency, and unmodified measurement projection.

Verified locally with Frappe 16.36.0 and MariaDB 11.8.6: two complete migrations,
all three database regression tests, all 1,097 portal unit tests, 134 fixture
builder tests, six builder JavaScript test files, the builder production build,
and the changed-file lint/schema checks passed. The production cloud site has not been
modified by this investigation.
