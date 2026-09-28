# Portal commercial schema repair — September 28, 2026

`/portal` failed with `Unknown column 'ill_configured_led_sheet' in 'SELECT'` when the user had existing Sales Orders. The dashboard and order list share `portal.orders.list_orders`, which selects configured-product references from Sales Order Item to calculate production coverage.

## Cause

The legacy `illumenate_lighting/illumenate_lighting/fixtures/custom_field.json` defines the LED Sheet links on Quotation Item and Sales Order Item, but that nested fixture directory is not loaded by Frappe. The original configurator patch only defined fixture and tape/neon links; the later commercial-lineage patch added LED Sheet links only to Delivery Note Item and Sales Invoice Item.

The local database audit also exposed the fresh-install variant: historical patches are marked complete on installation, and `after_install` did not create several base configurator fields or the quotation/order schedule links. An empty database did not exercise the child-row selection used when an order exists. The earlier migration checks therefore passed without detecting this runtime contract gap.

## Repair

- The shared commercial setup now creates missing fields across Quotation Item, Sales Order Item, Delivery Note Item and Sales Invoice Item, along with quotation/order schedule links and source-row power-supply tracking fields.
- Existing field settings are preserved. Missing supported product choices, including LED Sheet, are appended without removing site-specific choices.
- The new post-schema patch `illumenate_lighting.patches.b2b_commercial_schema` runs this setup on sites that already completed the old patches. The existing `after_install` hook calls the same corrected setup for new installations.
- The order-detail read model now uses `order.get("remarks")`; `remarks` is not guaranteed to exist on the deployed Sales Order schema. Real page rendering exposed this additional failure.

This adds schema and updates product-choice metadata. It does not rewrite historical commercial transactions or reset Patch Log.

## Verification and deployment

The regression suite checks physical database columns and metadata for the complete commercial-lineage contract on all four item DocTypes. It also inspects literal field selections in portal services and page controllers against the installed database, exercises repeated setup with older product choices and a custom label, and renders `/portal`, `/portal/orders`, and `/portal/orders/<order>` with an existing Sales Order and item row.

The rendering tests use Frappe's route resolver, page controllers, real database queries and Jinja templates in the isolated exact-version Bench described in [the migration repair notes](B2B_MIGRATION_REPAIR_2026_09_28.md). They do not execute browser JavaScript or compile asset bundles.

Final results: **208 local unit tests and all eight installed-site regression tests passed**. The new patch executed successfully through a complete migration, and a second migration passed. The SQL-field audit passed, all three portal routes returned HTTP 200 and contained the seeded order, and repeated schema setup preserved the custom product label and additional product choice. Changed-file Python syntax/lint and Git whitespace checks passed. The Cloud site itself was not modified locally.

Deploy the updated application and run **Migrate** again. The migration log should include `illumenate_lighting.patches.b2b_commercial_schema`. Reload `/portal` and open an existing order after migration succeeds. Updating application code alone does not create the missing database columns.
