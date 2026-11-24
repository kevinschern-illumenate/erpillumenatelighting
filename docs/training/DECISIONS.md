# Decision recommendations

Settle decisions 1, 2, 3 and 8 by 30 Nov 2026. The training sessions depend on them, and none needs any building. The EasyPost and QuickBooks dates (5, 6) set when Modules 06, 08 and 09 lose their "Rolling out" labels.

**Decided 22 Nov:** 4, 8 and 11, plus the open questions. Three code changes they needed are built and tested: drawing request SLAs now skip weekends; the accounting queues follow the Accounts roles; and staff can raise a quote request for a dealer.

| # | Decision | Recommendation | Decide by |
|---|---|---|---|
| 1 | Invoice timing | One invoice per delivery note; prepay and proforma orders invoiced in full from the sales order | 2026-11-30 |
| 2 | Automatic emails | Turn on order confirmation, shipped and PO chase now; invoice emails after QuickBooks pay links work; keep quote and ship-date emails off | 2026-11-30 |
| 3 | Helpdesk ticket types | The five types the Command Center expects, routed to three teams; 10 starter knowledge base articles | 2026-11-30 |
| 4 | Drawing request types | Decided: six types plus System Design Review; SLA counts weekday hours only (built) | 2026-12-04 |
| 5 | EasyPost go-live | Staging test the week of 30 Nov, live parcel-only pilot 7-18 Dec, full go-live 4 Jan 2027 | 2026-12-04 |
| 6 | QuickBooks rollout | Sandbox test in December, cut over on 1 Jan 2027, invoice emails once 5 live invoices carry pay links | 2026-12-11 |
| 7 | Label printer | 4x6 direct thermal printer; ask for the label size to be set to 4x6 in the n8n workflow | 2026-12-04 |
| 8 | Who holds which role | Decided: mapping below. Kevin is Systems Administrator; Kevin and Jay produce drawings and review designs | 2026-11-30 |
| 9 | Finance tab visibility | Restrict it to the Finance role before Module 01 is taught | 2026-11-30 |
| 10 | Portal support vs Helpdesk | Short term: check the queue daily. Later: send portal support into Helpdesk | 2026-12-11 |
| 11 | Desk quotes and the schedule | Decided: staff raise quote requests for dealers from the schedule (built) | 2026-11-30 |

---

## 1. Invoice timing

**Recommendation:** for Net 30 customers, create one sales invoice per delivery note on the day it ships. Invoice prepay and proforma orders in full from the sales order, and add a payment schedule if a deposit applies (deposit due now, balance before shipping).

**Why:**
- Partial shipments bill what actually shipped, and the dealer's invoice matches the packing slip in the box.
- ERPNext maps delivery note to invoice in one click, and billing is what moves an order's stage to Completed.
- **Payments only sync from QuickBooks when they match an invoice.** A deposit taken with no invoice behind it fails with `invoice_not_matched`. So deposits must be invoiced, not recorded as loose advances.
- One full invoice with a payment schedule avoids deposit line items, and the order stays "Proforma - Awaiting Payment" until it is paid in full.

## 2. Automatic emails

| Email | Recommendation | Reason |
|---|---|---|
| Order confirmation on SO submit (ilL-Email-Settings) | **On now** | It skips addresses the portal already emails and never sends twice |
| Shipped email to the delivery note contact (ilL-Email-Settings) | **On now**; leave "Also email dealer portal users" off | Portal buyers already get their own shipped email. Rule: tracking goes on the delivery note before it is submitted |
| PO confirmation chase to vendor (3 days) | **On** once the purchasing@ mailbox is set up | It does a buyer's follow-up for them |
| Delivered email (ilL-Shipping-Settings) | **On at EasyPost go-live** | Needs automatic tracking |
| Delivery check-in (5 days after shipping) | **Hold** until shipped emails have run cleanly for 2 weeks | It goes out after every shipment, including partials, so repeat dealers get many |
| Invoice (+1 day), payment reminder (−3 days), past due 1 and 15 days, payment received | **On once QuickBooks pay links are verified** on 5 live invoices and the company payment instructions are filled | Without a pay link the invoice email is incomplete |
| Past due 30 days | **Off.** Charlotte calls instead | At 30 days a person should reach out |
| Quote follow-up (+3), expiring (−7), expired (+1) | **Off** | Portal offers already remind buyers 3 days and 1 day before expiry. Sales follows up personally from the quote's Follow Up stage |
| Ship date update | **Off.** Send the manual "Ship date changed" template | The floor moves estimated ship dates for internal planning; automatic emails would expose every reshuffle |

Before switching anything on, check the full list at `/app/notification`. My list came from the email templates doc, and the site may have more.

## 3. Helpdesk ticket types and teams

