# Module 04: Sales orders

**Audience:** sales review, order approvers, operations, owner. **Length:** 90 minutes.
**Roles used:** ilL Sales Review, ilL Order Approver (submit), Command Center Editor, Dealer (portal side).

## Purpose

Trainees can create a sales order every way it happens, review and approve a dealer's order request, understand the order **stage** and what moves it, use the holds and ship-date fields, send the right customer emails, and process change, cancellation, reorder and replacement requests.

## Where to go

| What | Where |
|---|---|
| Sales orders stage | `/command-center#orders` |
| One order's page | `/command-center#so-<SO name>` |
| New sales order | `/app/sales-order/new` |
| Sales orders list (stage pill colours) | `/app/sales-order` |
| Order requests (intakes) | `/app/ill-order-intake` |
| Order changes | `/app/ill-order-change` |
| Staff queues | `/app/ill-portal-operations` → Order review, Order changes |
| Dealer side | `/portal/orders`, `/portal/orders/<SO>` |

---

### Lesson 4.1: Four ways an order is created

| Path | How | Result |
|---|---|---|
| Dealer accepts a portal offer | Module 03, Lesson 3.8 | Draft SO + order request (intake) |
| Dealer orders straight from a schedule | Portal "order request": PO, billing / shipping address, purchasing contact, requested date, receiving / shipping instructions, files | Draft SO + intake (SUBMITTED or UNDER_REVIEW) |
| From a desk Quotation | Quotation → Create → Sales Order | Draft SO |
| Directly in the desk | `/app/sales-order/new` + **Configure & Add Fixture** (needs ilL Sales Review) | Draft SO |

- Draft sales orders **create no demand**: no work orders, no shortages, no purchasing.
- The desk schedule form also has **Actions → Convert to Sales Order** (READY or QUOTED schedules).
- For a dealer order request, staff get a desk bell and an assignee from ilL-Portal-Routing-Settings.

**SS-04-01** · Dealer: order request form from a schedule
**URL:** `/portal/schedules/<schedule>` → Order · **Role:** Dealer
**Highlight:** PO number, addresses, purchasing contact, requested date, instructions, files

**SS-04-02** · Desk: new sales order with Configure & Add Fixture
**URL:** `/app/sales-order/new` · **Role:** ilL Sales Review

**SS-04-03** · Quotation → Create → Sales Order menu
**URL:** `/app/quotation/<submitted>`

---

### Lesson 4.2: Reviewing and approving a dealer order request

**Objective:** take an order request from SUBMITTED to APPROVED and submit the SO.

- **Intake states:** SUBMITTED → UNDER_REVIEW → INFORMATION_NEEDED / CHANGES_PROPOSED → APPROVED, or REJECTED / WITHDRAWN.
- On the draft SO, the **Portal request** button group:
  - Intake, files and conversation
  - Conversation with buyer
  - **Confirm delivery date** (sets "Staff Confirmed Delivery Date")
  - **Review order request**: Review, Request information, Propose changes, Reject (message required), Approve
- A banner shows the intake state, what changed since the buyer acknowledged, and open change requests.
- **Submit is blocked until:**
  1. the intake is complete;
  2. staff have confirmed a delivery date;
  3. billing address, shipping address and contact are present and belong to the customer;
  4. the buyer acknowledged the **current** revision (any staff edit after acknowledgement needs a new one);
  5. a linked offer is still accepted and its Quotation not cancelled;
  6. every configured row has an active submitted BOM.
- Drawings are **not** checked here; they block the work order instead (Module 02, Lesson 2.5).
- **On approval:** intake APPROVED, an **order acknowledgement PDF** is generated, a note is posted, the dealer is emailed.
- Submitting needs **ilL Order Approver** (or native SO submit permission). Rejection marks the schedule ISSUE.

**SS-04-04** · Draft SO with the Portal request banner and button group
**URL:** `/app/sales-order/<draft>` · **Role:** ilL Order Approver · **State:** intake UNDER_REVIEW
**Highlight:** banner; Confirm delivery date; Review order request

**SS-04-05** · Review order request dialog with the five choices

**SS-04-06** · Submit blocked: "buyer must acknowledge current revision" message

**SS-04-07** · Dealer: Acknowledge current revision on the order page
**URL:** `/portal/orders/<SO>` · **Role:** Dealer

**SS-04-08** · Order acknowledgement PDF
**URL:** attachment on the SO / dealer download

**SS-04-09** · Portal Operations → Order review queue

---

### Lesson 4.3: The Sales orders stage and the per-order page

