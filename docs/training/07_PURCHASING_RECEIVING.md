# Module 07: Purchasing & receiving

**Audience:** buyer, receiving, operations. **Length:** 2 sessions of 75 minutes (buying; then inbound and receiving).
**Roles used:** Purchase User / Manager, Stock User, Command Center Editor (+ Finance to show dollars).

## Purpose

Trainees can find what needs ordering, run the full buying cycle (material request → RFQ → supplier quotation → purchase order), track the vendor and the inbound shipment, and receive goods correctly.

> **Status:** the Command Center purchasing buttons (draft MR, RFQ, PO, shipment, receipt, LCV) are built ⚠️ but have **not been run through a full cycle on the live site**. Before rollout, do one full staging cycle with Charlotte: MR → RFQ → SQ → PO → email → shipment → PR → vendor bill + broker bill → LCV. Capture screenshots from that cycle.

## Where to go

| What | Where |
|---|---|
| Purchasing desk | `/command-center#purch` |
| Material requests | `/app/material-request` (+ New) |
| RFQs | `/app/request-for-quotation` |
| Supplier quotations | `/app/supplier-quotation` |
| Purchase orders | `/app/purchase-order` (+ New) |
| Inbound shipments | `/app/ill-inbound-shipment` |
| Purchase receipts | `/app/purchase-receipt` |
| Suppliers | `/app/supplier` |
| Customs tariff numbers (HTS) | `/app/customs-tariff-number` |
| Stock balance | `/app/query-report/Stock Balance` |
| Settings | `/app/ill-purchasing-settings` ("Settings" on the page) |

## The cycle

**To order → Requests → Vendor quotes → POs → In transit → Received → Bills → Landed cost**

This strip sits at the top of the Purchasing desk. Each tile has a count, dollars (Finance roles) and a red or amber dot when it holds a decision. This module covers the first six; Module 08 covers Bills and Landed cost.

**Every button creates a draft and says so. You submit in the desk.** The Command Center never submits or cancels.

---

### Lesson 7.1: The Overview tab and the decisions

**Objective:** start each day from the decisions list.

| Decision | Meaning | Threshold |
|---|---|---|
| to_order_late (red) | A firm shortage is past its order-by date | order-by = need date − lead time − safety days (3) |
| reorder_breach | Item below its reorder level | |
| mr_unactioned | Material request still "To quote" | > 2 days |
| quote_expiring | Supplier quotation valid-till close | ≤ 7 days (setting) |
| rfq_no_reply | RFQ with no reply | > 5 days |
| po_draft_old | Draft PO not submitted | > 2 days |
| po_not_sent (red) | Submitted PO still "Not sent" | |
| po_unconfirmed | Sent, not confirmed by vendor | > 3 days (setting) |
| po_overdue (red) | ETA passed, not received | |
| po_will_miss (red) | ETA after the sales order needs it | |
| shipment_eta_passed | Inbound shipment past ETA | |
| receipt_no_bill | Receipt not fully billed | > 14 days (setting) |
| bill_overdue (red) | Vendor bill past due | |
| bill_not_in_qbo (red) | Submitted bill not in QuickBooks | |
| needs_lcv | Freight / duty not in stock value yet | red after 30 days (setting) |
| cost_variance | Shipment actual cost ≥ 15% over estimate | |
| mail_unlinked | purchasing@ email not linked to a document | |

- Each decision opens its tab and lane.
- Also on Overview: arriving in the next 14 days (late ones red), open PO value by supplier, open PO value by month of ETA.

📸 **SS-07-01** · Purchasing desk Overview with the flow strip and decisions
**URL:** `/command-center#purch` · **Role:** Purchase Manager + CC Finance
**Highlight:** flow strip dots; three decisions (one red); Arriving next 14 days

📸 **SS-07-02** · (pair) Overview as Purchase User without Finance (no dollars) vs with
📸 **SS-07-03** · Flow strip at phone width (2-column grid)

---

### Lesson 7.2: To order: shortages, reorder levels and data gaps

- **Shortage table:** what's short against firm sales orders and work orders. Multi-select → **Draft one MR for selected**.
- **Below reorder level** with a suggested level and **Apply**.
- **Only if draft orders go ahead**: shortages from draft sales orders (heads-up only).
- **Data gaps:** items missing a supplier, lead time, reorder level, HTS code or country of origin. Lead time can be set inline; the rest are fixed on the Item.
- **Lead time comes from** (first found): PO line → PO header → latest live supplier quotation → supplier default → item lead time → item-group default in settings → none (listed as a data gap).

