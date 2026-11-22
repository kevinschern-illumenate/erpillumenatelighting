# Module 08: Vendor bills, payments & landed cost

**Audience:** accounting (Charlotte), buyer, owner. **Length:** 75-90 minutes.
**Roles used:** Accounts User / Manager, Purchase Manager, Command Center Finance.

## Purpose

Trainees can enter vendor, forwarder and broker bills, check the 3-way match, get bills into QuickBooks, record vendor payments the right way (in QuickBooks), and land freight and duty into stock value.

> **Status:** the QuickBooks bill sync, payment sync and landed cost buttons are built. The n8n and Intuit pieces need setup, and the purchasing writes haven't run a full live cycle ⚠️. Capture from the staging cycle described in Module 07.

## Where to go

| What | Where |
|---|---|
| Bills and landed cost tabs | `/command-center#purch` → Bills, Landed cost |
| Purchase invoices (bills) | `/app/purchase-invoice` |
| Landed cost vouchers | `/app/landed-cost-voucher` |
| Payment entries | `/app/payment-entry` |
| QuickBooks sync log | `/app/ill-qbo-sync-log` |
| QuickBooks settings | `/app/ill-qbo-settings` |
| "Bills not in QuickBooks" queue | `/app/ill-portal-operations` |

## The big picture

- **ERPNext** holds POs, receipts, bills and stock value.
- **QuickBooks Online** is the system of record for payables. **Pay bills in QuickBooks, not in ERPNext.**
- Bills flow ERPNext → QuickBooks. Payments flow QuickBooks → ERPNext.
- Landed cost vouchers stay in ERPNext; QuickBooks inventory is trued up periodically.

---

### Lesson 8.1: Entering the vendor bill

1. From the receipt or PO: **Draft bill** (Command Center) or **Create → Purchase Invoice** (desk).
2. Enter the supplier's invoice number and date, check rates and quantities.
3. Check the **3-way match chip** on the Bills tab: PO vs receipt vs bill, per item. Flagged when price variance is over **2% or $50**: `qty_off`, `price_off` or `matches`. **Nothing blocks submit**; you must check it.
4. Payment terms (Supplier or bill) set the due date, which drives the Overdue lane.
5. Submit in the desk.

- **Bills tab** lanes: Draft · Unpaid · Overdue · Partly paid · Paid (last 30 days), with the QuickBooks chip and the 3-way match chip.

📸 **SS-08-01** · Bills tab lanes with QuickBooks and 3-way match chips
**URL:** `/command-center#purch` → Bills · **Role:** Accounts User + CC Finance
**Highlight:** a `price_off` chip; a bill missing the QuickBooks chip
📸 **SS-08-02** · Draft bill created from a receipt (desk form)
📸 **SS-08-03** · Receipts tab "Draft bill" button

---

### Lesson 8.2: Forwarder and broker bills

- Forwarder and customs broker bills are Purchase Invoices to those suppliers using the **service items** (FREIGHT-IN, DUTY, TARIFF, MPF-HMF, BROKERAGE…), whose expense account is the "included in valuation" account.
- **Link each bill on the inbound shipment's cost line.** When the bill is submitted, the cost line's actual amount fills in.
- The broker's entry summary (7501) is the actual duty; the HTS rates were only the estimate.
- `cost_variance` flags a shipment whose actuals are 15% or more over estimate.

📸 **SS-08-04** · Broker bill using DUTY and BROKERAGE service items
📸 **SS-08-05** · Inbound shipment cost line linked to that bill, actual filled
**URL:** `/app/ill-inbound-shipment/<name>`

---

### Lesson 8.3: Getting bills into QuickBooks

