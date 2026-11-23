# Module 05: Manufacturing

**Audience:** production lead, floor staff, operations, owner. **Length:** 90 minutes.
**Roles used:** Manufacturing User / Manager, Stock User, Command Center Viewer / Editor / Finance, ilL Operations.

## Purpose

Trainees can follow an approved order through work orders, picking materials, building and completing, using the Command Center **Flow** tab as their daily to-do list and the production board reports for planning.

## Where to go

| What | Where |
|---|---|
| Manufacturing stage (opens on Flow) | `/command-center#mfg` |
| Work orders | `/app/work-order` (+ New work order) |
| Manufacture material requests | `/app/material-request?material_request_type=Manufacture` |
| BOMs | `/app/bom` |
| Production plans | `/app/production-plan` |
| Stock entries | `/app/stock-entry` |
| Production settings (weights, capacity, goals) | `/app/ill-production-settings` ("Weights & capacity" on the board) |

The chain this module teaches:

**Sales Order → Work Order → pick materials → build → pick & ship → Delivery Note**

---

### Lesson 5.1: From an approved order to work orders

**Objective:** know which work orders are created for you and which you create.

- Configured products already have their **Item** and a submitted **BOM** from the moment they were configured; the BOM is pinned to the order line.
- **On SO submit, draft work orders are created automatically** for **linear fixtures** and linear-fixture groups: one per line (one per run for groups; one per light engine for fixtures shipped in pieces), with the pinned BOM and a build traveler in the remarks.
- **Tape / neon and LED sheet lines get no automatic work order.** Staff create those (+ New work order, or the SO's manufacturing actions).
- Errors don't block the order: they go to the Error Log as "Manufacturing Generation Errors for <SO>" with an orange alert. Check it.
- **Actions → Generate Item/BOM/WO** on a submitted SO re-runs generation for configured rows.
- Guards:
  - **Request for Raw Materials** is refused if a line's pinned BOM isn't the item's default; use a Production Plan.
  - A Production Plan always uses the pinned BOM and can't create a second work order for a line that has one. Use plans for materials only.

**SS-05-01** · Submitted SO with its auto-created draft work orders in Connections
**URL:** `/app/sales-order/<name>` · **Role:** Manufacturing Manager

**SS-05-02** · Draft work order: pinned BOM, sales order item, traveler in remarks
**URL:** `/app/work-order/<draft>`

**SS-05-03** · Error Log entry "Manufacturing Generation Errors for …" (local instance)
**URL:** `/app/error-log`

**SS-05-04** · Actions → Generate Item/BOM/WO menu on a submitted SO

---

### Lesson 5.2: The Flow tab: your daily list

**Objective:** work from the Flow tab every morning.

- **Flow strip:** open sales orders → orders with every build line covered → work orders ready to pick → in production → orders to pick & ship → delivery notes (last 7 days). Each tile jumps to its section.
- **Your list:** one row per step that has work, most urgent first, with the ERPNext move that clears it:
  - orders needing work orders
  - draft work orders to submit
  - work orders ready to pick
  - waiting for parts
  - in production
  - orders to pick & ship
  - draft delivery notes
  - holds, clean-up
- **Sales orders → work orders:** how many orders are fully, partly or not covered, how many are stock only, and the order table with each order's step and next move.
- **Order step**, first match wins: On hold → Needs work orders → Work orders in draft → Waiting for parts (override) → Building → Waiting for parts → Pick materials → Pick & ship.
- **Work order lanes:** Draft · Ready to pick · Waiting for parts · In production · Completed (14 days) · Stopped. A work order whose order is closed or delivered is flagged.
- **Picking quantities:** required minus transferred. Stock goes to work orders by ship date first. "Short" means short after that hand-out; short work orders show an ETA from open POs.
- **Clean-up card:** draft work orders, draft delivery notes and open pick lists on closed or delivered orders. Not counted as work.
- Clicking any document opens the side sheet (Ctrl/⌘-click for the desk). Shows no money; every viewer sees the same.

**SS-05-05** · Flow tab, full page
**URL:** `/command-center#mfg` (Flow) · **Role:** Manufacturing User
**Highlight:** flow strip; Your list; coverage bar

**SS-05-06** · Work order lanes with a flagged work order
**Highlight:** Ready to pick lane; a short work order with its ETA

**SS-05-07** · Clean-up card expanded

---

### Lesson 5.3: Submitting, picking, building, completing

**Objective:** run a work order through ERPNext correctly.

1. **Submit the work order** (desk). Blocked if a required-for-manufacturing drawing isn't approved (Module 02, Lesson 2.5).
2. **Pick materials:** print the **ilL Work Order Traveler**; make a **Material Transfer for Manufacture** stock entry. The order moves to **In-Prod**.
3. **Build** using the traveler: build specs, cut list per segment with done boxes, materials with pulled boxes, six-point QC checklist, built-by and QC sign-off.
4. **QC fields** on the work order: Functional Test Pass/Fail, Serial Number, Test Notes.
5. **Finish:** a **Manufacture** stock entry completes the work order. When all of an order's work orders are complete it moves to **Pend-Ship** → Module 06.

- Planned start and expected delivery can be edited after submit (desk or side sheet).
- The Flow refreshes after any save from the Command Center.

**SS-05-08** · Work order traveler print preview
**URL:** `/app/work-order/<name>` → Print → ilL Work Order Traveler
**Highlight:** cut list; QC checklist; sign-off boxes

**SS-05-09** · Work order "Start" → Material Transfer for Manufacture stock entry
**URL:** `/app/stock-entry/new?...`

**SS-05-10** · Work order QC fields filled in

**SS-05-11** · (pair) Work order "Finish" → Manufacture entry; WO status Completed

**DATA-05-01** · Work orders for our job's SO with status and dates
**API:** `GET /api/resource/Work Order?filters=[["sales_order","=","<SO>"]]&fields=["name","production_item","qty","status","planned_start_date","actual_end_date"]`

---

### Lesson 5.4: Manufacture material requests

- Manufacture-type material requests (Purchasing shows only Purchase ones) appear on the **Material requests** tab in lanes **Draft → Needs work order → Building → Done** (last 30 days).
- "Building" = it has a work order (drafts count). "Done" = every linked work order is Completed.
- ERPNext's own "Manufactured" status only means work orders **cover** the quantity, not that it's built.
- The tab label shows the open count, red when one is past its needed date.

**SS-05-12** · Material requests tab with lanes
**URL:** `/command-center#mfg` → Material requests

---

### Lesson 5.5: Build points, capacity and the schedule board (production lead)

**Objective:** plan the floor using points.

- **Build points** measure difficulty per run: 2C/3C/4C/5C/6C runs, wet-rated (IP67+), FMC / jumpers, assemblies, loose bulk reels. Stamped on BOM submit and work order insert; roll up to SO lines and totals.
- Weights live in **ilL-Production-Settings**: 1 / 1.3 / 1.4 / 1.5 / 1.75 for 2C-6C; wet 1.75; FMC 2; assembly 2.5; loose 0.75; a separate release weight set; 57.5 points per person-day; head count 5.5; shift end 16:30; holiday list; overtime; commission flag 22%; monthly goals; paint supplier group; quote follow-up days.
- **Worth per point** = (net total − commission) / points.
- Floor staff can correct a count from the board queue; the change is logged on the timeline.
- **Schedule board tab:** pipeline cards (Pend-Prod / In-Prod / Pend-Ship / Waiting for parts / Paint / Held, with $, orders, points, average commission; commission over 22% in red), shipped today / this month, gap to monthly goal and dollars needed per shipping day, on-time %, due (past due, today, tomorrow, this week), capacity (workload, per day, days to complete, date clear, 22-workday burn-down), order queue (filter, sort by ship date / $ per point / points), waiting for parts, shipped this month.
- **Status rules:** floor override first; On Hold or a stopped WO = Held; all WOs complete = Pend-Ship; any WO in process = In-Prod; material short = Waiting for parts; else Pend-Prod.
- Dollar columns need Command Center Finance, Manufacturing Manager, Accounts Manager or System Manager; everyone else sees points.

**SS-05-13** · Schedule board tab, top half
**URL:** `/command-center#mfg` → Schedule board · **Role:** Manufacturing Manager
**Highlight:** pipeline cards; gap to goal; capacity and burn-down

**SS-05-14** · Order queue with filter and sort
**Highlight:** points, hours, $ per point, floor notes

**SS-05-15** · (pair) Schedule board as Manufacturing User (points only) vs Manager (dollars)

**SS-05-16** · ilL-Production-Settings form
**URL:** `/app/ill-production-settings` · **Highlight:** weights; capacity; monthly goals

**SS-05-17** · Correcting build counts from the queue

---

### Lesson 5.6: The report tabs

| Tab | What it shows |
|---|---|
| Run rate & daily $ | Orders received per workday (30 workdays) with $0 / same-day / next-day / rush counts; shipped $ per workday vs needed |
| Monthly report | This month and next two: goal, shipped, scheduled, run rate, at risk, expected releases, projection, % of goal, average commission |
| Releases & holds | Hold for Release / Confirmation orders with Likely Ship Date; Hold for Ship with days to ship |
| Proforma & will call | Open and completed-this-month |
| Paint | Orders at the paint supplier: PO, sent, due back, items |

**SS-05-18** · Monthly report tab
**SS-05-19** · Releases & holds tab
**SS-05-20** · Paint tab

---

## Slide deck beats

1. The chain: SO → WO → pick → build → ship → DN
2. What's automatic (linear fixtures) and what isn't (tape, neon, sheet)
3. The Flow tab as the daily list
4. Submitting a WO: the drawing gate
5. The traveler and QC
6. Stock entries that move the stage
7. Build points and capacity
8. The schedule board and gap to goal
9. Report tabs for the Monday plan

## Check yourself

1. An order has tape lines only. Will work orders appear by themselves?
2. What moves an order from Pend-Prod to In-Prod?
3. Where do you change the points-per-person-day figure?
4. A manufacture material request shows "Manufactured" in ERPNext. Is it built?
5. Why can't you use Request for Raw Materials on a particular line?