| Ticket type | Use for | Team |
|---|---|---|
| Quotation | Pricing, quote requests, revisions | Sales |
| Sales Order | Order status, changes, ship dates, tracking questions | Sales (operations as backup for tracking) |
| Design | Drawings, layouts, technical and product-fit questions | Engineering |
| Service | After delivery: damage, defects, warranty, returns | Support |
| Issue | Default catch-all. Retype within one business day from the Routing view | Support |

**Starter knowledge base (10 articles):** how to request a quote; how to read your quote and accept it online; order status and tracking; requesting drawings; using the configurators; spec sheets and submittal packages; returns and damage claims; warranty; account access and pricing visibility; paying an invoice (pay link).

## 4. Drawing request types

Only "System Design Review" exists today, so the portal's drawing request form says requests are unavailable. Create these at `/app/ill-request-type`:

| Type | Category | SLA hours (Normal / High / Rush) | Default assignee | Auto-create task |
|---|---|---|---|---|
| Shop / submittal drawing | Drawing | 72 / 48 / 24 | ilL Engineering role (least loaded) | Yes |
| Manufacturing approval drawing (tick "required for manufacturing" on each request) | Drawing | 72 / 48 / 24 | ilL Engineering role | Yes |
| Layout / run plan | Drawing | 120 / 72 / 48 | ilL Engineering role | Yes |
| Photometric / lighting calculation | Technical | 120 / 72 / 48 | ilL Applications Engineer role | Yes |
| Technical question | Technical | 48 / 24 / 8 | ilL Applications Engineer role | No |
| Spec sheet, IES or CAD file | Resource | 24 / 8 / 4 | ilL Engineering role | No |
| System Design Review (exists) | — | 16 / 8 / 4 | ilL Applications Engineer role | as set |

**Decided:** SLA hours count weekdays only. **Built:** deadlines now skip Saturdays and Sundays (Friday 4 pm plus 24 hours is Monday 4 pm). Dates on the company's default holiday list are skipped too. **To do:** on production and staging the Company has no Default Holiday List yet (a "2026" list exists, 1 Jul to 31 Dec 2026), so today only weekends are skipped. Set Company → Default Holiday List, and add a 2027 list before January.

## 5. EasyPost go-live

**Recommendation:** go live in stages, gated on criteria rather than a fixed date.

1. **Week of 30 Nov:** finish Phase 0. Connect the EasyPost and FedEx accounts, get test keys, confirm the FedEx surcharge thresholds against our agreement, buy the label printer (decision 7). Run the full flow on staging with the test key.
2. **7-18 Dec, live pilot:** Ryan buys labels in ERPNext for parcel-only orders. Freight and anything unusual stays manual.
3. **Go-live criteria:** 20 live labels bought with no error; at least one void and refund; tracking updates arriving on their own; dealers getting shipped emails with tracking.
4. **4 Jan 2027, full go-live** if the criteria are met. Starting after the holiday rush avoids changing the shipping process during the busiest weeks.

Until then, Module 06 teaches the manual label process as the main path.

## 6. QuickBooks rollout

1. **Now:** fill in the company's Invoice Payment Instructions (they print on every invoice).
2. **December:** a sandbox test end to end: bill push, bill payment, invoice push with pay link, customer payment. Register the Intuit webhook and set the shared secret.
3. **1 Jan 2027 cutover:** set "Send Bills Posted On or After" to 1 Jan 2027. From that date bills are entered in ERPNext only, never typed into QuickBooks too. A year boundary keeps 2026 close untouched and stops bills Charlotte already entered in QuickBooks from being duplicated.
4. **Mid-January:** turn on invoice emails once 5 live invoices carry pay links (decision 2).
5. **End of Q1 2027:** first landed-cost true-up of QuickBooks inventory, using the "landed cost in stock" figure.

## 7. Label printer

**Recommendation:** a 4x6 direct thermal printer with USB (Zebra ZD421d class, or a Rollo as the cheaper option), plus the office laser on letter paper as a fallback.

- FedEx labels from EasyPost are 4x6.
- The n8n workflow asks EasyPost for PDF labels but doesn't set a size. Ask for the label size to be set to 4x6 explicitly so labels print 1:1.
- ERPNext opens one merged PDF per shipment, so any printer that prints PDFs from the browser works; set the printer's paper to 4x6.

## 8. Who holds which role

