# Module 06: Shipping, delivery notes & tracking

**Audience:** shipping / warehouse, operations, sales and support (for tracking questions). **Length:** 90 minutes.
**Roles used:** Stock User / Manager (submit Shipment, buy labels), Command Center Editor, Dealer (portal side).

## Purpose

Trainees can pick and pack an order, create the delivery note and shipment, buy and print labels, get tracking to the dealer, handle will call, freight and drop ship, record late shipments, and hand off to invoicing.

> **Status:** The EasyPost label and tracking integration is built but has **not run live yet** (Rolling out). Until the pilot, the live process is **manual**: buy the label outside ERPNext and type Carrier and Tracking Number on the delivery note (Lesson 6.5). Teach both; mark the EasyPost slides "Rolling out".

## Where to go

| What | Where |
|---|---|
| Shipping stage | `/command-center#ship` |
| Orders to deliver | `/app/sales-order?status=["in",["To Deliver","To Deliver and Bill"]]` (Shipping quick link) |
| Pick lists | `/app/pick-list` |
| Delivery notes | `/app/delivery-note` |
| Shipments (labels) | `/app/shipment` |
| Packing slips | `/app/packing-slip` |
| Shipping settings | `/app/ill-shipping-settings` |
| Dealer side | `/portal/orders/<SO>` (Shipments panel) |

## Recommended workflow (one order, one ship event)

1. Order reaches **Pick & ship** on the Command Center.
2. **Pick List** from the SO; print **ilL Pick List**; pick; mark picked.
3. **Delivery Note** from the SO or pick list. **Save, don't submit yet.**
4. **Create Shipment** from the delivery note → add boxes (inches, pounds) → **Submit** the Shipment.
5. **Create Labels** → confirm the rate → **Buy Labels** → **Print Labels**. Tracking copies to the delivery note.
6. **Submit the delivery note.** This sends the dealer their shipped email with tracking.
7. Tracking updates arrive automatically; the Shipment completes when every box is delivered.
8. Create the **Sales Invoice** from the delivery note (Module 09).

**The rule:** buy labels **before** submitting the delivery note, or the shipped emails go out without tracking.

---

### Lesson 6.1: The Shipping stage in the Command Center

**Objective:** know what's ready to go out today.

- Summary tiles: orders to pick & ship, lines to pick, short in stock, draft delivery notes, shipped last 7 days.
- **Pick list: ready to ship**: one block per order at "Pick & ship". Each line: item, quantity to pick, warehouse, "On the shelf" or "Short n". Kits are expanded ("part of X"). Each block links its open pick lists and draft delivery notes. "Everything is picked; submit the delivery note." when done.
- **Open pick lists** and **Draft delivery notes** ("Submit once the order has shipped").
- **Shipped in the last 7 days**.
- **Delivery timeline** (red past due, orange at risk, green ready) and **"Can it go out?"** (Ready / At risk with reasons; flags "may have shipped without a Delivery Note").
- Click any document for the side sheet. On a submitted delivery note you can edit carrier, tracking number, "late, not warehouse fault" and why late. Creating and submitting happen in the desk.

**SS-06-01** · Shipping stage, full page
**URL:** `/command-center#ship` · **Role:** Stock User + CC Viewer
**Highlight:** tiles; a ready-to-ship block with a Short badge; Draft delivery notes table

**SS-06-02** · "Can it go out?" table with an At risk row and its reason

**SS-06-03** · Side sheet on a submitted delivery note, editing tracking fields
**Role:** Editor

---

### Lesson 6.2: Pick lists and packing

- From the SO: **Create → Pick List**. Print **ilL Pick List** (customer, orders, project, warehouse, batch/serial per line, a write-in "picked" column, Picked by / Checked by). No prices.
- Product bundles (kits) are expanded to parts. Non-stock lines without parts and drop-ship lines are skipped.
- Optional **Packing Slip** (print **ilL Packing List**: case number, carrier, tracking, net/gross weight).

**SS-06-04** · SO → Create → Pick List menu
**SS-06-05** · ilL Pick List print preview
**Highlight:** picked column; signatures
**SS-06-06** · ilL Packing List print preview

---

### Lesson 6.3: The delivery note

- Create from the SO or pick list: **Create → Delivery Note**. One delivery note per ship event or carrier; a split order gets one per shipment.
- Fields: **Carrier** (UPS / FedEx / USPS / Freight / Other) and **Tracking Number**, next to Transporter Name; editable after submit.
- **On-Time Review** section: **Late, Not Warehouse Fault** (counts as on time on the board) and **Why Was This Late**.
- Lines carry designation, room, notes and configured links from the SO.
- Print **ilL Delivery Note** is the packing slip that goes in the box (ship date, dealer PO, orders, carrier, every tracking number, kit contents, packed box, received-by signature, damage / shortage line; no prices). Dealers see it as "Packing Slip".