📸 **SS-07-04** · To order tab: shortage table with rows selected and "Draft one MR for selected"
📸 **SS-07-05** · Below reorder level with Apply
📸 **SS-07-06** · Data gaps list with inline lead time edit

🔌 **DATA-07-01** · Items missing HTS code or supplier (for the "why data gaps matter" slide)
**API:** `GET /api/resource/Item?filters=[["is_stock_item","=",1],["disabled","=",0],["customs_tariff_number","is","not set"]]&fields=["name","item_group"]&limit_page_length=50`

---

### Lesson 7.3: Requests and vendor quotes

**Requests tab:** material request lanes Draft · To quote · Quoted · Ordered · Receiving.
- **Request quotes** drafts an RFQ. **Order directly** drafts a PO (when you already know the vendor and price).

**Vendor quotes tab:** RFQ draft · Awaiting reply · Quoted · Expiring · Ordered · Expired / lost.
- **Enter quote** drafts a supplier quotation from the vendor's reply.
- **Accept → draft PO** turns a quote into a draft PO.
- **Compare quotes** shows items with two or more live quotes; cheapest and fastest marked.

📸 **SS-07-07** · Requests tab lanes with Request quotes / Order directly buttons
📸 **SS-07-08** · Draft RFQ created from the board (desk form)
📸 **SS-07-09** · Vendor quotes tab with Enter quote and Accept → draft PO
📸 **SS-07-10** · Compare quotes view

---

### Lesson 7.4: Purchase orders: creating, sending, tracking

**Creating**
- From the board (Order directly, Accept → draft PO) or `/app/purchase-order/new`.
- A new PO is pre-filled with lead time, ETA, freight mode and vendor status "Not sent". A blank Required By is allowed.
- **Supplier part numbers:** a blank one is filled from the Item; a different one you type is **saved back to the Item**. Type it right.
- Submit in the desk. A PO without an ETA gets one on submit.

**Sending**
- **Email PO** from the side sheet (opens the desk PO) or the desk email composer. Mail goes from **purchasing@** with your name.
- Emailing a submitted PO marks it **Sent**. A confirmation chase Notification (disabled by default) fires after 3 days.
- Drop ship POs tell the vendor it's a drop shipment to our customer.

**Tracking (side sheet, editable after submit)**
- Vendor status, sent and confirmed dates, vendor ack #, lead time, ETA, promised ship date, freight mode, notes. Per-line lead time and ETA.
- Card shows lead time and its source (`28d · quote`) and the ETA: red when overdue, amber when it lands after the sales order needs it.
- PO lanes: Draft · Not sent · Awaiting confirmation · Confirmed / in production · In transit · Partly received · To bill · On hold (Done behind a toggle). Or a table sorted by ETA.
- Sheet buttons: Email PO, **Create shipment**, **Draft receipt**, **Draft bill**, + Add to agenda.
- The production board's "Waiting for parts" uses the same ETA, so both boards agree.

📸 **SS-07-11** · Purchase orders lanes
**Highlight:** an amber ETA; lead time source chip
📸 **SS-07-12** · PO side sheet with tracking fields and buttons
📸 **SS-07-13** · Desk PO form with the ilL tracking section
**URL:** `/app/purchase-order/<name>`
📸 **SS-07-14** · Email composer on a PO sending from purchasing@
📸 **SS-07-15** · PO table view sorted by ETA

🔌 **DATA-07-02** · Open POs with ETA and vendor status (for a worked example)
**API:** `GET /api/resource/Purchase Order?filters=[["docstatus","=",1],["status","in",["To Receive and Bill","To Receive"]]]&fields=["name","supplier","ill_vendor_status","ill_eta","transaction_date"]&order_by=ill_eta asc&limit_page_length=10`

---

### Lesson 7.5: The purchasing@ mailbox

- Email from a PO, RFQ, supplier quotation, receipt, bill, supplier, inbound shipment or supplier payment is sent from purchasing@ and keeps your name.
- Incoming mail that names a document number is linked to that document and the supplier.
- Unlinked mail shows as the `mail_unlinked` decision; link it by hand.
- Setup (admin): Email Account, each buyer's User → User Emails, ilL-Email-Settings → Purchasing Email Account, Buying Settings → fixed outgoing account.

📸 **SS-07-16** · PO timeline showing a linked vendor reply

---

### Lesson 7.6: Inbound shipments

**Objective:** track goods from the vendor to our dock, including customs.

