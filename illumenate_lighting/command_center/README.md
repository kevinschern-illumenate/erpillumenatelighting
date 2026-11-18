# ilLumenate Command Center (Frappe Cloud web page + Server Scripts)

Source for the Command Center at `/command-center`, kept in `illumenate_lighting/command_center/`. The page and gateway live in database records; `illumenate_lighting/command_center_sync.py` copies these files into them on every `bench migrate` (see Deploy).

| File | Where it goes in ERPNext |
|---|---|
| `page/cc.js` | Web Page `illumenate-command-center` → JavaScript |
| `page/cc.css` | Web Page `illumenate-command-center` → CSS (Style) |
| `ss/cc_gateway.py` | Server Script `ilL Command Center Gateway` (API, method `ill_cc_gateway`, Allow Guest **off**) |

Not in this folder: `cc.html` (unchanged, still what is live) and `ss/cc_api.py` (the existing read-only "ilL Command Center API" script, method `ill_command_center`). Keep both as they are on the site.

## What v5 adds (everything in the v4 plan, Phases 1 to 4)

- **Workbench** (Phases 1-2): one card per stage; per doctype browse, search, sort, status mix, side sheet with edit, `+ New` (drafts only).
- **Executive** tab (Phase 3): KPI row, pipeline value by stage, break-even, "Decisions this week" cards (late orders/POs/material requests, expiring quotes, stale tickets, overdue tasks, draft work orders, overdue invoices) that link into the Workbench with the status pre-selected, ticket age, this-week note, recent changes. Finance tiles stay hidden until the gateway confirms the user has the Finance role.
- **Review** tab (Phase 4): Tuesday walk-through. Overview of every active project, then one page per project (overdue, due this week, no owner, blocked, team load, recent changes, notes). Arrow keys move between projects; tasks open the edit sheet; "Print / PDF" prints every project one per page.
- **Saved views** (Phase 4): name and reuse filters on the Tasks list and on every Workbench list. Stored in the browser (localStorage) under the signed-in user, so they do not follow someone to another computer.
- **Activity feed** (Phase 4): built from the "Command Center:" comments the gateway writes; shown on Executive, per project on Review, and per record in the Workbench sheet. People only see changes to records they can read.

## Fixes made while building this (versus the v4 files)

1. **`cc_gateway.py` would not save as a Server Script.** Frappe's sandbox (RestrictedPython) rejects names starting with `_` (`_gate`, `_roles`, ...). It also cannot see top-level helpers/constants from inside functions, and does not expose `frappe.get_roles` / `frappe.has_permission`. The script is now a single `main()` with closures, roles come from the `Has Role` table, permissions from `Document.has_permission()`.
2. Row totals respect the user's permissions and the search box (v4 counted all rows).
3. Workbench landing makes one `counts` call instead of 18 `list` calls.
4. Frappe v16: aggregates in get_list use the dict form (`{"COUNT": "*"}`), with the v15 string form as a fallback.

## Deploy

Deploys are automatic: merge to the default branch and deploy on Frappe Cloud. `illumenate_lighting/command_center_sync.py` copies these files into the Web Page and Server Script after migrate. Don't edit the records in the desk, because the next deploy overwrites them. The previous page JS/CSS is attached to the Web Page as private `cc.backup-<timestamp>` files after each change. Problems appear in Error Log as 'Command Center sync failed: …'.

## Known limits

- **The older `#finance` tab and the finance figures on the Sales pipeline page come from the existing `ill_command_center` script, which gives every Viewer the finance data.** The Finance role only gates the gateway-backed pages. Closing that gap means adding the same role check inside `cc_api.py`.
- Saved views are per browser, not stored in ERPNext.
- "Decisions" status values (e.g. `To Deliver and Bill`, `Pending`) and field names (`valid_till`, `exp_end_date`) are standard ERPNext; if a count shows missing, that doctype/field differs on the site and the signal is skipped, not an error.
- Custom `ilL-*` doctypes only list `status`, `owner`, `creation` until their useful fields are added to `ALLOWED` in `cc_gateway.py`.
- Writes have never run against real ERPNext. First test with a throwaway Task.

## Tests (no ERPNext needed)

- `tests/check_gateway_sandbox.py`: compiles the gateway under RestrictedPython and runs every action against a fake `frappe`, emulating both the v16 and v15 aggregate rules (`pip install RestrictedPython`, then `python illumenate_lighting/command_center/tests/check_gateway_sandbox.py`). Named `check_*` so pytest/unittest never collect it.
- `tests/smoke.js`: loads `cc.js` in jsdom against a mock gateway and walks every page (`npm i jsdom`, then `node illumenate_lighting/command_center/tests/smoke.js`).