This proposal is based on who owns what today (from Kevin's Desk) and the roles the Command Center already seeds. Each person also keeps the standard ERPNext roles for their job.

| Person | Owns today | ilL and Command Center roles | Standard ERPNext roles |
|---|---|---|---|
| Kevin | Owner; Systems Administrator; drawings and system design review | System Manager; Command Center Viewer, Editor, Finance; ilL Order Approver; ilL Catalog Publisher; ilL Engineering; ilL Applications Engineer; approves the HR lead's leave and expenses | All needed |
| Jay | Sales calls, standard quotes, dealer relationships; drawings when needed | ilL Sales Review; ilL Order Approver (backup to Kevin); ilL Support; ilL Engineering; ilL Applications Engineer; Command Center Editor, Finance; Helpdesk agent | Sales User |
| Charlotte | Invoicing, payments, AP/AR, QuickBooks; HR lead | Command Center Viewer, Finance, **plus Editor** (not seeded today; she needs it for Draft bill and Draft LCV); HR Manager; Leave and Expense Approver | Accounts Manager (now also opens the Accounting queues in Portal Operations), Purchase User |
| Ryan | Production, warehouse, shipping, purchasing, vendors | Command Center Editor; ilL Operations | Manufacturing Manager, Stock Manager, Purchase Manager |
| Regina | Branding, sales docs, eblasts, spec sheet layout | ilL Catalog Publisher; Command Center Editor | Website Manager if she edits web pages |

**Decided:**
- **Drawings and system design review:** Kevin and Jay, as internal staff (ilL Engineering and ilL Applications Engineer). A dealer pilot of the System Designer and CAD import comes later; when it starts, add the pilot customers in ilL-System-Designer-Settings and the CAD pilot list.
- **Accounting queues:** built. "Bills not in QuickBooks" and "New customers to set up" now follow the Accounts Manager and Accounts User roles, under a new Accounting section in Portal Operations. Dealer account requests stay with Sales and Support, so Charlotte isn't auto-assigned applications she can't approve.
- **Systems Administrator:** Kevin Schern.

## 9. Finance tab visibility

**Recommendation:** before Module 01 is taught, add the Finance role check to the older "ilL Command Center API" server script. Until then, hide the Finance tab from users without the Finance role. Today every Command Center Viewer sees invoiced totals and receivables.

## 10. Portal support vs Helpdesk

**Recommendation:** in the short term, Jay checks Portal Operations → Support responses every morning alongside the Inbox. Later, have portal support create Helpdesk tickets, so there is one inbox and one set of ticket types.

## 11. Desk quotes and the schedule

**Decided and built:** staff can raise a quote request on a dealer's behalf. On a DRAFT or READY schedule, **Actions → Request Quote for Dealer** (sales roles) asks for what the dealer wants, contact instructions and a needed-by date, then opens the new request. From there it is the normal path: Prepare Quotation, submit, and the dealer gets an offer they can accept online. The request's timeline records who raised it. Desk-only quotes remain for customers who don't use the portal.

**Why not switch on the existing "mark QUOTED on submit" hook:** it would mark the schedule QUOTED without creating an offer. The dealer couldn't accept online, and their schedule would version the next time they edit it.

Train it as the rule: every quote for a portal dealer's schedule starts as a quote request, whether the dealer asks in the portal or by phone or email (Module 03, Lesson 3.2).

## Findings from the 24 Nov review (need an owner decision)

Found while expanding the modules and checking staging and production read-only. Nothing below was changed on either site.

| # | Finding | Where | Recommendation |
|---|---|---|---|
| F1 | The Dealer role can create, edit, cancel and amend **Sales Invoice** and **Packing Slip**, with no company filter (manual permission rows, 9 Mar 2026). The portal reads both in code and does not need them. | Production and staging | Remove the Dealer row from both in Role Permissions Manager. Review the other unscoped Dealer rows too (ilL-Configured-Fixture, Item). |
| F2 | The Company has no Default Holiday List, so SLA and production dates skip weekends only. The "2026" list covers Jul to Dec and labels 12 Jul as Saturday. | Production and staging | Fix the list, set it as the default, add 2027 before January. |
| F3 | Portal Routing Settings has no queue rows, so quote and order requests get no due date. | Staging (check production) | Fill in the routing table before training staff on due dates. |
| F4 | "Quote ready" emails only the schedule's creator. Staff-created schedules never notify the dealer. | Code | Fix queued as a separate task; until then staff tell the dealer. |
| F5 | Landed-cost defaults mix "By qty" and "By value", so Draft LCV refuses shipments with both freight and duty. | Settings | Pick one basis (recommend By value for duty, then set freight the same). |
| F6 | An empty cost line's actual is read as $0 billed, hiding "bill not in yet" chips. | Code | Fix queued as a separate task. |
| F7 | ilL-QBO-Settings on staging has no accounts, bill webhook or cutover date; every BillPayment in the log failed. | Staging | Part of decision 6 (QuickBooks rollout). |
| F8 | ilL-Shipping-Settings has never been saved; no parcel templates; EasyPost workflows not imported into n8n. | Staging | Part of decision 5 (EasyPost go-live). |
| F9 | No purchasing@ Email Account on staging; the gallery sync webhook URL is incomplete (404); Postmark campaign workflows still active in n8n. | Staging / n8n | Tidy before training Module 13. |
| F10 | Accounts-only users could not open Portal Operations. | Code | Fixed 24 Nov (237c344); live after the next deploy. |
