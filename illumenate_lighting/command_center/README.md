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

## Meeting agenda (v6)

The **Agenda** tab replaces the Google Doc agenda for the weekly meeting.

- **Stored in ERPNext**, in two app doctypes: `ilL-Meeting-Agenda` (one per meeting: title, date, Open/Closed, notes) and `ilL-Meeting-Agenda-Item` (title, details, who brings it, status, outcome, order, optional linked record). Everyone sees the same agenda, and the page re-reads it every 30 seconds while it is open (or immediately on Refresh).
- **Add items** as free text, or with **+ Add from ERPNext**. Its *Suggested* tab lists overdue to-dos and tasks, sales orders at risk, quotes expiring this week and tickets waiting over 2 days. *Search all records* covers every doctype in the Workbench (to-dos, tasks, sales orders, quotes, POs, tickets, ...). Each Workbench record sheet also has **+ Add to agenda**, which adds the record to the next open meeting.
- Linked items show the record's **live status**, value and date, plus a *Details* button that opens the Workbench sheet (to edit the record mid-meeting).
- In the meeting: tick **Discussed**, type the **outcome**, and reorder with ↑ ↓. When a linked item is marked discussed, a "Command Center: discussed at the <date> meeting: <outcome>" comment goes on the linked record's timeline. Adding a record to an agenda writes a comment there too.
- **+ To-do** next to each outcome turns it into ERPNext ToDos: one per owner (defaults to whoever brings the item), due a week after the meeting by default. Each is linked to the item's record (or to the agenda item if it has none) and tagged `[meeting]`, so it appears on the Tasks page under source "meeting". The item lists its to-dos with their live status, and they're included in Copy as text and the printout. Editors only, like every other change.
- **+ New meeting** defaults to a week after the last one and can carry its still-Open items over (the old copies are marked "Carried over").
- **Copy as text** (for email/chat) and **Print / PDF**. Meeting mode hides items linked to email-derived to-dos.
- Permissions: Viewers read, Editors add and change. `command_center_sync.py` grants the Command Center roles on both doctypes the first time (Custom DocPerm). After that the desk's Role Permissions Manager is the authority. Removing an agenda item is the only delete the gateway does, and it never touches the linked record.

## Pipeline restructure (v7, Nov 18 2026)

The sales pipeline now mirrors the dealer portal: **Overview → Design → Quotes → Sales orders → Purchasing → Manufacturing → Shipping → Service**. One `STAGES` array in `cc.js` drives the stepper, the router and the tab highlight, so reordering is a one-line change. Old `#requests` links redirect to `#pipeline`.

- **Data:** the stage lanes come from the gateway's `stages` action (one permission-aware call), not from `cc_api.py`. It returns projects, fixture schedules (with line counts), drawing requests and reviews, quote requests and offers, order intakes, account requests, and the project/schedule/quote/order links on recent help desk tickets. If it fails, each stage shows the older feed's request lane and a note.
- **One stage per schedule:** the fixture schedule's status is the spine. Furthest along wins: an order request, sales order or ORDER_REQUESTED/ORDERED → Sales orders; an active quote request, issued/accepted offer or QUOTED → Quotes; otherwise Design. Earlier steps show as chips on the schedule page.
- **Design** (`#design`): board of fixture schedules (Drafting, Ready for quote, Drawing in progress, Waiting on customer, Review), one card per schedule with its project, dealer, architect/lighting designer/GC, version, lock and line count. General drawing and document requests list with SLA, assignee and age. Design-type tickets moved here from Quotes. `#design/<schedule>` shows the project, the lines (read-only), drawing requests, reviews and the quote/order steps it led to.
- **Quotes:** quote request lanes (Requested, Under review, Information needed, Issued) plus a "Dealer responded" lane for accepted, declined and revision-requested offers. Accepted offers carry a "Continues in Sales orders" chip. Quotation tickets and the "Quotes waiting on dealers" table stay.
- **Sales orders:** order request (intake) lanes above the open orders, and drawing requests tied to a sales order (manufacturing sign-off). Each order page lists its intakes and drawing requests.
- **Service** is the last pipeline step (no longer a top tab) and starts with the **Customer requests** lane: dealer applications and address, contact, profile and company changes (`ilL-Account-Request`).
- **Inbox** is a help desk portal: all tickets with filters (status, type, owner, linked or not) and sort; a *Needs a reply* queue (Open tickets, i.e. the customer wrote last); a *Routing* view for unassigned or untyped tickets with one-click type and owner. *Manage* opens a ticket sheet to reassign, link or unlink a quotation, sales order, project or fixture schedule, and change status, priority, type and team. Every ticket shows its pipeline stage. Replies are written in Helpdesk (*Reply in Helpdesk* opens `/helpdesk/tickets/<name>`).
- **Writes:** reassigning and linking need the Command Center Editor role. Field changes go through the gateway's `save` and assignments through its new `assign` action (an open ToDo per owner, as the desk does; unassigning cancels that person's open ToDo). Both leave a "Command Center:" comment on the record. Drawing and quote requests can be reassigned from their lanes (their `assigned_to` is editable); order intakes and account requests can't, since those fields are read-only on the doctype.
- **Gateway:** sections are now in pipeline order with a new **Design** section (ilL-Project, ilL-Project-Fixture-Schedule, ilL-Document-Request, ilL-Drawing-Review); the Requests section is gone (each request doctype sits in its stage). Portal doctypes that store their status in `state` (quote requests, offers, intakes, order changes, account requests) or `decision` (drawing reviews) are read, filtered, sorted and grouped through that field, exposed to the page as `status`. Executive "Decisions this week" adds drawings past SLA, quote and order requests waiting on us, and pending account requests.

