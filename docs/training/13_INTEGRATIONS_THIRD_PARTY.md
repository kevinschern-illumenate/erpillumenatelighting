# Module 13: Integrations & third-party apps

**Audience:** systems administrator (all lessons); accounting (13.3); shipping lead (13.2); marketing & web (13.4); everyone (13.1 overview). **Length:** 30 minutes overview + 30 minutes per role lesson.
**Roles used:** System Manager, Accounts Manager, Stock Manager, ilL Catalog Publisher.

## Purpose

Everyone understands which outside systems the ERP talks to and what they themselves must do in each. Admins and leads can check that each integration is healthy and fix the common failures.

## Map of the systems

| System | What it does for us | Who touches it | Status |
|---|---|---|---|
| **ERPNext (Frappe v16)** | Core ERP: quotes, orders, stock, manufacturing, purchasing, accounting | Everyone | Live |
| **Command Center** | The staff cockpit on top of ERPNext | Everyone | Live |
| **Dealer portal** | Dealers' projects, quotes, orders, drawings | Dealers; staff for support | Live |
| **Frappe Helpdesk** | Customer tickets (sales@) | Support, sales | Live |
| **Frappe CRM** | Website leads → deals → customers | Sales, marketing | Live |
| **Frappe HRMS** | Leave, expenses | Everyone | Live |
| **n8n** | The integration hub: every outbound connection goes through it | Admin | Live |
| **QuickBooks Online** | Payables and receivables system of record; payments | Accounting | Rolling out: setup steps pending |
| **EasyPost (FedEx)** | Shipping labels and tracking | Shipping | Rolling out: not piloted |
| **Webflow** (ilLumenate, 206 Lighting) | Public websites and product listings | Marketing & web, catalog publisher | Live (auto-push and galleries gated) |
| **Gmail / Google** | Kevin's Desk email triage (metadata only) | Kevin | Live |
| **Postmark campaigns** | Email campaigns | Marketing | Dormant (scheduler removed) |
| **Bluebeam** | Drawing markup (spike only) | — | Planned |

---

### Lesson 13.1: How the pieces connect (everyone)

- ERPNext sends events to **n8n**; n8n talks to QuickBooks, EasyPost, Webflow and the spec sheet renderer, then writes results back to ERPNext.
- Each outside system writes into ERPNext as its own **service user** (shipping-integration, qbo-integration, webflow-auto-push, publication-worker), so changes on the timeline are labelled by source.
- If something "didn't sync", the answer is usually in a log: Error Log, ilL-QBO-Sync-Log, Publish Jobs, or the n8n execution list.

**SS-13-01** · n8n workflow list showing the ilL workflows
**URL:** n8n editor · **Role:** n8n admin
**SS-13-02** · A record timeline showing a change by a service user

---

### Lesson 13.2: EasyPost (shipping lead, admin) (Rolling out)

- Workflows: **ilL Shipping: EasyPost labels** (rate, buy, void) and **EasyPost tracker → ERPNext** (tracking events).
- The EasyPost API key lives **only in n8n**. Use a test key on staging.
- ERPNext side: ilL-Shipping-Settings (Module 06, Lesson 6.9).
- **Setup order:** migrate → warehouse address and box templates → EasyPost account and FedEx connection → n8n workflows and variables → settings → permissions → test.
- **Health checks:** Label Status "Error" on Shipments; "Shipping exception" emails; n8n executions for failed runs.
- **Phase 0 to finish before go-live:** staging spike, connect EasyPost and FedEx accounts, test keys, confirm FedEx surcharge thresholds, choose label printer (decisions 5 and 7).

**SS-13-03** · n8n EasyPost labels workflow canvas
**SS-13-04** · EasyPost dashboard: a test shipment (test mode)

---

### Lesson 13.3: QuickBooks Online (accounting, admin) (Rolling out)

| Direction | What | How |
|---|---|---|
| ERPNext → QuickBooks | Sales Invoice → QBO Invoice (+ pay link back) | n8n workflow (live, not in the repo) |
| ERPNext → QuickBooks | Purchase Invoice → QBO Bill; cancel deletes | `purchase_invoice_qbo_bill` workflow; hourly retry |
| QuickBooks → ERPNext | Customer Payment and Bill Payment → Payment Entry | Intuit webhook → `quickbooks_payment_sync` workflow |
| Not synced | Landed cost vouchers (true up QuickBooks inventory periodically); HR expense reimbursements (mark paid by hand) | |

- **Rules for staff:** record payments in QuickBooks; never type a payment in ERPNext unless the sync log says it's a manual case.
- **Health checks:** ilL-QBO-Sync-Log (Failed rows), Error Log "QBO bill push failed", Portal Operations → Bills not in QuickBooks, `bill_not_in_qbo` decision.
- **Settings:** ilL-QBO-Settings (sync enabled, secret, paid-to / paid-from accounts, mode of payment, bill webhook URL, bills-from date).
- **Rollout steps still open** (decision 6): deploy confirmation, settings secret, Intuit webhook registration, sandbox end-to-end test, go-live; company invoice payment instructions; enable invoice Notifications.

