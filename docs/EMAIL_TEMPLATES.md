# Customer and supplier email templates

Code: `illumenate_lighting/illumenate_lighting/email_templates/`. Settings: **ilL-Email-Settings** (Desk, also linked from the Command Center settings card). Checked against the live site (Frappe 16.60.2, ERPNext 16.60.0, Helpdesk 16.1.0, CRM 16.0.4) on 2026-11-18.

## What ships

- **42 Email Templates** named `ilL - <DocType> - <purpose>` (three generic ones are `ilL - <purpose>`), each scoped to its DocType with `reference_doctype`, so the composer on a Sales Order only offers Sales Order templates plus the three generic ones. All use HTML (`use_html`), which switches the Desk composer to its HTML editor, so tables survive.
- **6 Helpdesk saved replies** (`HD Saved Reply`, scope Global) that read the ticket's `ill_sales_order` / `ill_sales_invoice` / `ill_quotation` links.
- **13 Notifications**, all **disabled**, each pointing at its Email Template (v16 Notifications render an Email Template's text directly, so the wording lives in one place).
- **Order confirmation and shipment emails sent by the app** after submit (off until switched on in ilL-Email-Settings), so a contact who is also a dealer portal user doesn't get the same news twice.
- Jinja helpers: `ill_email_context(doctype, name)`, `ill_tracking(delivery_note)`, `ill_money(value, currency)`, `ill_date(value)`. `ill_print_pdf_url` now also makes links for Delivery Note, Packing Slip, Purchase Order, Request for Quotation, Supplier Quotation and Payment Entry.
- Helpdesk: a new ticket whose subject names a quote, order or invoice (a customer replying to one of these emails) is linked to it, so the saved replies have context.
- Supplier recipients: a blank RFQ supplier email or Purchase Order `contact_email` defaults to Supplier **Purchasing Email** (`ill_purchasing_email`).

The `seed_email_templates` patch creates only what is missing. Staff edit the wording on the site afterwards, and migrations never overwrite it. To put the shipped text back on one template:

```bash
bench --site <site> execute illumenate_lighting.illumenate_lighting.email_templates.seed.restore --kwargs '{"names": ["ilL - Sales Order - Order confirmation"]}'
```

To review the wording without a site, run `python3 tools/render_email_previews.py previews.html`, which renders every template with sample data.

## The ilLumenate email card (every automatic email)

Decided 2026-11-18: 72-hour links, sender "ilLumenate Lighting", two-factor for staff only, footer PO Box 297, Bothell WA 98041 · (425) 381-2447, blue buttons.

Frappe wraps every email in `templates/emails/standard.html` (Notifications, Email Templates, portal emails, assignment alerts, composer emails) or `templates/emails/auth_email.html` (password reset, sign-in link, two-factor). This app ships both files in `illumenate_lighting/templates/emails/`. Frappe's template loader searches apps in reverse install order, and `illumenate_lighting` is installed right after Frappe, so ours are used. ERPNext, HRMS, CRM, Helpdesk and Print Designer don't ship these files (checked 2026-11-18). If an app installed later ever does, it wins, and the old look comes back.

| File | What it is |
|---|---|
| `ill_card.html` | The card: navy band with the white wordmark (`public/images/email/wordmark-white.png`), gold rule, white card, "Questions?" line, address footer. Tables and inline styles; the `<style data-premailer="ignore">` block only adds web fonts (served from `/assets/illumenate_lighting/fonts/`) and the phone layout. |
| `standard.html` | Card when the email has a header or container (alerts, the welcome and reset templates, portal emails) or its body carries `<!-- ill:card -->`. Frappe sends Notifications without a container, so `library.Template.body()` starts every template a Notification or auto-send uses with that marker (`library.automatic_slugs()`). Anything else, a person's email from the Desk composer, keeps Frappe's plain layout and reads like normal email with their signature. A site seeded before 2026-11-18 needs `seed.restore` on those templates to pick up the marker. |
| `auth_email.html` | Always the card. |
| `ill_macros.html` | Heading, paragraph, blue pill button, small print, copy-link and code blocks for the bodies below. |
| `ill_welcome_body.html`, `ill_password_reset_body.html` | Welcome and reset wording. Seeded as the Email Templates **ilL - Welcome** and **ilL - Password reset** and set in System Settings, so staff can edit the wording; `new_user.html` / `password_reset.html` include the same files if the setting is cleared. Both print the real link lifetime with `ill_link_lifetime()`. |
| `login_with_email_link.html`, `two_factor_setup.html`, `verification_code.html` | Frappe's sign-in link, authenticator setup and emailed code, reworded. Frappe has no setting for these, so the files are the only place to change them. |

Contact details and colors live in `email_templates/brand.py` (`BRAND`, `COLORS`). Change the phone, address or sales email there, not in the templates.

**Portal emails** (`portal/outbox.dispatch_one`) are sent with `with_container=True`, so they get the card too. Their bodies are built with `brand.portal_email(title, paragraphs, details, action, secondary, note, preference_note)`: a heading, the job name, a details panel (PO, carrier, tracking, dates), one blue button and a line linking the notification settings on `/portal/account`. Subjects keep their old prefixes ("Quote ready: …") because the schedule activity feed and notification center read them; the shipment subject is now "Your order has shipped: <order>".

**Sender name.** `PortalEmailQueue.before_insert` calls `brand.rebrand_sender`: email that would go out under the default account's own name ("Info <info@…>") and Frappe's welcome/reset mail (which otherwise carries the name of whoever created the user) are sent as **ilLumenate Lighting <the account's address>**. Email a person sends from the composer keeps their name. The Info account's Reply-To (sales@) is unchanged.

**Settings** (patch `apply_email_branding`, re-runnable with `bench --site <site> execute illumenate_lighting.illumenate_lighting.email_templates.system_emails.apply`):

| Setting | Before | After |
|---|---|---|
| System Settings → Reset Password Link Expiry Duration (also the welcome link) | 1200 s (20 min) | 259200 s (72 h) |
| System Settings → Welcome Email Template | Welcome Email | ilL - Welcome |
| System Settings → Reset Password Template | (blank: Frappe default) | ilL - Password reset |
| System Settings → App Name | Frappe | ilLumenate Lighting |
| Role **All** → Two Factor Auth | on (every user, dealers included) | off |
| Every role with Desk access → Two Factor Auth | off | on (staff only; a new Desk role needs it ticked by hand) |

The old **Welcome Email** and **Reset Password** Email Templates are left on the site, unused.

**Not done in code:** the links in every email use the site's primary domain. To make them read `app.illumenate.lighting` instead of `illumenatelighting.v.frappe.cloud`: in DNS add a CNAME `app` → `illumenatelighting.v.frappe.cloud`; in the Frappe Cloud dashboard open the site → Domains → add `app.illumenate.lighting`, wait for the certificate, then **Set Primary**.

To preview without a site, render a body through `standard.html` with premailer and Frappe's compiled `email.bundle.css` (what Frappe does before sending); `tests/portal_unit/test_email_branding.py` renders every file and checks for leaks.

## How a template is written

Every template starts with one line and then prints `c.*`:

```jinja
{% set c = ill_email_context(doctype, name) %}
<p>Hi {{ c.greeting_name }},</p>
...
{{ c.blocks.signature }}
```

Why a helper instead of `{{ customer_name }}` and `frappe.db.get_value(...)` in the template:

| Surface | What the template sees (verified in v16 source) | Consequence |
|---|---|---|
| Desk email composer | The document's fields at the top level (`{{ name }}`, `{{ po_no }}`), full safe globals | Works either way |
| Notification with an Email Template | `doc.as_dict()` at the top level, **restricted globals** (`restrict_globals=True`) | Long `frappe.*` lookups are limited; hook Jinja methods work |
| Request for Quotation | RFQ fields + `supplier`, `supplier_name`, `contact` (dict), `user_fullname`, **restricted globals**. ERPNext's `portal_link` / `update_password_link` render as nothing, and no Website User is created for suppliers (`email_templates/rfq.py`): suppliers reply to the email | Same |
| Frappe CRM (Deal / Lead) | Top-level fields plus `doc`; only `enabled` templates for the DocType are listed | Same |
| Helpdesk saved reply | `{**ticket, **agent_user}`: **`name`, `doctype`, `owner` are the agent's**, not the ticket's | Saved replies call the helper with the ticket's link fields, and sign with `{{ full_name }}` (the agent) |

Frappe renders with Jinja's `DebugUndefined`: a variable that isn't there prints as literal `{{ x }}` in the customer's inbox. `ill_email_context` therefore always returns every key (blank when unknown), pre-formatted ("November 18, 2026", "$1,234.00"), and returns an empty context instead of raising when the document is missing or the person rendering it can't read it. The tests render every template with full, partial and empty contexts and fail on any `{{`, `None` or `Undefined` in the output.

### What `c` holds

| Key | Contents |
|---|---|
| `found`, `doctype`, `name`, `is_cancelled` | The document |
| `greeting_name` | Contact's first name → `contact_display` → party name → "there" |
| `party_name`, `contact_email`, `po_no`, `po_date`, `date`, `grand_total`, `currency` | Header values |
| `job_name`, `project_name`, `schedule_name` | From `ill_fixture_schedule` (header or first line) → schedule name and its `ilL-Project` |
| `poc` {name, email, phone, title} | Point of contact (below) |
| `lines`, `lines_more` | Up to *Lines Listed in an Email* (default 15) item rows; label = fixture type + section/room, else item name |
| `pdf` {quote, so, si, dn, packing, po, rfq, sq} | Share-key PDF links in the repo print formats |
| `portal_url`, `is_dealer`, `portal` {home, orders, drawings, support} | Only when the customer has an enabled portal (Website User) contact; others would hit a login page |
| `quote` | number, date, valid_till, `expires_in`, `expired`, total, revised_from, lost_reason, crm_deal |
| `order` | date, progress (In production / Partly shipped / Shipped / On hold), total, `ship_date` + label, `delivery_promise` + label, requested_date, shipping address, receiving/shipping instructions, `hold_message`, will_call, proforma, schedule, `payment_due` {label, amount, due_date, portion}, shipments (with tracking), invoices |
| `invoice` | date, due_date, `days_overdue`, `overdue_stage` (first / second / final), total, outstanding, paid_to_date, `is_paid`, `is_return`, billing address, schedule (when more than one row), payments (from `ill_invoice_payments`) |
| `sales_orders` [{name, pdf, complete}] | SI: unique `items[].sales_order`; DN: unique `items[].against_sales_order` |
| `pay_link`, `pay_instructions` | QuickBooks link (https on intuit.com only, and only while a balance is owed); Company `custom_invoice_payment_instructions` |
| `shipment` | date, carrier, number, url (from `portal/shipment_tracking.py`), is_return, partial, address, packing_slips |
| `purchase`, `rfq`, `supplier_quote`, `receipt`, `payment`, `customer`, `deal` | Supplier-side, payment, customer and CRM values |
| `blocks` | Ready HTML: `lines`, `lines_no_prices`, `supplier_lines`, `order_schedule`, `invoice_schedule`, `payments`, `applied`, `rejected`, `tracking`, `pay_button`, `signature`, `shipping_address`, `billing_address`, `ship_to`, `pickup_address` |

### Rules

- **Point of contact** (signature): Company Contact Person (`company_contact_person`) → first Sales Team member with an email (Sales Person → Employee) → Customer Account Manager / CRM deal or lead owner / document creator, when that is an enabled System User and not an integration user (QuickBooks, publication worker) → ilL-Email-Settings sales or purchasing contact. On the live site this already resolves to the staff member who made each document.
- **Ship date**: the production board's `ill_estimated_ship_date` → `ill_likely_ship_date` → `delivery_date`, labelled "Estimated ship date". The staff-confirmed `ill_confirmed_delivery_date` is shown separately as "Confirmed delivery date" (see *Differences from the brief*).
- **Deposit**: with more than one payment schedule row, the first open row is the deposit; with one row due within 3 days of the order date, it is "Payment in advance". Net terms show nothing.
- **Customer PO**: the order confirmation asks for a PO number when `po_no` is blank and echoes it when set.
- **Packing list**: the first submitted Packing Slip for the Delivery Note (print format "Packing Slip"), else the ilL Delivery Note print.
- **Hold reasons** are never shown as staff shorthand; each `ill_hold_reason` maps to customer wording in `formatting.HOLD_MESSAGES`.
- Internal fields (floor notes, production overrides, build points, tariff and rate notes, late reasons) are never printed; a test enforces it.

## Template summary

| # | Template | DocType | How it is sent | To | PDF |
|---|---|---|---|---|---|
| 1 | `ilL - Quotation - Quote sent` | Quotation | Manual: pick it in the email composer | contact_email | ilL Quotation |
| 2 | `ilL - Quotation - Quote follow-up` | Quotation | Notification: 3 days after the quote date while Open | contact_email | - |
| 3 | `ilL - Quotation - Quote expiring soon` | Quotation | Notification: 7 days before Valid Till while Open | contact_email | - |
| 4 | `ilL - Quotation - Quote expired, refresh pricing` | Quotation | Notification: 1 day after Valid Till while Open or Expired | contact_email | - |
| 5 | `ilL - Quotation - Quote revised` | Quotation | Manual: pick it in the email composer on the amended quote; fill in what changed | contact_email | ilL Quotation |
| 6 | `ilL - Quotation - Quote lost check-in` | Quotation | Manual: pick it in the email composer once the quote is marked Lost | contact_email | - |
| 7 | `ilL - Quotation - Submittal package ready` | Quotation | Manual: pick it in the email composer; attach the submittal PDF | contact_email | - |
| 8 | `ilL - CRM Deal - Quote follow-up` | CRM Deal | Manual in Frappe CRM (deal email) | deal email | - |
| 9 | `ilL - CRM Deal - Lost check-in` | CRM Deal | Manual in Frappe CRM after the deal is Lost | deal email | - |
| 10 | `ilL - Sales Order - Order confirmation` | Sales Order | Automatic on submit when ilL-Email-Settings allows; or manual | contact_email (portal dealers skipped) | ilL Sales Order |
| 11 | `ilL - Sales Order - Deposit request` | Sales Order | Manual: pick it in the email composer | contact_email | ilL Sales Order |
| 12 | `ilL - Sales Order - On hold, action needed` | Sales Order | Manual: pick it in the email composer after setting Hold Reason | contact_email | - |
| 13 | `ilL - Sales Order - Ship date update` | Sales Order | Notification: Estimated Ship Date changes on a submitted order | contact_email | - |
| 14 | `ilL - Sales Order - Ship date changed` | Sales Order | Manual: pick it in the email composer after changing the ship date; add the reason | contact_email | - |
| 15 | `ilL - Sales Order - Ready for pickup` | Sales Order | Manual: pick it in the email composer (Will Call orders) | contact_email | - |
| 16 | `ilL - Sales Order - Proforma, pay before shipping` | Sales Order | Manual: pick it in the email composer (Proforma orders) | contact_email | ilL Sales Order |
| 17 | `ilL - Sales Order - Partial shipment` | Sales Order | Manual: pick it in the email composer | contact_email | - |
| 18 | `ilL - Sales Order - Order change confirmed` | Sales Order | Manual: pick it in the email composer; fill in what changed | contact_email | ilL Sales Order |
| 19 | `ilL - Sales Order - Status update` | Sales Order | Manual: pick it in the email composer | contact_email | - |
| 20 | `ilL - Sales Order - Drawings ready for approval` | Sales Order | Manual: pick it in the email composer; attach the drawings for non-portal customers | contact_email | - |
| 21 | `ilL - Delivery Note - Shipped` | Delivery Note | Automatic on submit when ilL-Email-Settings allows; or manual | contact_email (portal dealers skipped) | ilL Delivery Note |
| 22 | `ilL - Delivery Note - Delivery check-in` | Delivery Note | Notification: 5 days after shipping, not returns | contact_email | - |
| 23 | `ilL - Delivery Note - Return received` | Delivery Note | Manual: pick it in the email composer on a return Delivery Note | contact_email | - |
| 24 | `ilL - Sales Invoice - Invoice` | Sales Invoice | Notification: 1 day after the invoice date (after the QuickBooks pay link arrives); or manual | contact_email | ilL Sales Invoice |
| 25 | `ilL - Sales Invoice - Payment reminder` | Sales Invoice | Notification: 3 days before the due date with a balance | contact_email | - |
| 26 | `ilL - Sales Invoice - Past due` | Sales Invoice | Notifications: 1, 15 and 30 days after the due date with a balance | contact_email | ilL Sales Invoice |
| 27 | `ilL - Sales Invoice - Paid in full receipt` | Sales Invoice | Manual: pick it in the email composer | contact_email | ilL Sales Invoice |
| 28 | `ilL - Sales Invoice - Credit note` | Sales Invoice | Manual: pick it in the email composer on a return invoice | contact_email | ilL Sales Invoice |
| 29 | `ilL - Payment Entry - Payment received` | Payment Entry | Notification: on submit of a customer receipt | contact_email | - |
| 30 | `ilL - Payment Entry - Remittance advice` | Payment Entry | Manual: pick it in the email composer on a supplier payment | contact_email | - |
| 31 | `ilL - Customer - Dealer welcome` | Customer | Manual: pick it in the email composer | purchasing contact | - |
| 32 | `ilL - Purchase Order - Send to supplier` | Purchase Order | Manual: pick it in the email composer; sending marks the PO Sent | Supplier purchasing email, else contact_email | ilL Purchase Order |
| 33 | `ilL - Purchase Order - Confirmation chase` | Purchase Order | Notification: 3 days after Sent On with no confirmation | contact_email | - |
| 34 | `ilL - Purchase Order - Ship date and ETA check` | Purchase Order | Notification: 1 day after Promised Ship Date, not received; or manual | contact_email | - |
| 35 | `ilL - Purchase Order - Change or cancellation` | Purchase Order | Manual: pick it in the email composer on the amended or cancelled PO | contact_email | ilL Purchase Order |
| 36 | `ilL - Request for Quotation - Request` | Request for Quotation | Set as the RFQ's Email Template; ERPNext sends it per supplier | each supplier row's email | - |
| 37 | `ilL - Request for Quotation - No response reminder` | Request for Quotation | Manual: pick it in the email composer to suppliers who have not quoted | supplier email | - |
| 38 | `ilL - Supplier Quotation - Questions and expiry` | Supplier Quotation | Manual: pick it in the email composer; fill in the questions | contact_email | - |
| 39 | `ilL - Purchase Receipt - Receiving discrepancy` | Purchase Receipt | Manual: pick it in the email composer; describe the issue and attach photos | contact_email | - |
| 40 | `ilL - General follow-up` | (any) | Manual: pick it in the email composer on any document | anyone | - |
| 41 | `ilL - We received your message` | (any) | Manual: pick it in the email composer on any document | anyone | - |
| 42 | `ilL - Holiday hours` | (any) | Manual: pick it in the email composer; fill in the dates | anyone | - |

Every body is in `email_templates/bodies/<slug>.html`; each starts with a comment saying what it's for.

### Helpdesk saved replies

| Saved reply | Reads ticket field |
|---|---|
| `ilL - Order status` | `ill_sales_order` |
| `ilL - Invoice copy and payment link` | `ill_sales_invoice` |
| `ilL - Quote copy` | `ill_quotation` |
| `ilL - Warranty claim: what we need` | `ill_sales_order` |
| `ilL - Damaged in transit` | `ill_sales_order` |
| `ilL - Resolved, anything else?` | - |

They greet the ticket's Contact and sign with the agent's name. With no link on the ticket they ask for the order, invoice or quote number instead.

## Automation

### Notifications (created disabled)

| Notification | DocType | Event | Field | Days | Condition | Attach |
|---|---|---|---|---|---|---|
| `ilL - Quote follow-up` → `ilL - Quotation - Quote follow-up` | Quotation | Days After | `transaction_date` | 3 | `doc.docstatus == 1 and doc.status == "Open"` | - |
| `ilL - Quote expiring soon` → `ilL - Quotation - Quote expiring soon` | Quotation | Days Before | `valid_till` | 7 | `doc.docstatus == 1 and doc.status == "Open"` | - |
| `ilL - Quote expired` → `ilL - Quotation - Quote expired, refresh pricing` | Quotation | Days After | `valid_till` | 1 | `doc.docstatus == 1 and doc.status in ("Open", "Expired")` | - |
| `ilL - Ship date update` → `ilL - Sales Order - Ship date update` | Sales Order | Value Change | `ill_estimated_ship_date` | - | `doc.docstatus == 1 and doc.ill_estimated_ship_date and doc.per_delivered < 100` | - |
| `ilL - Delivery check-in` → `ilL - Delivery Note - Delivery check-in` | Delivery Note | Days After | `posting_date` | 5 | `doc.docstatus == 1 and not doc.is_return` | - |
| `ilL - Invoice` → `ilL - Sales Invoice - Invoice` | Sales Invoice | Days After | `posting_date` | 1 | `doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0` | ilL Sales Invoice |
| `ilL - Invoice due soon` → `ilL - Sales Invoice - Payment reminder` | Sales Invoice | Days Before | `due_date` | 3 | `doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0` | - |
| `ilL - Invoice past due 1 day` → `ilL - Sales Invoice - Past due` | Sales Invoice | Days After | `due_date` | 1 | `doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0` | - |
| `ilL - Invoice past due 15 days` → `ilL - Sales Invoice - Past due` | Sales Invoice | Days After | `due_date` | 15 | `doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0` | - |
| `ilL - Invoice past due 30 days` → `ilL - Sales Invoice - Past due` | Sales Invoice | Days After | `due_date` | 30 | `doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0` | ilL Sales Invoice |
| `ilL - Payment received` → `ilL - Payment Entry - Payment received` | Payment Entry | Submit | - | - | `doc.payment_type == "Receive" and doc.party_type == "Customer"` | - |
| `ilL - PO confirmation chase` → `ilL - Purchase Order - Confirmation chase` | Purchase Order | Days After | `ill_sent_on` | 3 | `doc.docstatus == 1 and doc.ill_vendor_status == "Sent" and not doc.ill_vendor_confirmed_on and not doc.ill_vendor_order_no` | - |
| `ilL - PO late shipment` → `ilL - Purchase Order - Ship date and ETA check` | Purchase Order | Days After | `ill_promised_ship_date` | 1 | `doc.docstatus == 1 and doc.per_received < 100 and doc.ill_vendor_status not in ("Shipped", "Delivered")` | - |

Recipient for all of them is the document's `contact_email`. To turn one on: send its template to yourself from a test document (test plan below), then open the Notification, set **Sender** to the account you want (see Email accounts), tick **Enabled**, save. Each send is recorded as a Communication in the document's timeline.

Configs, as created by the patch:

```json
[
 {
  "name": "ilL - Quote follow-up",
  "document_type": "Quotation",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.status == \"Open\"",
  "email_template": "ilL - Quotation - Quote follow-up",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "transaction_date",
  "days_in_advance": 3
 },
 {
  "name": "ilL - Quote expiring soon",
  "document_type": "Quotation",
  "event": "Days Before",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.status == \"Open\"",
  "email_template": "ilL - Quotation - Quote expiring soon",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "valid_till",
  "days_in_advance": 7
 },
 {
  "name": "ilL - Quote expired",
  "document_type": "Quotation",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.status in (\"Open\", \"Expired\")",
  "email_template": "ilL - Quotation - Quote expired, refresh pricing",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "valid_till",
  "days_in_advance": 1
 },
 {
  "name": "ilL - Ship date update",
  "document_type": "Sales Order",
  "event": "Value Change",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.ill_estimated_ship_date and doc.per_delivered < 100",
  "email_template": "ilL - Sales Order - Ship date update",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "value_changed": "ill_estimated_ship_date"
 },
 {
  "name": "ilL - Delivery check-in",
  "document_type": "Delivery Note",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return",
  "email_template": "ilL - Delivery Note - Delivery check-in",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "posting_date",
  "days_in_advance": 5
 },
 {
  "name": "ilL - Invoice",
  "document_type": "Sales Invoice",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0",
  "email_template": "ilL - Sales Invoice - Invoice",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "posting_date",
  "days_in_advance": 1,
  "attach_print": 1,
  "print_format": "ilL Sales Invoice"
 },
 {
  "name": "ilL - Invoice due soon",
  "document_type": "Sales Invoice",
  "event": "Days Before",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0",
  "email_template": "ilL - Sales Invoice - Payment reminder",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "due_date",
  "days_in_advance": 3
 },
 {
  "name": "ilL - Invoice past due 1 day",
  "document_type": "Sales Invoice",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0",
  "email_template": "ilL - Sales Invoice - Past due",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "due_date",
  "days_in_advance": 1
 },
 {
  "name": "ilL - Invoice past due 15 days",
  "document_type": "Sales Invoice",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0",
  "email_template": "ilL - Sales Invoice - Past due",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "due_date",
  "days_in_advance": 15
 },
 {
  "name": "ilL - Invoice past due 30 days",
  "document_type": "Sales Invoice",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0",
  "email_template": "ilL - Sales Invoice - Past due",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "due_date",
  "days_in_advance": 30,
  "attach_print": 1,
  "print_format": "ilL Sales Invoice"
 },
 {
  "name": "ilL - Payment received",
  "document_type": "Payment Entry",
  "event": "Submit",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.payment_type == \"Receive\" and doc.party_type == \"Customer\"",
  "email_template": "ilL - Payment Entry - Payment received",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ]
 },
 {
  "name": "ilL - PO confirmation chase",
  "document_type": "Purchase Order",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.ill_vendor_status == \"Sent\" and not doc.ill_vendor_confirmed_on and not doc.ill_vendor_order_no",
  "email_template": "ilL - Purchase Order - Confirmation chase",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "ill_sent_on",
  "days_in_advance": 3
 },
 {
  "name": "ilL - PO late shipment",
  "document_type": "Purchase Order",
  "event": "Days After",
  "enabled": 0,
  "channel": "Email",
  "condition": "doc.docstatus == 1 and doc.per_received < 100 and doc.ill_vendor_status not in (\"Shipped\", \"Delivered\")",
  "email_template": "ilL - Purchase Order - Ship date and ETA check",
  "recipients": [
   {
    "receiver_by_document_field": "contact_email"
   }
  ],
  "date_changed": "ill_promised_ship_date",
  "days_in_advance": 1
 }
]
```

### Sent by the app (ilL-Email-Settings → Automatic Emails)

| Email | When | To | Duplicate guard |
|---|---|---|---|
| `ilL - Sales Order - Order confirmation` + ilL Sales Order PDF | Sales Order submit, queued after commit | `contact_email`, else the Customer's Portal Purchasing Contact | Skips addresses the dealer portal already emails for this order; skips if a Communication from this template already exists on the order |
| `ilL - Delivery Note - Shipped` + ilL Delivery Note PDF | Delivery Note submit (not returns), queued after commit | same | same, across every Sales Order on the note |

Both ship off. *Also Email Dealer Portal Users* sends to portal users as well; *BCC* and *Send From Email Account* apply to both.

### Purchasing mailbox (purchasing@)

All supplier email goes in and out through one shared mailbox (`email_templates/purchasing_mail.py`). The mailbox is **ilL-Email-Settings → Purchasing Mailbox → Purchasing Email Account**. When that is blank, it is the Email Account whose address is the **Purchasing Contact Email** (now `purchasing@illumenate.lighting` by default). Until such an Email Account exists, none of this does anything.

- **Outgoing** (*Send All Purchasing Email From This Account*, on by default). Email about a Purchase Order, RFQ, Supplier Quotation, Purchase Receipt, Purchase Invoice, Supplier, Subcontracting Order or Receipt, Inbound Shipment, or a Payment Entry that pays a supplier, leaves from the mailbox whoever sends it:
  - `Communication` `before_insert` covers the composer, RFQ *Send Supplier Emails*, Notifications and `make()`. It changes `sender` and `email_account`, so Frappe uses the mailbox's SMTP login, signature and Reply-To.
  - `PortalEmailQueue.before_insert` catches mail queued directly with another account's From (for example a Notification's own send). It moves the mail to the mailbox and rewrites the queued From and Reply-To headers. This runs before `rebrand_sender`.
  - A person's name is kept ("Reigine Yray <purchasing@…>"). Automatic mail carries the mailbox's name, which `rebrand_sender` turns into "ilLumenate Lighting".
  - The composer shows the mailbox as From on these documents when the buyer has the account in **User → User Emails** (`public/js/desk/purchasing_sender.js`, from `frappe.boot.ill_purchasing_mail`).
