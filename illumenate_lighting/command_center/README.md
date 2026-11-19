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

## Manufacturing: production board

The Manufacturing step (`#mfg`) is the warehouse "Schedule Wizard" workbook, live. Its data comes from the app endpoint `illumenate_lighting.illumenate_lighting.api.production_board.get_board`, which is ordinary app code and not a Server Script, so it is deployed with the app. It is read-only and needs Command Center Viewer, Manufacturing User/Manager or System Manager. Dollar columns need Command Center Finance, Manufacturing Manager, Accounts Manager or System Manager; everyone else sees points only.

- Pipeline cards: Pend-Prod / In-Prod / Pend-Ship / Waiting for parts / Paint / Held, each with $, number of orders, points and average commission. Commission above the flag (22% by default) shows red.
- Shipped today and this month, available to ship, gap to the monthly goal with dollars needed per shipping day, on-time %.
- Due: past due, today, tomorrow (Monday on a Friday), this week.
- Capacity: workload, capacity per day (points per person per day × head count), days to complete, date clear, and a 22-workday burn-down that skips weekends and the holiday list.
- Order queue: 2C–6C runs, Loose, WR, FMC, Assy, points, hours, $ per point and floor notes. It can be filtered by status and sorted by ship date, $ per point or points.
- Waiting for parts: what's short after stock is handed out in ship-date order, the ETA from open purchase orders, and whether the order is going to miss its date.
- Shipped this month: delivery notes, on time or late, the reason, and on-time % by week.
- Sub-tabs for the rest of the workbook:
  - **Run rate & daily $:** orders received per workday over the last 30 workdays, with $0 / same-day / next-day / rush counts and the month and 30-day averages. Also shipped dollars per workday against the dollars needed per day.
  - **Monthly report:** this month and the next two. Rows are goal, shipped, scheduled, estimated run rate, at risk, expected releases, projection (with and without at-risk), % of goal and average commission.
  - **Releases & holds:** orders on Hold for Release / Confirmation, with Likely Ship Date, monthly totals, and release points and days using the release weights. Hold for Ship orders appear with days until their ship date.
  - **Proforma & will call:** open orders, and those completed this month.
  - **Paint:** orders with an open PO to the paint supplier group (set in settings) or marked Paint by hand. Shows PO, date sent, date due back and items.
- The previous work-order tables are in a collapsed "Work order clean-up" card at the bottom.
- **Material requests** sub-tab: Manufacture-type Material Requests (the Purchasing desk shows only Purchase ones), in lanes Draft → Needs work order → Building → Done (last 30 days). A request is "Building" once it has a work order (draft ones count), and "Done" when every linked work order is Completed; ERPNext's own "Manufactured" status only means work orders cover the quantity. Cards show the items, the sales order and the linked work orders with their status. The tab label carries the open count, red when one is past its needed date.

**Status rules:** the floor override on the Sales Order comes first. Then On Hold or a stopped WO means Held. All WOs complete means Pend-Ship. Any WO in process means In-Prod. Material short means Waiting for parts. Anything else is Pend-Prod.

**Ship date:** the Sales Order's Estimated Ship Date. If that's blank, the delivery date is used, shown with a `*`.

**Weights, capacity, head count, overtime, holiday list and monthly goal:** Desk → ilL-Production-Settings ("Weights & capacity" button on the page).

## Warehouse flow (v9)

The Manufacturing step now opens on a **Flow** tab. The production board's other tabs (Schedule board, Material requests, Run rate, Monthly report, Releases, Proforma, Paint) are unchanged and sit after a "Reports" label. The tab used last is remembered per browser. Flow tells the same open orders in ERPNext documents instead of workbook codes:

Sales Order → Work Order → pick materials → build → pick & ship → Delivery Note