## Fixes made while building this (versus the v4 files)

1. **`cc_gateway.py` would not save as a Server Script.** Frappe's sandbox (RestrictedPython) rejects names starting with `_` (`_gate`, `_roles`, ...). It also cannot see top-level helpers/constants from inside functions, and does not expose `frappe.get_roles` / `frappe.has_permission`. The script is now a single `main()` with closures, roles come from the `Has Role` table, permissions from `Document.has_permission()`.
2. Row totals respect the user's permissions and the search box (v4 counted all rows).
3. Workbench landing makes one `counts` call instead of 18 `list` calls.
4. Frappe v16: aggregates in get_list use the dict form (`{"COUNT": "*"}`), with the v15 string form as a fallback.

## Deploy

Deploys are automatic: merge to the default branch and deploy on Frappe Cloud. `illumenate_lighting/command_center_sync.py` copies these files into the Web Page and Server Script after migrate. Don't edit the records in the desk, because the next deploy overwrites them. The previous page JS/CSS is attached to the Web Page as private `cc.backup-<timestamp>` files after each change. Problems appear in Error Log as 'Command Center sync failed: …'. Each deploy's migrate output has one `Command Center sync: …` line per step (roles, Server Script, Web Page) saying what changed. If a backup is refused (e.g. System Settings → Allowed File Extensions excludes JS/CSS), the page is still updated and the old code stays in the Web Page's Version history.

## Known limits

- **The older `#finance` tab and the finance figures on the Sales pipeline page come from the existing `ill_command_center` script, which gives every Viewer the finance data.** The Finance role only gates the gateway-backed pages. Closing that gap means adding the same role check inside `cc_api.py`.
- Saved views are per browser, not stored in ERPNext.
- "Decisions" status values (e.g. `To Deliver and Bill`, `Pending`) and field names (`valid_till`, `exp_end_date`) are standard ERPNext; if a count shows missing, that doctype/field differs on the site and the signal is skipped, not an error.
- `cc_api.py` (the older feed) is still not in this repo. The pipeline lanes no longer depend on it, but the ticket list (`D.tk`), quotes, orders, purchasing and finance data still come from it.
- "Needs a reply" uses the ticket status (Helpdesk sets Open when the customer writes last), not the last message itself.
- Writes have never run against real ERPNext. First test with a throwaway Task.

## Tests (no ERPNext needed)

- `tests/check_gateway_sandbox.py`: compiles the gateway under RestrictedPython and runs every action against a fake `frappe`, emulating both the v16 and v15 aggregate rules (`pip install RestrictedPython`, then `python illumenate_lighting/command_center/tests/check_gateway_sandbox.py`). Named `check_*` so pytest/unittest never collect it.
- `tests/smoke.js`: loads `cc.js` in jsdom against a mock gateway and walks every page (`npm i jsdom`, then `node illumenate_lighting/command_center/tests/smoke.js`).