- Record: **ilL-Inbound-Shipment**. Create it from the PO sheet (**Create shipment**) or the desk.
- **Statuses:** Planned → Booked → In transit → At port / customs → Cleared → Out for delivery → Delivered → Costs final (also Cancelled).
- **Freight modes:** Ocean FCL / LCL, Air, Courier, LTL, FTL, Vendor delivers, Will call.
- Fields: supplier, forwarder and customs broker (both Suppliers), incoterm, origin, tracking / BOL / AWB / PRO and URL, container, ports, ETD / ATD / ETA / ATA, cleared on, delivered on, customs entry no. and entered value; POs, receipts, cost lines, landed cost vouchers.
- **Cost lines** are seeded on creation: freight as a % of goods value, duty and tariffs from each item's HTS rates. The board shows the estimated landed % before anything arrives (Module 08).
- Changing status or ETA moves the linked POs' vendor status and ETA **forward only**.
- **Shipments tab** lanes: Planned · Moving · At customs · Arriving · Delivered, costs open · Costs final. Cards: mode, tracking, ETA / ATA, POs, goods value, estimated vs actual cost bar, landed %.

📸 **SS-07-17** · Shipments tab lanes
📸 **SS-07-18** · Inbound shipment desk form, header and routing
**URL:** `/app/ill-inbound-shipment/<name>`
📸 **SS-07-19** · Inbound shipment cost lines (estimate vs actual)
**Role:** with Finance (amounts) · note: without Finance they arrive blank

---

### Lesson 7.7: Receiving

**Objective:** receive goods so stock, the PO and the shipment all update.

1. From the PO sheet or shipment sheet: **Draft receipt** (links the receipt to the shipment).
2. Count against the vendor packing slip. Print **ilL Receiving Report** (received, accepted, rejected, **put-away location**, vendor packing slip no., Received by / Inspected by / discrepancies).
3. Enter rejected quantities if any (native ERPNext). QC is a paper sign-off; no barcode scanning.
4. **Submit** the receipt in the desk. Default warehouse "Stores - ilL". Stock is valued at the PO rate.
5. On submit: a fully received PO gets vendor status **Delivered**; the receipt joins the PO's open inbound shipment (only if exactly one; otherwise link it by hand); sales order stages refresh (orders may leave "Waiting for parts").
6. Discrepancy? Send the manual template "ilL - Purchase Receipt - Receiving discrepancy".

- **Receipts tab:** received goods with billed %, shipment and an LCV chip (Landed / Needs LCV / No inbound costs), plus **Draft bill** (Module 08).

📸 **SS-07-20** · Draft receipt created from the board
📸 **SS-07-21** · ilL Receiving Report print preview
**Highlight:** put-away column; Inspected by
📸 **SS-07-22** · Receipt with a rejected quantity
📸 **SS-07-23** · Receipts tab with LCV chips

---

### Lesson 7.8: Suppliers and HTS codes (setup)

**Supplier form → Purchasing Defaults:** supplier role (goods vendor, freight forwarder, customs broker, carrier, other), default lead time, default freight mode, purchasing email (filled from the primary contact if blank).

**Suppliers tab:** scorecard: open POs and $, quoted vs actual lead time, on-time %, last PO, default lead time (editable).

**HTS / customs tariff numbers:** set on the Item. The tariff record holds **duty %** (general rate; estimate only, the broker's entry summary is the actual), **additional tariff %** (Section 301 etc.), rates checked on, notes. No automatic rate lookup; recheck rates by hand.

**ilL-Purchasing-Settings:** company, default warehouse, safety days, reorder lookback, default lead times by item group (extrusions 10, tape / neon / sheet 35, power and controls 28), warning windows, landed cost rules per cost type.

📸 **SS-07-24** · Supplier form Purchasing Defaults section
📸 **SS-07-25** · Suppliers scorecard tab
📸 **SS-07-26** · Customs tariff number with duty and additional tariff %
📸 **SS-07-27** · ilL-Purchasing-Settings form

---

## Slide deck beats

1. The cycle strip: To order → … → Landed cost
2. Decisions: the buyer's morning list
3. Finding what to order (shortages, reorder, data gaps)
4. RFQs and comparing quotes
5. POs: create, send, track (the ETA everyone relies on)
6. purchasing@: one mailbox, auto-linked
7. Inbound shipments and customs
8. Receiving: count, report, submit; what updates
9. Suppliers and HTS setup

## Check yourself

1. Where does a PO's lead time come from if the line has none?
2. You emailed the vendor the PO from Outlook instead of ERPNext. What's wrong on the board?
3. Two open inbound shipments hold the same PO. What do you do after receiving?
4. What makes a PO card amber?
5. Why does a typo in a supplier part number on a PO matter later?