- **Incoming** (*Link New Supplier Email to the Document It Mentions*, on by default). Replies to email ERPNext sent thread onto their document through In-Reply-To. A new email arriving in the mailbox that names a PO, RFQ, Supplier Quotation, Purchase Receipt, Purchase Invoice or Inbound Shipment number is linked to it. The subject is checked before the body, and a cancelled document only wins when nothing else is named. The email is also linked to the sender's **Supplier**: first by exact address (Supplier email, Purchasing Email), then by company domain across suppliers and their contacts. A domain match only counts when exactly one supplier matches, and never for free-mail domains or our own domain.
- **Purchasing board**: *Purchasing emails not linked to a document* counts open, unlinked email received in the mailbox. Its tile opens that Communication list.
- **Supplier Purchasing Email**: the `backfill_supplier_purchasing_email` patch fills blanks from each supplier's primary contact, or from the one address its contacts share. Saving a Supplier fills a blank from its primary contact.

Setup: create the Email Account for purchasing@ (incoming and outgoing on; IMAP `INBOX` with *Append To* blank; Email Sync Option **ALL**; *Always use this account's email address as the sender* on; not the default account). Then add the account to each buyer's **User Emails**, set *Purchasing Email Account* here, and set **Buying Settings → Fixed Outgoing Email Account** to it.

### Recommendations

- **Avoiding double emails with the dealer portal** (`portal/notifications.py` emails portal users on quote ready, order approved, action needed and Delivery Note submit). Chosen approach: **different recipients**. The portal keeps emailing its users (respecting their notification toggles), and the app's confirmation and shipment emails go only to contacts the portal does not cover. The Notifications above cover events the portal doesn't email (follow-ups, invoices, reminders, receipts, ship date updates, purchasing), so they don't overlap. Later, the portal's short messages could render these templates so dealers get the same detail; that's a portal change and isn't in this PR.
- **Auto email on submit**: use Notifications with *Attach Print* (or the app sender above), not Print Settings' send-on-submit. Notifications have conditions, chosen recipients and templates; Print Settings would mail every submit.
- **QuickBooks pay link**: the n8n workflow writes `custom_qbo_payment_link` with `frappe.db.set_value`, which doesn't fire Value Change Notifications. So the invoice Notification fires **one day after the invoice date**, giving n8n time to write the link. No live invoice has a link yet, and the Company's *Invoice Payment Instructions* (`custom_invoice_payment_instructions`) is **empty**, so today an invoice email would have no way-to-pay section. Fill the instructions before enabling any invoice Notification. Links are only shown when they are https on intuit.com, the same rule as the write-back.
- **Collections**: the three past-due Notifications share one template whose tone steps up at 15 and 30 days. ERPNext **Dunning** (no Dunning Types exist yet) is the alternative when you want fees or interest, or one letter covering several invoices. **Process Statement Of Accounts** (none configured) can email monthly statements on a schedule; set it up for customers on terms rather than writing a template for it.
- **Email accounts**: Info (`info@`) is the default outgoing account, so a Notification with no Sender goes from info@. Suggest Sender = **Sales** (`sales@`, which has incoming enabled so replies come back) for customer emails. Purchasing email goes through the purchasing mailbox (above). Avoid **ilLumenate Lighting** (`hi@`): it adds an unsubscribe footer, which belongs on marketing, not transactional mail. Replies come back to the sending account; Frappe threads a reply into the document's timeline when that account receives mail (sales@ does). If Helpdesk receives the account instead, the reply becomes a ticket, and the subject link above attaches it to the quote, order or invoice.
- **CRM**: use the two CRM Deal templates by hand from the deal's email tab. A Frappe Notification on CRM Deal (Value Change on `status`) can automate the lost check-in later if wanted. When a deal is Won, staff make the Quotation → Sales Order in ERPNext, and the Sales Order confirmation takes over.
- **Auto Repeat** isn't needed: every email here is triggered by a document event or a date on the document, which Notifications already handle. Auto Repeat makes new documents on a schedule.
- **Scheduler**: nothing here needs a custom daily job. The "N days after" cases are date-field Notifications; Frappe evaluates them once a day.
- **Purchase Order sent**: emailing a submitted PO already marks it *Sent* with *Sent On* = today (`purchasing.on_communication`). The confirmation chase then fires 3 days later if no Vendor Order / Ack # or confirmation date was recorded.

## Test plan

Render without sending (bench console). This is the exact path the composer uses:

```python
frappe.get_doc("Email Template", "ilL - Sales Order - Order confirmation").get_formatted_email(
	frappe.get_doc("Sales Order", "ilL-SAL-ORD-Epic Home Systems-00003").as_dict())
```

Helpdesk:

```python
from helpdesk.api.saved_replies import get_rendered_saved_reply
get_rendered_saved_reply("<ticket>", "ilL - Order status")
```

To send yourself a test: open the document, **Email**, put your own address in To, pick the template, and send. Check that every value is filled (no blank labels, no "None", no `{{ }}`), dates read "November 18, 2026", money shows "$", PDF links open the right print format in a private window, the tracking link opens the carrier page, and the signature shows the right person.

Live documents to test with (all exist on the site today):

| Case | Document | Template(s) |
|---|---|---|
| SO with customer PO | `ilL-SAL-ORD-Epic Home Systems-00003` | Order confirmation (echoes PO), Status update |
| SO without PO | `ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00003` | Order confirmation (asks for PO, shows payment in advance) |
| Partial shipment | `ilL-SAL-ORD-KETEK Design Group-00007` | Partial shipment, Status update (lists shipment + tracking) |
| Cancelled order | `ilL-SAL-ORD-Tech Integrated-00005` | Any: PDF links must be blank |
| Overdue invoice | `ilL-ACC-SINV-Cascade Integration-00023` | Past due (first stage), Payment reminder |
| Partly paid invoice | `ilL-ACC-SINV-Cascade Integration-00027` | Invoice (paid so far + amount due) |
| Paid invoice | `ilL-ACC-SINV-Olympic Home & Theater-00002` | Paid in full receipt (payment history) |
| Credit note | `ilL-ACC-SINV-Garrett Integrated Systems-00003` | Credit note |
| No QBO link | any invoice today | Invoice: no button; "How to pay" once Company instructions are filled |
| Shipment with FedEx tracking | `ilL-MAT-DN-Tech Integrated-00006` | Shipped (tracking link, packing list link) |
| Return delivery note | `MAT-DN-2026-00057` | Return received; Shipped must say "return", not "shipped" |
| Quote with fixture schedule | `ilL-SAL-QTN-Technology Design Associates-00006` | Quote sent / follow-up (job name "Glick Residence") |
| Quote to a CRM Deal | `ilL-SAL-QTN--00002` | Quote follow-up (greets the deal contact) |
| CRM Deal | `CRM-DEAL-2026-00015` (has a quote), `CRM-DEAL-2026-00042` (no owner) | Quote follow-up, Lost check-in |
| Purchase Order | `PUR-ORD-2026-00057` (not sent), `PUR-ORD-2026-00041` (shipped) | Send to supplier, Confirmation chase, Ship date and ETA check |
| Supplier with no Purchasing Email | `COLORS LED` (every supplier today) | PO goes to the PO's `contact_email` |
| Customer payment | `ACC-PAY-2026-00100` | Payment received |
| Customer | `Epic Home Systems` | Dealer welcome |
| Ticket with no links | `0249` | Order status: asks for the order number |

Before this PR, each case above was rendered against the live documents (read-only, through the API) with the real context code: all 42 templates on 18 documents, no leaks.

Duplicate check: with *Email Order Confirmation* on, submit a Sales Order whose contact is a dealer portal user. The portal email arrives, the template email doesn't, and the order shows a comment saying why. Submit one for a non-portal contact: one email arrives, and a second submit or a job retry doesn't send another.

## Differences from the brief (the live site wins)

1. **Document Share Key Expiry is 30 days**, not 90. PDF links in an email stop working after a month. Suggest 90 (System Settings).
2. **Sales Order and Quotation have no `ill_project` field.** The project comes through `ill_fixture_schedule` → `ilL-Project-Fixture-Schedule.ill_project` → `ilL-Project.project_name`.
3. **`ill_confirmed_delivery_date` is a delivery promise, not a ship date.** It's set before approval (the portal won't submit without it), labelled "Staff Confirmed Delivery Date", and can't change after submit. The date that moves is `ill_estimated_ship_date` ("the day the order leaves our warehouse"), so that leads the ship date and the confirmed date is shown as "Confirmed delivery date". The ship date Notification watches `ill_estimated_ship_date`; one on the confirmed date would never fire on a submitted order.
4. **Quotation has `crm_deal`** (set even when Quotation To is Customer). The CRM follow-up finds the deal's quote through it or `quotation_to = CRM Deal`.
5. **Packing Slips are used** (e.g. `MAT-PAC-2026-00013`), so the packing list link prefers them.
6. **Not on the live site**: Supplier `ill_duty_rate_pct`, `ill_additional_tariff_pct`, `ill_rate_notes`, `ill_rates_checked_on`; Issue `ill_review_state`. None is used.
7. **Live-only fields** used: none required. `crm_deal` on Quotation is live-only (Frappe CRM) and is read only when present.
8. **Empty today**: Company payment instructions, QuickBooks pay links, Dunning Types, Process Statement Of Accounts, Buying Settings fixed email, RFQs / Supplier Quotations, Helpdesk saved replies, ticket links.
9. **Extra print formats exist** (`ilL-Sales Order`, `ilL - Sales Order 05052026`, `ilL-Sales Invoice`, `ilL-Delivery Note`, `ilL Quotation - 04202026`, `ilL-Quotation-Retail 04272026`). The defaults are the repo's `ilL …` formats, which these emails use.

