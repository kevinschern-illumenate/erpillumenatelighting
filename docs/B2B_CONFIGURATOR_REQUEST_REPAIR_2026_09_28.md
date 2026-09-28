# Configurator request validation repair - September 28, 2026

The project linear configurator sent `override_max_run_ft: ""` when the override checkbox was off. Frappe v16 validates whitelisted parameter annotations before entering the function. A `float | None` parameter therefore rejected the form's empty string before the existing blank-value normalization could run.

Earlier DOM tests captured JavaScript request objects but did not pass their form-encoded values through Frappe's request validator. The installed-site tests covered migrations, page rendering and stock scope, but not this calculation request. The new tests cover that missing boundary.

## Corrections

- Linear, tape and neon coordinator requests omit unused numeric overrides. Active overrides must be finite and positive. The embedded fixture configurator now rejects malformed, infinite, zero and negative overrides instead of silently ignoring them or partially parsing strings such as `12feet`.
- Six public override parameters in the linear, tape, neon and Webflow APIs accept form strings as well as numbers and null, allowing domain normalization to run. Internal calculation signatures remain numeric.
- Two optional delivered-output parameters allow an empty form selection to reach the existing structured validation response.
- Four legacy schedule-save endpoints normalize optional line indices before any write. Blank means a new line, zero remains a valid index, and fractional, negative and non-finite inputs are rejected. The optional Webflow session quantity follows the same rule with a minimum of one.
- Webflow no longer silently discards an invalid run override. It reports a validation error instead.
- The database audit found two additional invalid Finish queries: cascading configurator options and saved fixture details requested `display_name`, but the installed DocType defines `finish_name`. Both now use the installed schema.
- Both CI workflows now run on pushes to `main` as well as `develop`. The v16 job includes the new request-validation suite.

## Verification

The isolated Bench uses the exact Frappe, ERPNext, HRMS, CRM and Print Designer commits supplied by the user, with Python 3.14.2. The new installed-site suite submits 68 form-encoded requests through `frappe.handler.execute_cmd`, including whitelist enforcement and Frappe's actual argument validation. It checks absent, blank, numeric and invalid optional values, and queries seeded Finish/template/fixture records. A source-driven scan also checks all optional numeric whitelist parameters for blank-form compatibility.

The existing physical-column audit now includes eight configurator/API modules in addition to portal services and page controllers. It checks literal field selections against the real installed database. Dynamic SQL and site-specific engineering data still require runtime coverage; this audit does not claim to validate every possible product configuration.

Final results: **213 unit tests, 30 DOM tests, seven installed-site request tests (68 dispatched requests), and 10 installed-site migration/portal/schema regressions passed**. Both complete migration passes succeeded. Template checks parsed 35 templates and checked 12 embedded scripts. The new request tests deliberately use missing engineering templates for calculation requests so that reaching a normal domain validation response is asserted without creating production artifacts. They test the request contract, not an approved BOM for the site's reference products.

## Deployment and the earlier stock traceback

These changes require deployment of the updated application code and browser assets. Running Migrate on an older application checkout does not load these fixes.

The stock repair was verified on GitHub `main` at `c5ba78109771b5bd5e5a8e3462ec0d4779c2ac68`. The later stock traceback still contained the pre-fix `frappe.throw` at `pricing_utils.py:197`, matching the parent revision. That establishes that the traceback came from the earlier implementation; it does not establish whether Cloud had an older deployment, stale serving processes, or whether the copied error predated deployment. Confirm the active app revision on the site's bench after updating, then reload the browser to load the new configurator JavaScript. The current request repair must be included in a newer commit than `c5ba781`.

No schema patch, inventory adjustment, transaction rewrite or Patch Log reset is part of this repair. Cloud data and deployment state were not modified locally.