- **Data:** the app endpoint `illumenate_lighting.illumenate_lighting.api.warehouse_flow.get_flow`. It is read-only and returns no money, so every viewer sees the same thing. Readers: Command Center Viewer, Manufacturing User/Manager, Stock User/Manager or System Manager.
- **Flow strip:** the document chain with a count at each step (open sales orders, orders with every build line covered, work orders ready to pick, in production, orders to pick & ship, delivery notes in the last 7 days). Each tile jumps to its section.
- **Your list:** one row per step that has something in it, most urgent first, with the ERPNext move that clears it: orders needing work orders, draft work orders to submit, work orders ready to pick, waiting for parts, in production, orders to pick & ship, draft delivery notes, holds, and clean-up. Rows filter the orders table or highlight a work order lane.
- **Sales orders → work orders:** how many orders with build lines (items with a BOM, from the line's BOM or the item's default BOM) are fully covered, partly covered or not covered, how many are stock only, and a bar of where every order sits. The table lists each order at its step with its work orders (coloured by lane), the build lines still missing one, and the next step.
- **Order step**, first match wins: On hold (hold reason, On Hold, a stopped work order, or the floor override "Held") → Needs work orders → Work orders in draft → Waiting for parts (floor override) → Building (a work order in process, or the "Paint" override) → Waiting for parts → Pick materials → Pick & ship.
- **Work orders** in lanes: Draft · Ready to pick · Waiting for parts · In production · Completed (last 14 days, or still on an open order) · Stopped (only shown when there is one). A work order whose sales order is closed or delivered is flagged.
- **Picking:** for production, required minus transferred (minus consumed with "skip material transfer"). For shipping, ordered minus the larger of delivered and picked, with product bundles expanded to their parts. Non-stock lines without parts and drop-ship lines are skipped. Stock outside work-in-progress warehouses goes first to work orders by ship date, then to orders ready to ship. "Short" means ERPNext stock is short after that, and short work orders get an ETA from open purchase orders. Quantities are shown as pieces (Ea, Nos, …) plus any other units (inches, feet).
- **Clean-up:** draft work orders, draft delivery notes and open pick lists tied to orders that are closed or delivered. They are listed in a collapsed card and not counted as work.
- **Shipping** now starts with the full pick list for orders ready to ship (one block per order, kit parts labelled), open pick lists and draft delivery notes on open orders, and what shipped in the last 7 days. The older timeline and "Can it go out?" table follow.
- The stepper's Manufacturing count switches to open work orders and lines needing one once the flow has loaded.

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

## Purchasing (v8)

The **Purchasing** step (`#purch`) is a purchasing desk. Its data comes from the app endpoint `illumenate_lighting.illumenate_lighting.api.purchasing_board.get_board` (ordinary app code, deployed with the app, like the production board). It refreshes on demand and when older than 2 minutes. If it fails, the page shows the older feed's shortage list (`D.purch`) with a note.

- **Flow strip** above the tabs: To order → Requests → Vendor quotes → POs → In transit → Received → Bills → Landed cost. Each tile has a count, dollars for money roles, and a red or amber dot when it holds a decision. Click a tile to open its tab. Under 700px it becomes a 2-column grid.
- **Tabs** (the last one used is remembered per browser):
  - **Overview:** the decisions (`to_order_late`, `reorder_breach`, `mr_unactioned`, `quote_expiring`, `rfq_no_reply`, `po_draft_old`, `po_not_sent`, `po_unconfirmed`, `po_overdue`, `po_will_miss`, `shipment_eta_passed`, `receipt_no_bill`, `bill_overdue`, `bill_not_in_qbo`, `needs_lcv`, `cost_variance`), each opening its tab and lane. Also what arrives in the next 14 days (late ones red), open PO value by supplier, and open PO value by month of ETA.
  - **To order:** the shortage table (multi-select "Draft one MR for selected"), items below their reorder level (with a suggested level and **Apply**), shortages that only exist if draft sales orders go ahead, and **Data gaps** (no supplier, lead time, reorder level, HTS code or origin; lead time can be set inline).
  - **Requests:** Material Request lanes (Draft · To quote · Quoted · Ordered · Receiving). **Request quotes** drafts an RFQ; **Order directly** drafts a PO.
  - **Vendor quotes:** RFQ and Supplier Quotation lanes (RFQ draft · Awaiting reply · Quoted · Expiring · Ordered · Expired / lost). **Enter quote** drafts a Supplier Quotation; **Accept → draft PO** drafts the PO. **Compare quotes** shows items with two or more live quotes, with the cheapest and fastest marked.
  - **Purchase orders:** lanes (Draft · Not sent · Awaiting confirmation · Confirmed / in production · In transit · Partly received · To bill · On hold; Done behind a toggle) or a table sorted by ETA. The card shows the lead time and its source (`28d · quote`) and the ETA: red when overdue, amber when it arrives after the sales order needs it. The side sheet edits vendor status, sent and confirmed dates, ack #, lead time, ETA, promised ship date, freight mode and notes (`update_po_tracking`), plus per-line lead time and ETA (`update_po_line_tracking`). It also has Email PO (opens the desk PO), Create shipment, Draft receipt, Draft bill and + Add to agenda.
  - **Shipments:** `ilL-Inbound-Shipment` lanes (Planned · Moving · At customs · Arriving · Delivered, costs open · Costs final). Cards show the mode, tracking, ETA/ATA, POs, goods value, an estimated vs actual cost bar by cost type, and landed %. The sheet edits the header and cost lines (`update_shipment`) and drafts a receipt or a Landed Cost Voucher. Without the Finance role, cost lines are read-only because their amounts arrive blank.
  - **Receipts:** received goods with billed %, shipment and an LCV chip (Landed / Needs LCV / No inbound costs), plus **Draft bill**.
  - **Bills:** Purchase Invoice lanes (Draft · Unpaid · Overdue · Partly paid · Paid in the last 30 days), the QuickBooks chip (`custom_qbo_id`), and a 3-way match chip (PO vs receipt vs bill; over 2% or $50 is flagged).
  - **Landed cost:** what still needs a voucher (with missing bills, e.g. "Duty bill not in yet") and **Draft LCV**; recent vouchers; landed cost by item (purchase rate, landed rate, uplift %, 12-month average; Copy as text); and the **landed cost in stock** total for the QuickBooks true-up.
  - **Suppliers:** scorecard with open POs and $, quoted vs actual lead time, on-time %, last PO, and the supplier's default lead time (editable).