## Fields that could not be confirmed on the live site

- `site_config` `disable_render_safe_exec`: not readable over the API. The templates don't depend on it; only our Jinja methods and `frappe.utils` are used.
- Supplier Quotation / Request for Quotation / Purchase Receipt rendering: no live records exist, so these were checked against the v16 DocType JSON and unit tests only.
- HD Ticket rendering on a ticket with links: no ticket is linked yet.
- `supplier_part_no` on Purchase Order Item: verified in v16 JSON; no live PO line uses it yet.

## Open questions (recommended answer first)

1. **Sender**: one shared **sales@** for customer emails and Notifications (replies come back to a monitored inbox), not each staff member's own address. Set it as the Sender on each Notification and in ilL-Email-Settings.
2. **Default point of contact** when a document names nobody: **sales@illumenate.lighting**, as "ilLumenate Lighting Sales" (editable in ilL-Email-Settings). Add a phone number there.
3. **Packing list**: keep the current rule (Packing Slip when one exists, else the ilL Delivery Note print).
4. **Confirmed delivery date vs ship date**: confirm the reading in *Differences* #3.
5. **Deposit**: confirm that a split payment schedule's first row is the deposit, and that a single row due on the order date means payment in advance.
6. **Portal dealers**: portal email only (the default). Tick *Also Email Dealer Portal Users* if they should get both.
7. **Go-live order**: first manual templates; then Quote follow-up/expiring, Delivery check-in, Payment reminder; then the app's confirmation and shipment emails; then invoices and past-due once payment instructions (or QuickBooks Payments links) are in place. Leave *Payment received* off while QuickBooks sends its own receipts.
8. **Brand**: answered 2026-11-18. Every template is sent inside the ilLumenate card (see *The ilLumenate email card*); the bodies keep their neutral inline styles, which sit well inside it.
9. **Pickup**: fill Pickup Address and Pickup Hours in ilL-Email-Settings before using *Ready for pickup*.
10. **Share key expiry**: raise it from 30 to 90 days?