**Objective:** use `#orders` and `#so-<name>` to spot orders that need attention.

- **#orders:**
  - stats: open orders, past delivery, need materials, need correcting
  - **Order requests** lanes: Submitted · Under review · Information needed · Changes proposed · Approved (30 days)
  - drawing requests tied to sales orders (manufacturing sign-off)
  - open SO rows with mini steps (Ordered › Materials › Production › Shipped › Billed), to-do / task / ticket pills
  - order tickets, draft SOs ("create no demand yet"), order change requests
- **#so-<name>:** step bar; **Needs correcting** flags (zero value, On Hold, past due, retired part numbers, duplicate or stale work orders, "may have shipped without a Delivery Note", open change requests); to-dos (**+ Add to-do**); related quotation, tickets, projects, intakes, drawing requests; lines; purchasing needed (**Draft MR**, PO ETAs); work orders and lines that still need one.

**SS-04-10** · Sales orders stage, full page
**URL:** `/command-center#orders` · **Role:** Editor + Finance
**Highlight:** order request lanes; mini steps on a row; Draft SOs table

**SS-04-11** · Per-order page with Needs correcting flags
**URL:** `/command-center#so-<name>` · **State:** an SO with at least one flag
**Highlight:** step bar; flags; Draft MR button; + Add to-do

**DATA-04-01** · Our job's sales order (from DATA-02-01) with its stage history
**API:** `GET /api/resource/Sales Order/<name>` and `GET /api/resource/Version?filters=[["ref_doctype","=","Sales Order"],["docname","=","<name>"]]&fields=["creation","data"]&order_by=creation asc`
**Use:** "life of an order" timeline slide

---

### Lesson 4.4: Order stage: what it means and what moves it

**Objective:** read the stage pill and know what will move it next.

| Stage | Meaning |
|---|---|
| Pending Approval | Any draft |
| Hold for Release / Hold for Confirmation | On hold by request; shows Likely Ship Date |
| Needs Work Orders | Build lines without a work order |
| Pend-Prod | Ready for production |
| Waiting for parts | Short after stock is allocated in ship-date order; note shows parts ETA or "No PO for short parts" |
| In-Prod / Paint | Being built / at the paint supplier |
| Held | On Hold or a stopped work order |
| Pend-Ship / Hold for Ship | Built, waiting to ship / held until ship date |
| Will Call - Ready | Built, customer picks up |
| Proforma - Awaiting Payment | Must be paid before it ships |
| Partially Shipped (n%) / Shipped / In Transit | Delivery notes submitted |
| Delivered | Manual override only |
| Completed / Cancelled | Closed or billed / cancelled |

- Also on the SO: **Waiting On** (Us / Customer / Vendor / Warehouse) and **Stage Detail**.
- **Stage Override** wins until cleared (Completed and Cancelled always win). The older "Production Status Override" field was merged into it.
- Stages refresh on SO, work order, stock entry, payment, invoice, delivery note, PO and receipt events, plus a sweep every 15 minutes. Expect up to 15 minutes' lag.
- Shortages are shared across all open orders in ship-date order, so **one order's stage can change when another order changes**.

**SS-04-12** · Sales order list coloured by stage
**URL:** `/app/sales-order` · **Highlight:** stage pills

**SS-04-13** · SO form header with stage pill, Waiting On and Stage Detail
**URL:** `/app/sales-order/<name>`

**DATA-04-02** · Open orders by stage
**API:** `GET /api/resource/Sales Order?filters=[["docstatus","=",1],["status","not in",["Completed","Closed","Cancelled"]]]&fields=["ill_stage","count(name) as n"]&group_by=ill_stage`

---

### Lesson 4.5: Ship dates, holds, proforma and will call

**Objective:** set the fields that drive the production board and customer emails.

| Field | Use |
|---|---|
| Estimated Ship Date | The day it leaves our warehouse. Drives the production board and on-time %. Falls back to delivery date |
| Staff Confirmed Delivery Date | The promise to the dealer (set during approval) |
| Hold Reason | Hold for Release / Confirmation / Ship |
| Likely Ship Date | Shown for release and confirmation holds |
| Proforma / Will Call | Proforma = pay before shipping; Will Call = customer pickup |
| Floor Notes | Notes for the production floor |
| Receiving / Shipping Instructions | From the dealer's order request |

- All of these can be edited **after submit**, in the desk or the Command Center side sheet (Editor).
- Changing a submitted delivery promise must go through the order change workflow (Lesson 4.7).