- **Lead time** precedence (`purchasing.lead_time`): PO line → PO header → latest live Supplier Quotation for the item and supplier → Supplier default → Item `lead_time_days` → item-group default in ilL-Purchasing-Settings (walking up the group tree) → none (listed in Data gaps).
- **ETA** precedence: line `ill_eta` → header `ill_eta` → Required By (`schedule_date`) → order date + lead time. A blank Required By is allowed (`purchase_order.allow_blank_schedule_date`). The production board's "Waiting for parts" uses the same `ill_eta`, so both boards agree.
- **Every button creates a draft** and says so. Submitting happens in the desk, which also runs ERPNext's validations (Decision D5). The Command Center never submits or cancels.
- **Tracking fields** (patch `add_purchasing_tracking_fields`): Purchase Order `ill_vendor_status`, `ill_sent_on`, `ill_vendor_confirmed_on`, `ill_vendor_order_no`, `ill_est_lead_time_days`, `ill_promised_ship_date`, `ill_eta`, `ill_freight_mode`, `ill_purchasing_notes` (editable after submit). Purchase Order Item: lead time and ETA. Supplier: default lead time, freight mode, purchasing email, role (goods vendor / forwarder / broker / carrier). Customs Tariff Number: duty %, additional tariff %, rates checked on, notes.
- **Hooks** (`api/purchasing.py`, all best-effort: a failure goes to Error Log as "Purchasing hook failed", never blocks a save):
  - A new PO is pre-filled with lead time, ETA, freight mode and "Not sent", and gets an ETA on submit if it has none.
  - An email sent from a submitted PO marks it Sent.
  - A full receipt marks the PO Delivered and joins the PO's open shipment.
  - A submitted bill linked on a shipment cost line fills its actual amount.
  - A shipment moves its POs' vendor status and ETA forward, never back.
- **Settings:** Desk → **ilL-Purchasing-Settings** ("Settings" on the page) holds the company and warehouse for Draft MR, default lead times by item group (seeded: extrusions 10, tape/neon/sheet 35, power and controls 28), safety days (3), warning windows, and per-cost-type landed cost rules (included or expensed, account, allocation basis, estimate %).
- **Roles:** reading needs Command Center Viewer, Purchase Manager/User, Stock Manager or Accounts Manager/User. Dollars need Command Center Finance, Purchase Manager, Accounts Manager or System Manager. Buttons need Command Center Editor, Purchase Manager or Purchase User, plus the ERPNext permission on the document. `command_center_sync.py` grants Viewer read and Editor read/write/create on `ilL-Inbound-Shipment`, and Viewer read on the settings.

### Landed cost, step by step (for Charlotte)

1. **Estimate.** Creating a shipment seeds its cost lines from settings: freight as a % of goods value, and duty and tariffs from each item's HTS code (`ill_duty_rate_pct` + `ill_additional_tariff_pct`). The board shows the estimated landed % before anything arrives.
2. **Receive.** Draft the Purchase Receipt from the board and submit it in the desk. Stock is valued at the PO rate.
3. **Bills.** The vendor's bill is a Purchase Invoice against the PO or receipt. Forwarder and broker bills use the service items (FREIGHT-IN, DUTY, ...) whose expense account is the "included in valuation" account. Link each bill on the shipment's cost line; the actual amount fills in.
4. **Land it.** When every included cost has its bill (or you tick "allow estimates"), **Draft landed cost voucher** builds the LCV: one charge row per included cost type, with the allocation basis from settings. It refuses unsubmitted receipts, lines without an account, and mixed bases (one basis per voucher; use Manual). Check the distribution and submit it in the desk. ERPNext revalues the received items and reposts consumption (a Repost Item Valuation job, so allow a short delay).
5. **QuickBooks (Decision D1, option A).** Bills still go to QBO as today. The LCV is not sent. True up QBO inventory periodically with the "landed cost in stock" figure on the Landed cost tab.

## Catalog tab (v8)

