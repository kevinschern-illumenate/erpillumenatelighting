# Webflow product page scripts

Custom code from the main ilLumenate Webflow site's Products template page, copied by the owner on
2026-11-06 as the starting point. One file per CMS JSON field the script reads. These run in the
browser on public pages and hold no keys or secrets.

The staging site (`staging-illumenate.webflow.io`) has no Site plan, so it cannot hold custom code.
Test changes on staging with a userscript extension (Tampermonkey) instead, then paste the final
versions into the main site's custom code when staging moves to main (plan section 10).

The JSON shapes the sync sends are in `docs/erpnext_spec_sheet_redesign_plan.md` (4.16, 4.19) and
`n8n_workflows/lib/ill_transform_to_webflow.js`.
