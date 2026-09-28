# Schedule stock availability repair - September 28, 2026

Opening a populated fixture schedule failed when the stock service could not find an enabled, non-group `ilL-Stores` warehouse for the selected company. The stock lookup raised a validation error during page rendering. It also inherited ERPNext's global default company unless a site override existed, which could select a different company from the one intended for the portal.

## Behavior

- The default portal stock company is now the user-confirmed **ilLumenate Lighting**. The warehouse remains **ilL-Stores**, matched by `Warehouse.warehouse_name`, so the ERPNext company suffix in the document name is allowed.
- An explicit `ill_portal_stock_company` site configuration value still takes precedence. The release inventory report uses the same company resolver.
- Missing stock scope returns `availability: unknown` to optional schedule, fixture, BOM-item, batch-fixture and extrusion-kit stock views. The schedule and fixture configurator display **Stock availability unavailable**. Schedule access and editing remain available.
- Unknown results contain no quantities or shortages. A configured warehouse with insufficient stock still produces the normal shortage result.
- Stock never falls back to other warehouses or companies. The SQL continues to use on-hand quantity minus reserved quantity within the approved scope.
- Only the specific missing-scope exception is handled this way. Database failures and unrelated programming errors are not converted into unknown stock.

This change follows the original plan's stock-scope requirement in S4.5. It adds no schema, warehouse records, inventory transactions or migration patches.

## Verification

Local unit and DOM tests cover the default company, explicit overrides, missing scope across stock entry points, empty component demand, shared schedule demand, unrelated-error propagation, and the display transition between known and unknown availability.

Installed-site regressions use the [exact-version isolated Bench](B2B_MIGRATION_REPAIR_2026_09_28.md), with all five framework/add-on commits supplied by the user. They render a schedule containing accessory and configured-fixture rows through Frappe's real route resolver, controllers, database and Jinja templates. Missing scope must return HTTP 200 with the schedule content and unavailable label, without an error message or a false stock summary. The extrusion-kit stock helper is also exercised with missing scope.

A separate real database test supplies stock in the selected warehouse, another company, another warehouse, a disabled warehouse and a group warehouse. Only the approved source counts. Seven on hand minus four reserved yields three available; two schedule lines requiring two each produce a combined shortage of one. A missing Bin in a valid scope yields zero, rather than unknown availability.

Results: **212 unit tests, 28 DOM tests and 10 installed-site regression tests passed**. Template checks parsed 35 templates, rendered the existing quote/configurator/export examples and checked 12 embedded scripts. Scoped Python checks reported no new lint diagnostics; Git whitespace checks passed. These checks use synthetic read-model fixtures, not a copy of Cloud data, and do not constitute a live Cloud browser test.

## Deployment

Deploy the updated application using the normal Frappe Cloud deployment process, then reload the fixture schedule. No extra data migration or Patch Log reset is required for this repair.

If the unavailable label remains, check that `Warehouse.warehouse_name` is `ilL-Stores`, its company is `ilLumenate Lighting`, and it is enabled and not a group. If the site has an explicit `ill_portal_stock_company` override, that value must identify the intended company. This local repair does not inspect or change Cloud configuration.