- On bill submit, ERPNext sends it to n8n, which finds or creates the Vendor and creates the **QuickBooks Bill** (DocNumber = the ERPNext bill name; supplier invoice number in the private note). The QuickBooks id is written back to the bill (`custom_qbo_id`) and supplier.
- Cancelling the bill deletes the QuickBooks Bill, unless it has payments; then fix it in QuickBooks.
- **Not sent:** debit notes / returns, bills dated before the settings' start date, multi-currency bills.
- **Retries:** hourly for bills unacknowledged after 15 minutes. Failures: Error Log "QBO bill push failed".
- **Watch:** the `bill_not_in_qbo` decision and Portal Operations → "Bills not in QuickBooks".
- Amended bills start without a QuickBooks id (the field doesn't copy).

📸 **SS-08-06** · Submitted bill showing the QuickBooks id field filled
📸 **SS-08-07** · Portal Operations → Bills not in QuickBooks
📸 **SS-08-08** · ilL-QBO-Settings (bill webhook URL, start date, accounts)
**URL:** `/app/ill-qbo-settings` · **Role:** Accounts Manager

---

### Lesson 8.4: Paying vendors

**Objective:** pay in QuickBooks and let ERPNext follow.

1. Pay the bill in **QuickBooks** (Bill Payment).
2. QuickBooks notifies n8n, which posts it to ERPNext as a **Pay** Payment Entry against the matching bill(s) (matched by QuickBooks id). One payment across several bills = one Payment Entry with several references.
3. Edits in QuickBooks cancel and recreate the Payment Entry; voids cancel it. ERPNext never deletes it.
4. Check **ilL-QBO-Sync-Log**: Received, Matched, Created, Superseded, Cancelled, Skipped-Duplicate, Skipped-NoOp, **Failed**.

**When it fails**

| Error | Fix |
|---|---|
| No bill with that QuickBooks id | The bill never reached QuickBooks or its id wasn't written back. Fix the outbound side, then replay |
| Bill not submitted | Submit it, replay |
| allocation exceeds payment / mixed parties | Correct in QuickBooks |
| Payment uses a vendor credit, or one line covers several bills | **Manual:** record the Payment Entry by hand in ERPNext |

- Supplier payments emailed from ERPNext go from purchasing@.

📸 **SS-08-09** · Payment Entry created from QuickBooks (synced from = QuickBooks Online)
**URL:** `/app/payment-entry/<name>`
📸 **SS-08-10** · QBO sync log list with a Failed row
📸 **SS-08-11** · One sync log record: payload, Applied To, error message

🔌 **DATA-08-01** · Sync log status counts for the last 30 days
**API:** `GET /api/resource/ilL-QBO-Sync-Log?filters=[["creation",">","<30 days ago>"]]&fields=["status","count(name) as n"]&group_by=status`

---

### Lesson 8.5: Landed cost, step by step

1. **Estimate.** Creating the inbound shipment seeds cost lines: freight as a % of goods value, duty and tariffs from HTS rates. Estimated landed % shows before arrival.
2. **Receive.** Submit the receipt; stock is valued at the PO rate.
3. **Bills.** Vendor bill against the PO or receipt. Forwarder and broker bills with service items, linked on the cost lines.
4. **Land it.** When every included cost has its bill (or tick "allow estimates"), **Draft LCV** builds the voucher: one charge row per included cost type, allocation basis from settings. It refuses unsubmitted receipts, lines with no account, and mixed bases (one basis per voucher; use Manual). Check the distribution, submit in the desk. ERPNext revalues the items (a short delay while it reposts).
5. **QuickBooks.** The LCV is not sent. True up QuickBooks inventory periodically with the **landed cost in stock** figure.

**What's included by default:** freight (by qty, est. 8%), MPF / HMF (est. 0.4%), duty, additional tariff, brokerage, insurance (by value), drayage (by qty). **Not capitalised:** storage / demurrage, sales / use tax, other. Change per cost type in ilL-Purchasing-Settings.

**Landed cost tab:** what still needs a voucher (with missing bills, e.g. "Duty bill not in yet") and **Draft LCV**; recent vouchers; landed cost by item (purchase rate, landed rate, uplift %, 12-month average; Copy as text); **landed cost in stock** total.

📸 **SS-08-12** · Landed cost tab: needs-voucher list with "Duty bill not in yet"
📸 **SS-08-13** · Draft LCV from the board (desk form): charge rows and distribution
📸 **SS-08-14** · LCV refused: mixed allocation bases message
📸 **SS-08-15** · Landed cost by item table and the landed-cost-in-stock total
📸 **SS-08-16** · ilL-Purchasing-Settings cost type rules

🔌 **DATA-08-02** · A real delivered inbound shipment with estimates vs actuals (worked example)
**API:** `GET /api/resource/ilL-Inbound-Shipment?filters=[["status","in",["Delivered","Costs final"]]]&fields=["name","supplier","freight_mode","goods_value","landed_cost_pct"]&limit_page_length=5` then `GET /api/resource/ilL-Inbound-Shipment/<name>`

---

## Slide deck beats

1. Who holds what: ERPNext vs QuickBooks
2. Entering a bill and the 3-way match chip
3. Forwarder and broker bills on cost lines
4. Bills into QuickBooks, and how to spot one that didn't make it
5. Pay in QuickBooks; ERPNext follows
6. Reading the sync log and fixing failures
7. Landed cost in five steps
8. The quarterly QuickBooks inventory true-up

## Check yourself

1. Where do you record a vendor payment?
2. A bill has no QuickBooks chip after an hour. Where do you look?
3. The 3-way match chip says `price_off`. Can you still submit? Should you?
4. Why might Draft LCV refuse to build a voucher?
5. A QuickBooks payment applied a vendor credit. What do you do in ERPNext?