**SS-04-14** · SO form: production and hold section
**URL:** `/app/sales-order/<name>` · **Highlight:** Estimated Ship Date; Hold Reason; Likely Ship Date; Proforma / Will Call; Floor Notes

**SS-04-15** · Editing Estimated Ship Date from the Command Center side sheet
**URL:** `/command-center#orders` → SO sheet · **Role:** Editor

---

### Lesson 4.6: Deposits, terms and customer emails

**Objective:** collect deposits and keep the dealer informed.

- Terms: prepay unless approved for Net 30. Credit control is native ERPNext (customer credit limit and payment terms).
- **Deposits** come from the SO payment schedule: with several rows, the first open row is the deposit; a single row due within 3 days of the order date is "Payment in advance".
- To collect before production, use the Sales Invoice template "Order confirmation and invoice" (Module 09).
- **Print formats:** ilL Sales Order (hold reason, instructions, shipped / billed %, advance paid, balance); ilL Sales Order - MSRP (for the dealer's client).
- **Automatic emails** (off until enabled in ilL-Email-Settings): order confirmation on submit with the ilL Sales Order PDF.
- **Portal emails** (always on): order approved, action needed, shipped.
- **Manual templates** on Sales Order: Deposit request; On hold, action needed; Ship date changed; Ready for pickup; Proforma, pay before shipping; Partial shipment; Order change confirmed; Status update; Drawings ready.
- The "Ship date update" Notification exists but is disabled.

**SS-04-16** · SO payment schedule with a deposit row
**URL:** `/app/sales-order/<name>` · **Highlight:** payment schedule table

**SS-04-17** · Email composer with the SO template list open
**Highlight:** the "ilL - Sales Order - …" templates

**SS-04-18** · ilL-Email-Settings: automatic email switches
**URL:** `/app/ill-email-settings` · **Role:** System Manager

**SS-04-19** · Print preview: ilL Sales Order

---

### Lesson 4.7: Changes, cancellations, reorders and replacements

**Objective:** process a dealer's order change request correctly.

| Type | Allowed when | Staff action |
|---|---|---|
| Change | Order approved | Cancel the SO, amend it, get a fresh intake, buyer acknowledgement and approval, then Complete |
| Cancellation | Order approved | Cancel the SO in the desk, then Complete |
| Reorder | Order approved | Creates a new DRAFT schedule automatically; completes at once |
| Replacement | After a rejection, withdrawal or cancellation | Creates a new DRAFT schedule automatically; completes at once |

- Staff decide in `/app/ill-order-change/<name>`: REVIEW (→ UNDER_REVIEW), REJECT or COMPLETE.
- Queue: Portal Operations → Order changes. The CC per-order page flags open change requests.
- A **staff note** field is kept internal.

**SS-04-20** · Dealer: change / cancellation request on the order page
**URL:** `/portal/orders/<SO>` · **Role:** Dealer

**SS-04-21** · Desk order change record with decision buttons
**URL:** `/app/ill-order-change/<name>` · **Role:** ilL Sales Review

**SS-04-22** · Order change requests table on `#orders`

---

### Lesson 4.8: What the dealer sees

- `/portal/orders`: status (Order Request → Approved → In Production → Production Complete → Partially Shipped → Shipped → Completed; also On Hold, Cancelled, Issue) and a **"Needs your action"** filter.
- `/portal/orders/<SO>`: next-step banner, timeline, complete intake, edit PO number, acknowledge current revision, withdraw, download acknowledgement, change / cancellation requests, shipments with tracking, invoices with balance, packing slips, conversation, Request Drawing.

**SS-04-23** · Dealer orders list with Needs your action filter
**URL:** `/portal/orders` · **Role:** Dealer

**SS-04-24** · Dealer order detail page, full scroll (phone width 390×844 as well)
**URL:** `/portal/orders/<SO>`

---

## Slide deck beats

1. Four ways an order starts
2. Drafts create no demand: why approval matters
3. The approval checklist (six gates before submit)
4. Order stages and what moves them
5. Ship dates and holds: the fields the floor relies on
6. Deposits, proforma and will call
7. Customer emails: automatic, portal, manual
8. Change, cancel, reorder, replace
9. The dealer's order page
10. Worked example: our job's order timeline (DATA-04-01)

## Check yourself

1. A dealer accepted a quote yesterday. Why isn't the order on the production board?
2. You edited a line after the buyer acknowledged. What must happen before you can submit?
3. Where do you put the date the order will leave our warehouse?
4. An order shows "Waiting for parts" but nothing changed on it. How is that possible?
5. A dealer wants to change quantities on an approved order. Walk through the steps.