The **Catalog** top tab embeds the ERPNext Catalog Builder (`/catalog-builder?embed=1`) in a same-origin iframe. Session, CSRF, permission gate and localStorage drafts are the builder's own. There is **no new sync path**: it is the same Check → Import, endpoints, permissions and `ilL-Catalog-Import` receipts.

- **Who sees it:** ilL Catalog Publisher or System Manager (gateway `config` → `catalog.allowed`, read with a cheap `lite` config call at startup). The builder page re-checks server-side, so a Viewer without the role gets 403 there too. Refresh re-reads access.
- **Kept alive:** the iframe lives in `#cccatalog` after `#ccmain`. It is created on the first visit and only hidden on other tabs, so the grid, undo history and a passing Check survive switching to Inbox and back.
- **Toolbar:** Open full screen ↗, Import history, Reload builder.
- **Messages** (same origin only, from the builder's own frame): `ready`, `dirty` (amber dot on the tab, and a leave-page guard while dirty), and `imported` (toast with the receipt, Workbench counts refreshed). The page sends `open` (records to load as-is through the builder's `records` endpoint) and `new` (a blank record of a doctype), queued until the builder says `ready`. `/catalog-builder?open=<doctype>:<name>` does the same in full screen.
- Before announcing the tab, run the production smoke in `docs/CATALOG_BUILDER_ROLLOUT.md`.

## ilLumenate Workbench (v8)

The Workbench has two areas: **Pipeline** (`#wb/~pipeline`, the stage cards as before) and **ilLumenate** (`#wb/~ill`, every app doctype grouped like the desk workspace). `#wb` opens the area used last.

- **Groups** (`ILL_GROUPS` in the gateway): Product templates, Specifications, Attributes, Relationships & maps, Submittal mappings, Configured products, Projects & design, Dealer portal, Purchasing & inbound, Catalog & Webflow publishing, Product finder, Meetings, and Logs & system. Logs & system is System Manager only. A **Settings** card links the single doctypes in the desk. A filter box searches all of them. Counts load one call per group, when its card scrolls into view.
- A doctype can be in a pipeline section and a group (for example ilL-Project). Lists, saved views and counts are shared. The breadcrumb and sibling buttons follow the area you came from.
- **Per-doctype behaviour, all in the gateway** (no doctype JSON changed):
  - Masters with an `is_active` Check show status **Active / Inactive**, with a one-click Activate / Deactivate in the sheet.
  - Portal doctypes keep their status in `state`.
  - Doctypes with no status get no status filter or mix.
  - Columns come from meta (title + `in_list_view` fields) unless listed.
  - Child tables show read-only in the sheet (first 25 rows).
  - Templates, specs, maps, submittal mappings and Item are **created in the Catalog Builder** (`+ New` opens the Catalog tab), and their sheet has **Edit in Catalog Builder**.
  - Generated and audit records (configured products, receipts, snapshots, portal events and messages, publish/export jobs, sync logs) are **read-only**.
  - `prompt`-named doctypes (LED Package) ask for a name.
  - Fields above permlevel 0 are never offered (Frappe would silently drop the edit).
  - Session tokens and singles holding credentials are excluded.
- `tests/portal_unit/test_cc_workbench_registry.py` fails when an app doctype is in no group, SETTINGS or EXCLUDED.

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
- `cc_api.py` (the older feed) is still not in this repo. The pipeline lanes no longer depend on it, but the ticket list (`D.tk`), quotes, orders and finance data still come from it. Purchasing now comes from `purchasing_board` (money gated by role); `D.purch` / `D.lowstock` are only the fallback. Once the board is trusted, drop the purchasing money from `cc_api.py`.
- Purchasing writes (drafts, tracking, shipments, landed cost vouchers) have never run against real ERPNext. Do one full cycle on staging with Charlotte first: MR → RFQ → SQ → PO → email → shipment → PR → vendor bill + broker bill → LCV.
- "Needs a reply" uses the ticket status (Helpdesk sets Open when the customer writes last), not the last message itself.
- Writes have never run against real ERPNext. First test with a throwaway Task.

## Tests (no ERPNext needed)

- `tests/check_gateway_sandbox.py`: compiles the gateway under RestrictedPython and runs every action against a fake `frappe`, emulating both the v16 and v15 aggregate rules (`pip install RestrictedPython`, then `python illumenate_lighting/command_center/tests/check_gateway_sandbox.py`). Named `check_*` so pytest/unittest never collect it.
- `tests/portal_unit/test_warehouse_flow.py`: work order lanes, coverage, pick quantities, order steps and the stock hand-out for the flow endpoint.
- `tests/smoke.js`: loads `cc.js` in jsdom against a mock gateway and walks every page (`npm i jsdom`, then `node illumenate_lighting/command_center/tests/smoke.js`).