**SS-13-05** · ilL-QBO-Settings form (secret masked)
**SS-13-06** · n8n QuickBooks payment sync workflow canvas
**SS-13-07** · QuickBooks bill showing the ERPNext bill number as DocNumber (sandbox)

---

### Lesson 13.4: Webflow and n8n publishing (marketing & web, catalog publisher)

- **Product sync** (per brand): claims publish jobs from ERPNext and stages, publishes or retires items.
- **Attribute, category and product filter syncs**: every 6 hours plus manual runs.
- **Gallery sync**: started from ERPNext (Rolling out; staging run pending).
- **Lead forms**: Webflow form → Frappe CRM Lead, one workflow per brand.
- **Spec sheets**: ERPNext → n8n renderer → PDF attached.
- **Health checks:** Publish Job list, Portal Operations → Publication failures, failure notifications. A read-only drift check tool exists (`tools/reconcile_webflow.cjs`) but hasn't been run against the live site.

**SS-13-08** · n8n Webflow product sync workflow canvas
**SS-13-09** · Webflow CMS item updated by the sync (staging site)

---

### Lesson 13.5: Frappe apps (Helpdesk, CRM, HRMS)

- **Helpdesk** (`/helpdesk`): tickets with ilL link fields; six "ilL - …" saved replies. Ticket types (Quotation, Design, Sales Order, Service, Issue), teams and the knowledge base are configured in Helpdesk itself (decision 3).
- **CRM** (`/crm`): leads from Webflow; job titles from ilL-Job-Title-Master (System Manager edits); Won deal → ERPNext Customer.
- **HRMS** (`/hrms`): Module 12.

**SS-13-10** · Helpdesk saved replies list
**SS-13-11** · CRM deal marked Won and the created Customer

---

### Lesson 13.6: Email setup and templates (admin)

- **43 Email Templates** named "ilL - <DocType> - <purpose>". Keep "Use HTML editor" on. Restore the shipped wording with `email_templates.seed.restore`.
- **13 Notifications**, all shipped **disabled**. Enable each with a Sender when the team is ready (decision 2).
- **ilL-Email-Settings:** automatic order confirmation and shipped emails (off by default), dealer-portal copy switch, will call pickup address and hours, purchasing mailbox.
- **Mailboxes:** sales@ (Helpdesk / shared inbox), purchasing@ (purchasing documents, auto-linking).
- Portal emails go through an outbox sent every 5 minutes; failures show in Portal Operations → Email failures.

**SS-13-12** · Email Template list filtered "ilL -"
**SS-13-13** · Notification list showing disabled ilL notifications
**SS-13-14** · ilL-Email-Settings

---

### Lesson 13.7: Roles reference (admin)

| Role | Unlocks |
|---|---|
| Dealer | Portal only, own company |
| ilL Sales Review | Quotations (submit / amend / cancel), SO create / write, projects and schedules, order intake read; Request Quote for Dealer; sales, account review and inbox queues |
| ilL Order Approver | Sales Review + SO submit / cancel / amend |
| ilL Engineering | Drawing requests, tasks, export jobs; authoring specs, attributes, templates, submittal mappings |
| ilL Applications Engineer | System Designer design review |
| ilL Catalog Publisher | Engineering authoring + Item, Item Price, Webflow; Catalog Builder; CC Catalog tab |
| ilL Support | Issue queue, account requests, sales inbox |
| ilL Operations | Drawing holds (read), materials to order |
| ilL Product Finder Manager | Finder content and verification |
| ilL Integration | Service users only |
| Command Center Viewer / Editor / Finance | Read / write / dollars in the Command Center |
| Accounts Manager / Accounts User (standard ERPNext) | Also open the Accounting queues in Portal Operations (bills not in QuickBooks, customers to set up) |

- ilL roles **add to** standard ERPNext roles (Purchase, Stock, Accounts, Manufacturing, HR…); they never replace them. No role is assigned automatically. Decision 8 proposes who holds which.
- Audit with `portal.role_audit.report`, `.dealers`, `.hr`.

**SS-13-15** · User form roles section for a typical sales user

---

### Lesson 13.8: Background jobs to know (admin)

| Schedule | Job |
|---|---|
| Every minute | Webflow auto-push tick, gallery publication tick |
| Every 5 minutes | Portal email outbox, packet job recovery |
| Every 10 minutes (weekdays 6:00-17:59) | Kevin's Desk cache |
| Every 15 minutes | Order and quote stage refresh |
| Hourly | QuickBooks bill resend |
| Daily | Offer expiry reminders, overdue staff digest, finder session expiry |
| After every deploy | Workspace merge, Helpdesk fields, Command Center sync (overwrites desk edits to the Command Center page) |

**SS-13-16** · Scheduled Job Type list filtered to illumenate_lighting

---

## Slide deck beats

1. The system map
2. n8n: the hub, and service users
3. EasyPost: what's ready, what's left
4. QuickBooks: who holds what, and the sync log
5. Webflow and leads
6. Frappe apps around the ERP
7. Emails and notifications: what's on, what's off
8. Roles reference
9. Where to look when something didn't sync

## Check yourself

1. A Webflow listing didn't update. Name three places to look.
2. Where does the EasyPost API key live?
3. Which direction do payments flow between QuickBooks and ERPNext?
4. Why do your desk edits to the Command Center page disappear after a deploy?
