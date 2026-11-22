# Module 09: Invoicing, receivables & finance

**Audience:** accounting, owner. **Length:** 60-75 minutes.
**Roles used:** Accounts User / Manager, Command Center Finance.

## Purpose

Trainees can invoice an order (deposit, proforma or after shipping), get the invoice and its pay link to the dealer, follow receivables, record customer payments the right way (in QuickBooks), and read the Finance tab and commission reports.

> **Status:** several pieces are not switched on yet: invoice email Notifications are disabled, the company "Invoice Payment Instructions" field is empty, and no live invoice has a QuickBooks pay link yet (Rolling out). Train the flow; mark these slides "Rolling out".

## Where to go

| What | Where |
|---|---|
| Finance tab | `/command-center#finance` (Restricted) |
| New sales invoice | `/app/sales-invoice/new` |
| Sales invoices | `/app/sales-invoice` |
| Accounts Receivable report | `/app/query-report/Accounts Receivable` |
| Payment entries | `/app/payment-entry` |
| QuickBooks sync log | `/app/ill-qbo-sync-log` |
| Sales partners (reps) | `/app/sales-partner` |
| Commission reports | Sales Partner Invoice Report; Sales Team Commissions |

---

### Lesson 9.1: When to invoice

| Situation | Invoice | Notes |
|---|---|---|
| Deposit / prepay before production | From the SO, template "Order confirmation and invoice" | Deposit = first open row of the SO payment schedule |
| Proforma (pay before shipping) | From the SO | Order stays "Proforma - Awaiting Payment" until paid |
| Standard, after shipping | **Delivery Note → Create → Sales Invoice** | Working assumption: one invoice per delivery note (confirm with finance) |

- Invoicing moves the order stage to **Completed** once fully billed.
- Credit notes: a return invoice prints as "Credit Note".

**SS-09-01** · Delivery note → Create → Sales Invoice menu
**SS-09-02** · Sales invoice form created from a delivery note
**URL:** `/app/sales-invoice/<name>`

---

### Lesson 9.2: The invoice the dealer receives

- Print **ilL Sales Invoice**: payments received, a "How to pay" box with the **QuickBooks pay link** and the company's payment instructions.
- On submit, n8n creates the QuickBooks Customer and Invoice and writes the QuickBooks id and pay link back (`custom_qbo_id`, pay link).
- **Notifications** (all created **disabled**): invoice 1 day after invoice date (gives time for the pay link), reminder 3 days before due, past due at 1 / 15 / 30 days, payment received.
- Manual templates: Paid in full receipt, Credit note.
- Dealers see invoices with outstanding balance on `/portal/orders/<SO>`.

**SS-09-03** · ilL Sales Invoice print preview with the How to pay box
**SS-09-04** · Invoice showing QuickBooks id and pay link fields
**SS-09-05** · Notification list filtered to Sales Invoice (showing disabled)
**URL:** `/app/notification?document_type=Sales Invoice`
**SS-09-06** · Dealer order page Invoices section
**Role:** Dealer

---

### Lesson 9.3: Customer payments

1. Record the payment in **QuickBooks** (Receive Payment), not in ERPNext.
2. QuickBooks → n8n → ERPNext creates a **Receive** Payment Entry against the invoice(s), matched by QuickBooks id. One payment across several invoices = one Payment Entry, several references.
3. Check the sync log (Module 08, Lesson 8.4 has the failure table). Most common: `invoice_not_matched` (the invoice never got its QuickBooks id).
4. Still manual: payments applying a credit memo, and one line linked to several invoices.

- Print **ilL Payment Receipt** shows the QuickBooks reference.
- Deposits paid move proforma orders on; the stage refreshes on Payment Entry.

**SS-09-07** · Receive Payment Entry synced from QuickBooks
**SS-09-08** · ilL Payment Receipt print preview

---

### Lesson 9.4: Receivables and the Finance tab

- **Finance tab** (owner: Charlotte): invoiced this month vs break-even and on-pace target; receivables outstanding; invoiced by month; customer concentration; aging table. Quick links to invoices, AR report, payment entries, bills, QuickBooks sync log.
- The "Cash · payables · margin" tile is not built yet ("Needs a QuickBooks export") (Planned).
- **Known gap:** the Finance tab's figures currently show to every Command Center Viewer. Don't screenshot it for anyone outside the company.
- **Accounts Receivable report** for collections; Executive tab "overdue invoices" decision.

**SS-09-09** · Finance tab, full page
**URL:** `/command-center#finance` · **Role:** CC Finance
**Highlight:** invoiced vs break-even; aging table
**SS-09-10** · Accounts Receivable report with ageing buckets

**DATA-09-01** · Invoiced per month, last 6 months (for the trend slide; keep totals only, no customer names)
**API:** `GET /api/resource/Sales Invoice?filters=[["docstatus","=",1],["posting_date",">","<6 months ago>"]]&fields=["posting_date","grand_total"]&limit_page_length=0`

---

### Lesson 9.5: Commissions and reps

- Reps are native **Sales Partners**. The SO's total commission feeds the board's commission % (red above 22%) and worth per point.
- **Sales Partner Invoice Report**: invoices by partner and date.
- **Sales Team Commissions**: by sales person; defaults to **paid** invoices last month.
- Overview stage shows **SPIF candidates** ($3K+ orders since Oct 1, with the rep).
- Reps never print on customer documents.

**SS-09-11** · Sales Team Commissions report, last month
**SS-09-12** · SPIF candidates panel on `#pipeline`

---

## Slide deck beats

1. Three moments to invoice
2. The invoice and the pay link
3. Payments: record in QuickBooks; ERPNext follows
4. The sync log and the usual failure
5. Finance tab and AR report
6. Commissions and SPIFs

## Check yourself

1. The dealer paid in QuickBooks but the invoice is still unpaid in ERPNext. What do you check first?
2. Which document do you invoice from after shipping?
3. Why does the invoice email wait one day after the invoice date?
4. Where do you see which reps earned commission last month?