**SS-06-07** · Delivery note form (draft) with Carrier, Tracking Number and On-Time Review
**URL:** `/app/delivery-note/<draft>` · **Highlight:** Create Shipment button; Carrier; Tracking Number

**SS-06-08** · ilL Delivery Note print preview (the in-box packing slip)

**DATA-06-01** · Delivery notes for our job (DATA-02-01) with carrier and tracking
**API:** `GET /api/resource/Delivery Note?filters=[["docstatus","=",1],["ill_tracking_number","is","set"]]&fields=["name","customer","ill_carrier","ill_tracking_number","posting_date"]&order_by=posting_date desc&limit_page_length=5`

---

### Lesson 6.4: Shipments and EasyPost labels (Rolling out)

**Objective:** buy, print and void labels from ERPNext.

**Create the Shipment**
- On a **saved** delivery note (draft or submitted), click **Create Shipment**. If one exists, it opens that one.
- Pre-filled: pickup address (from settings), you as pickup contact, the customer's delivery address and contact, value of goods (DN total), pickup today 09:00-17:00, description "LED lighting fixtures and components", one suggested box from item weights and the default box template.
- One Shipment per delivery note.

**Add boxes**
- **Add Template** picks a standard box, or type dimensions. Units are **inches and pounds**.
- A row with Count 3 becomes three rows on save, so each box gets its own tracking number.
- Boxes over the additional-handling or oversize limits get flagged; an orange "Surcharges likely" alert shows, but you can still submit. Boxes over the maximum are refused.
- **Submit** (every box needs length, width, height and weight).

**Buy labels**
- **Create Labels** gets a rate (address verified, FedEx Ground or Home Delivery for residential, on our FedEx account). It is one automatic choice, not a comparison across carriers.
- The confirm dialog shows service, rate, boxes, transit days, address verified / residential, surcharge flags. Click **Buy Labels ($xx.xx)**.
- After buying: master tracking number, carrier, service, cost, tracking URL; status **Booked**; Label Status **Bought**; each box's tracking number and label; one merged label PDF attached; carrier and tracking copied to the delivery note.
- **Print Labels** opens the merged PDF.

**Void**
- **Void Label** refunds every box, clears the numbers from the Shipment and delivery note, Label Status **Voided**. You can buy again.
- A Shipment with bought labels **can't be cancelled** until voided.

