# ilLumenate Staff Training: Outline Set

A shared copy lives in Claude Docs: [ilLumenate Staff Training Outline](https://claude.ai/artifact/FaKD1XWDgfwxqFn9kouLEx). Keep this folder and the doc in step: change one, change the other.

This folder holds the training **outlines** for every area of the Command Center ERP and the third-party apps around it. Each module is an outline with screenshot prompts and data-pull prompts. A second pass (the "capture bot") runs a local ERPNext instance, takes the screenshots, pulls real-world examples through the API, and turns each outline into a manual chapter and a slide deck.

Every fact here was taken from the code and docs in this repo as of 2026-11-22 (branch `claude/brave-newton-yw7nr8`). Where a feature is built but has not run live yet, the outline says so. Teach it as "coming", or capture it on staging only.

## Modules

| # | Module | Primary audience |
|---|---|---|
| 01 | [Command Center orientation](01_COMMAND_CENTER_ORIENTATION.md) | Everyone |
| 02 | [Design, tickets & tasks](02_DESIGN_TICKETS_TASKS.md) | Sales, applications engineering, support |
| 03 | [Quotes](03_QUOTES.md) | Sales, sales review |
| 04 | [Sales orders](04_SALES_ORDERS.md) | Sales review, order approvers, operations |
| 05 | [Manufacturing](05_MANUFACTURING.md) | Production lead, floor staff, operations |
| 06 | [Shipping, delivery notes & tracking](06_SHIPPING_DELIVERY_TRACKING.md) | Shipping/warehouse, operations, sales (tracking questions) |
| 07 | [Purchasing & receiving](07_PURCHASING_RECEIVING.md) | Buyer, receiving, operations |
| 08 | [Vendor bills, payments & landed cost](08_AP_VENDOR_PAYMENTS_LANDED_COST.md) | Accounting (Charlotte), buyer |
| 09 | [Invoicing, receivables & finance](09_INVOICING_AR_FINANCE.md) | Accounting, owner |
| 10 | [Service & dealer portal administration](10_SERVICE_DEALER_PORTAL_ADMIN.md) | Support, sales, accounts |
| 11 | [Catalog, products & publishing](11_CATALOG_PRODUCTS_PUBLISHING.md) | Catalog publisher, engineering, marketing/web |
| 12 | [HR self-service](12_HR.md) | Everyone (employee), HR lead, approvers |
| 13 | [Integrations & third-party apps](13_INTEGRATIONS_THIRD_PARTY.md) | Admin, accounting, shipping lead, marketing |

## Learning paths by role

Take Module 01 first. Then:

| Role | Required modules | Optional |
|---|---|---|
| Owner / executive | 01, 02, 03, 04, 09, 10 | all |
| Sales / sales review (ilL Sales Review) | 02, 03, 04, 10 | 06 (tracking questions), 11 (finder, spec sheets) |
| Order approver (ilL Order Approver) | 03, 04, 05 (lesson 1) | 06 |
| Applications engineering (ilL Engineering, ilL Applications Engineer) | 02, 03 (configurators), 05 (drawing holds), 11 | 04 |
| Support (ilL Support) | 02 (Inbox), 10, 06 (tracking lessons) | 04 |
| Production lead / floor (Manufacturing User/Manager) | 05, 06 (lessons 1-3) | 07 (receiving) |
| Shipping / warehouse (Stock User/Manager) | 06, 07 (receiving lessons), 05 (Flow tab) | 13 (EasyPost) |
| Buyer (Purchase User/Manager) | 07, 08 | 05 (waiting for parts), 13 (purchasing mailbox) |
| Accounting (Accounts User/Manager, Command Center Finance) | 08, 09, 13 (QuickBooks) | 07 |
| Catalog publisher / marketing & web (ilL Catalog Publisher) | 11, 13 (Webflow, n8n) | 03 (configurators) |
| HR lead | 12 | 10 (role audits) |
| Systems administrator (System Manager) | all, plus 13 in full | |

## Conventions for the capture bot

### Screenshot prompts

Each prompt looks like this:

> **SS-06-14** · Shipment form, submitted, "Create Labels" button visible
> **URL:** `/app/shipment/<name>` · **Role:** Stock User · **State:** submitted Shipment with 2 parcels, Label Status "Not bought"
> **Highlight:** the Create Labels button; the Label Status field
> **Data:** use the DN from DATA-06-02

- **IDs** are `SS-<module>-<sequence>`. Name the image file the same (`SS-06-14.png`) so the manual can reference it.
- **URL** is relative to the site root. `<name>` means pick a real record that matches the **State**.
- **Role** is the role to sign in as. It matters: buttons, tabs and dollar figures change by role. The Command Center hides dollars without the Finance role.
- **Highlight** is what to box or arrow in the final image.
- Take screenshots at 1440×900, deviceScaleFactor 2, light theme, unless the prompt asks for a phone width (390×844).
- When a prompt says **(pair)**, take two images (before and after an action) and suffix them `-a` and `-b`.

### Data-pull prompts

> **DATA-06-02** · A real delivery note shipped last week with a tracking number
> **API:** `GET /api/resource/Delivery Note?filters=[["docstatus","=",1],["ill_tracking_number","is","set"]]&fields=["name","customer","ill_carrier","ill_tracking_number","posting_date"]&order_by=posting_date desc&limit_page_length=5`
> **Use:** the worked example in Lesson 06.4

- Use these to pick realistic records for screenshots and worked examples, and to seed the local instance.
- **Redact before publishing:** dealer contact names, emails, phone numbers, street addresses, bank details and pricing for named customers. Keep company names only if the owner approves. Replace with "Sample Dealer A" and so on when in doubt.
- Never write to production. Read-only `GET` calls only. Do all create/submit walkthroughs on the local instance.
- **Check field names first.** The custom field names in the API examples come from the code (`ill_*`, `custom_qbo_id`), but confirm each against the doctype before relying on it: `GET /api/method/frappe.desk.form.load.getdoctype?doctype=<DocType>`. Adjust the query if a field differs.
- **One job, end to end.** DATA-02-01 picks one real fixture schedule that went all the way to a shipped, invoiced order. Reuse that job (its project, quote, sales order, work orders, delivery note, shipment, invoice) as the running example in Modules 02-09, so trainees follow the same job through every stage.

### Status labels

| Label | Meaning | How to train it |
|---|---|---|
| Live | Live and in use | Train normally |
| (Rolling out) | Built, not yet piloted on the live site | Capture on the local instance; label the slide "Rolling out". Re-check before publishing |
| (Planned) | Planned only, not built | Mention as "coming"; no screenshots |
| (Restricted) | Restricted to certain roles | Say which roles in the slide |

### Each module's shape

1. **Purpose and audience**
2. **Where to go**: Command Center routes, desk URLs, portal pages
3. **Lessons**: objective, steps, screenshot prompts, data-pull prompts, gotchas
4. **Slide deck beats**: the 6-10 slides the presentation needs
5. **Check yourself**: 4-6 questions for the end of the session

### Capture environment checklist

Before capturing, the local instance needs:

- [ ] The `illumenate_lighting` app installed and migrated (this runs `command_center_sync.py`, so `/command-center` exists).
- [ ] Frappe Helpdesk, Frappe HRMS and Frappe CRM installed (optional in `hooks.py`, but Modules 02, 10, 12 and 13 need them).
- [ ] One test user per role in the learning-path table, plus a **Dealer** portal user linked to a sample Customer through a Contact.
- [ ] Command Center roles: one user with Viewer only, one with Editor, one with Editor + Finance (to show the dollar/no-dollar difference).
- [ ] Sample data seeded from the API pulls: 2-3 projects with fixture schedules, quotes in several states, sales orders across stages, work orders, purchase orders, an inbound shipment, receipts, bills.
- [ ] ilL-Shipping-Settings filled in with an **EasyPost test key** in n8n (or labels left as "Label error" screenshots only). Never use the live key.
- [ ] ilL-QBO-Settings left disabled on the local instance. Capture the QBO sync log from sample entries.
- [ ] Browser localStorage cleared before each module, because the Command Center remembers the last tab per browser.

## Decisions to make before publishing the manual

The open decisions and my recommendation for each are in [DECISIONS.md](DECISIONS.md): invoice timing, automatic emails, Helpdesk ticket types, drawing request types, EasyPost go-live, QuickBooks rollout, label printer, role mapping, Finance tab visibility, portal support routing, and desk quotes.

## Known gaps to keep out of the manual (or flag)

- The Finance tab and the finance figures on the Sales pipeline page show to every Command Center Viewer (older data feed). Don't publish those screenshots outside the company.
- Plain desk Quotations don't mark the schedule QUOTED or create a portal offer; only quote-request quotations do. The manual must say this plainly (Module 03).
- Tape / neon and LED sheet lines get no automatic work orders (Module 05).
- `docs/DEMO_SCRIPT.md` and `docs/CONFIGURATOR_UI_IMPROVEMENTS_PLAN.md` are out of date. Don't use them as sources.
- The Command Center README still says "production status override"; the field is now **Stage Override**.
