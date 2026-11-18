# ilLumenate Command Center (Frappe Cloud web page + Server Scripts)

Source for the Command Center at `/command-center`. These files are **pasted into the site**, they are not part of the `illumenate_lighting` app and are not deployed by Frappe Cloud's bench.

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

## Deploy (about 15 minutes, in this order)

1. **Back up.** In the Web Page, copy the current JavaScript and CSS into `cc.v3.js` / `cc.v3.css` (they are not in this repo).
2. **Roles.** Role list → create `Command Center Editor` and `Command Center Finance`. User → Roles: Finance for charlotte@, jay@, kevins@; Editor for whoever may change records (suggested kevins@, jay@, ryanb@, reigine@). Viewer already exists.
3. **Server Script** → New: `ilL Command Center Gateway`, type API, method `ill_cc_gateway`, Allow Guest off. Paste `ss/cc_gateway.py`. Save. If Save errors, send me the message: it will be a sandbox difference on your Frappe version.
4. **Web Page** `illumenate-command-center`: replace JavaScript with `page/cc.js` and CSS with `page/cc.css`. Leave `cc.html`.
5. **Test as Kevin:** Workbench → open a Task → change a harmless field → Save → the "Command Center:" comment appears in the record's ERPNext timeline. Then Executive (numbers load, cards link through) and Review (arrow keys, Print / PDF).
6. **Viewer-only user:** no `+ New`, no Save. **User without Finance:** Finance locked in Workbench; Finance tiles locked on Executive.
7. **User with no Viewer role:** lock screen.

If the Workbench, Executive or Review tabs say the gateway is missing, step 3 was skipped. The rest of the page keeps working.

## Known limits

- **The older `#finance` tab and the finance figures on the Sales pipeline page come from the existing `ill_command_center` script, which gives every Viewer the finance data.** The Finance role only gates the gateway-backed pages. Closing that gap means adding the same role check inside `cc_api.py`.
- Saved views are per browser, not stored in ERPNext.
- "Decisions" status values (e.g. `To Deliver and Bill`, `Pending`) and field names (`valid_till`, `exp_end_date`) are standard ERPNext; if a count shows missing, that doctype/field differs on the site and the signal is skipped, not an error.
- Custom `ilL-*` doctypes only list `status`, `owner`, `creation` until their useful fields are added to `ALLOWED` in `cc_gateway.py`.
- Writes have never run against real ERPNext. First test with a throwaway Task.

## Tests (no ERPNext needed)

- `tests/gateway_sandbox_test.py`: compiles the gateway under RestrictedPython and runs every action against a fake `frappe` (`pip install RestrictedPython`).
- `tests/smoke.js`: loads `cc.js` in jsdom against a mock gateway and walks every page (`npm i jsdom`, then `node tests/smoke.js`).
