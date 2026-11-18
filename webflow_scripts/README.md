# Webflow product page scripts

Custom code from the main ilLumenate Webflow site's Products template page, copied by the owner on
2026-11-06 as the starting point. One file per CMS JSON field the script reads. These run in the
browser on public pages and hold no keys or secrets.

The staging site (`staging-illumenate.webflow.io`) has no Site plan, so it cannot hold custom code.
Test changes on staging with a userscript extension (Tampermonkey) instead, then paste the final
versions into the main site's custom code when staging moves to main (plan section 10).

The JSON shapes the sync sends are in `docs/erpnext_spec_sheet_redesign_plan.md` (4.16, 4.19) and
`n8n_workflows/lib/ill_transform_to_webflow.js`.

## Testing on staging with Tampermonkey

1. Install Tampermonkey (Chrome Web Store). In Chrome, Extensions > Tampermonkey > Details, turn on
   **Allow User Scripts**.
2. Tampermonkey > Create a new script, replace everything with `staging.user.js`, save.
3. Open a product page on `staging-illumenate.webflow.io` (e.g. `/products/kit-ra01`).

The scripts read CMS data from hidden elements (the ids are listed at the top of
`staging.user.js`). On the main site they come from Code Embeds; on staging (no Site plan) they
must be Designer text elements bound to the same CMS field with the same id, hidden.

After editing any `.html` file here, rebuild: `python3 webflow_scripts/build_userscript.py`.

The staging site kept the main site's Code Embeds when it was duplicated, and they still run
(with the old code). `staging.user.js` lets its own copies register first and then ignores the
old copies' DOMContentLoaded listeners and Finsweet callbacks, so each script runs once. It relies
on the page's own Finsweet and Swiper (no @require). `window.__illStaging.ignored` in the console
shows how many old registrations were ignored.

## Configured spec sheet

`configured-spec-sheet.html` runs the Configure Spec Sheet popup: it closes the popup and makes
Generate download the current spec sheet filled in and highlighted (plan 4.20). It replaces
`extrusion-kit-configured-spec.html` (the old submittal script, kept for reference).

## 206 Lighting

`206/` holds the 206 site scripts the illumenate configured spec sheet copies (owner, 2026-11-06):
the code builder (sets `window.CurrentConfigSelection`) and the configure/highlight script
(fills the generated spec sheet and highlights the selected options). Reference only; not part of
the staging userscript.