**Errors** (red banner "Label error: …", Label Status Error): invalid address, no rate, already refunded, EasyPost error. "This rate is out of date. Click Create Labels again." After a timeout on buy, **check EasyPost before retrying** (a retry can't buy twice, but check anyway).

**Not supported:** insurance; LTL / freight labels (use Lesson 6.5); customer-billed or collect freight; return labels (return delivery notes have no Create Shipment button).

**SS-06-09** · Create Shipment button on a saved delivery note
**SS-06-10** · New Shipment, pre-filled, with the blue units intro
**URL:** `/app/shipment/new` · **Highlight:** pickup / delivery addresses; value of goods; parcel row
**SS-06-11** · Add Template dialog with standard boxes
**SS-06-12** · (pair) Parcel row with Count 3 → three rows after save
**SS-06-13** · "Surcharges likely" alert on submit
**SS-06-14** · Submitted Shipment with Create Labels button
**SS-06-15** · Buy Labels confirm dialog (EasyPost test key)
**Highlight:** rate; transit days; address verified; Buy Labels button
**SS-06-16** · Shipment after buying: Booked, Bought, per-box tracking, attached PDF
**SS-06-17** · Merged label PDF
**SS-06-18** · Void Label confirm and the resulting timeline comment
**SS-06-19** · Label error banner (e.g. invalid address)
**SS-06-20** · Cancel blocked: "Void the label before cancelling this Shipment."

---

### Lesson 6.5: Manual labels, freight, will call and drop ship

**Manual label (the live process today, and the fallback if EasyPost is down)**
- Buy the label in the carrier's site. On the delivery note set **Carrier** and **Tracking Number**, then submit. Tracking links work for UPS, FedEx and USPS.

**Freight / LTL**
- No label integration. Set Carrier **Freight** or **Other** and type the PRO / BOL number (no clickable link). All freight is billed to our account; collect freight isn't supported.

**Will call (customer pickup)**
- Set **Proforma / Will Call = Will Call** on the SO. When built, the stage becomes **Will Call - Ready**.
- Send the manual template "ilL - Sales Order - Ready for pickup" (uses pickup address and hours from ilL-Email-Settings).
- Still submit a delivery note when it's collected; no Shipment.

**Proforma**
- Proforma orders stay "Proforma - Awaiting Payment" until paid. Don't ship until the stage moves.

**Drop ship**
- SO lines delivered by the supplier are skipped on the pick list. The PO email tells the vendor "This is a drop shipment to our customer X".

**SS-06-21** · Delivery note with Carrier = Freight and a PRO number typed in
**SS-06-22** · SO with Will Call set and stage "Will Call - Ready"
**SS-06-23** · Ready for pickup email template preview

---

### Lesson 6.6: Tracking updates and who gets told (Rolling out)

- **Where tracking lives:** the Shipment (master number and per-box numbers and statuses). The delivery note mirrors the main number.
- **Automatic updates:** EasyPost sends tracking events through n8n to ERPNext.

| Carrier status | Box status | Shipment |
|---|---|---|
| pre-transit, in transit, out for delivery, available for pickup | same | In Progress |
| delivered | Delivered | **Completed** when every box is delivered |
| return to sender | Returned | Returned + exception alert |
| failure / error | Exception | exception alert |

- Labels bought outside ERPNext don't get automatic updates.

**Emails**

| Email | When | Who | Status |
|---|---|---|---|
| "Your order has shipped" / "Part of your order…" | Delivery note submit | Dealer portal buyers (they can turn it off) | Live, always on |
| "ilL - Delivery Note - Shipped" with packing slip PDF | Delivery note submit | DN contact email | Off until ilL-Email-Settings switch |
| "Delivered: SO" | Shipment Delivered | Dealer portal buyers | Off until ilL-Shipping-Settings switch |
| "Shipping exception" | Box exception or return | Shipping lead | (Rolling out) |
| "Delivery check-in" | 5 days after DN date | Customer | Notification, check if enabled |

**SS-06-24** · Shipment with mixed box statuses (one Delivered, one In Transit)
**SS-06-25** · Dealer "Your order has shipped" email (from the email queue)
**URL:** `/app/email-queue/<name>`
**SS-06-26** · Dealer notification settings with the Shipping notifications toggle
**URL:** `/portal/account/notifications` · **Role:** Dealer

---

### Lesson 6.7: Answering "where's my order?"

- **Dealer view:** `/portal/orders/<SO>` → Order Progress (% delivered), **Shipments** panel (one row per delivery note: items, date, carrier, every tracking link, Packing slip PDF), timeline.
- **Staff:** open the SO → Connections → Delivery Note → Shipment. Or the Command Center order page.
- **Order stage:** Pend-Ship → Partially Shipped (n%) → Shipped / In Transit → Completed (billed).
- Helpdesk tickets link to the SO, not the delivery note or Shipment.

**SS-06-27** · Dealer order page Shipments panel with tracking links
**URL:** `/portal/orders/<SO>` · **Role:** Dealer
**SS-06-28** · Same panel at phone width (390×844)

---

### Lesson 6.8: Late shipments and on-time %

- **On time** = delivery note date ≤ the SO's Estimated Ship Date (or delivery date), or **Late, Not Warehouse Fault** ticked.
- Manufacturing → Schedule board: "On-time this month" tile (flagged below 95%), **Shipped this month** table with On time / Late, not warehouse / Late and **Why late**, on-time by week.
- **After every late shipment:** fill Why Was This Late; tick Not Warehouse Fault only when it wasn't (customer hold, vendor, carrier).

**SS-06-29** · Shipped this month table with Late badges and reasons
**URL:** `/command-center#mfg` → Schedule board
**SS-06-30** · Delivery note On-Time Review section filled in

---

### Lesson 6.9: Settings (shipping lead and admin)

- **ilL-Shipping-Settings:** Enabled (master switch for labels), webhook URL and secret, EasyPost carrier account, service and residential service, pickup address and hours, description, default box template, exception alert email, Send Delivered Email, surcharge thresholds (FedEx published values; check against our agreement).
- **Shipment Parcel Templates** for standard boxes; a warehouse Address with phone and email.
- Buying, voiding and printing labels need **Submit** permission on Shipment (Stock User / Manager by default).
- The EasyPost key lives only in n8n (Module 13).

**SS-06-31** · ilL-Shipping-Settings form
**URL:** `/app/ill-shipping-settings` · **Role:** System Manager
**SS-06-32** · Shipment Parcel Template list

---

## Slide deck beats

1. The 8-step ship workflow (diagram), and the one rule
2. Shipping stage: what's ready today
3. Pick list and packing slip
4. Delivery note fields that matter
5. Shipment and boxes (inches, pounds, one row per box)
6. Buying, printing, voiding labels (rolling out)
7. Manual label, freight, will call, drop ship
8. Tracking updates and emails
9. "Where's my order?" script for sales and support
10. Late shipments and on-time %

## Check yourself

1. Why must labels be bought before the delivery note is submitted?
2. A shipment has three boxes. How many tracking numbers, and where do they show?
3. EasyPost is down and the truck is here. What do you do?
4. A dealer will pick up their order. What do you set, and what do you send?
5. An order shipped two days late because the customer moved the date. What do you record?
6. Why can't you cancel a Shipment?
