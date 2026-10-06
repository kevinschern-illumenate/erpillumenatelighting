# QuickBooks Online ⇄ ERPNext connector: setup and test

How to set it up and prove it works. Design notes: [QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md](QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md). Full scenario list: [QA_CHECKLIST.md](QA_CHECKLIST.md) §9.

```
ERPNext ──► ilL-QBO-Push-Log (outbox, retries) ──► n8n "QuickBooks API Proxy" ──► QuickBooks
QuickBooks ──(Intuit webhook)──► n8n "QuickBooks Payment → ERPNext" ──► ERPNext ──► ilL-QBO-Sync-Log
```

Both n8n workflows use your one QuickBooks OAuth2 credential. ERPNext never holds QuickBooks tokens. ERPNext and n8n sign every request to each other with one shared secret.

## What syncs

| In ERPNext | In QuickBooks | When |
|---|---|---|
| Sales Invoice submitted | Invoice (customer found by name or created first) | seconds after submit |
| Credit note (return) submitted | Credit Memo, applied to the original invoice if ERPNext reduced it | seconds after submit |
| Sales Invoice / credit note cancelled | Invoice voided / Credit Memo deleted | seconds after cancel |
| Payment Entry (Receive, Customer) submitted | Payment applied to those invoices | seconds after submit |
| That Payment Entry cancelled | Payment voided | seconds after cancel |
| Customer email/phone/address changed (already in QuickBooks) | Customer updated | seconds after save |
| **Payment Entry created / cancelled automatically** | ← Payment received / voided in QuickBooks | 1–5 min (Intuit batches webhooks) |

**Not synced:**
- Purchase side (bills, vendors).
- Multi-currency documents.
- Payments with deductions or write-offs.
- Edits made in QuickBooks to invoices, or to payments that came from ERPNext. A void of such a payment *is* synced back.
- Renaming a customer. The QuickBooks display name is kept.

Every outbound push is a row in **ilL-QBO-Push-Log**. Every inbound payment is a row in **ilL-QBO-Sync-Log**. A QuickBooks outage never blocks a submit: the push waits and retries for about 16 hours, then stops and waits for **Retry**.

---

## Setup

### 1. Deploy

Merge and let Frappe Cloud deploy. Migrate adds the new doctypes, settings fields and custom-field fixes.

### 2. Turn off the old ERPNext → QuickBooks flow

Do this before step 7, or every invoice gets pushed twice.

- In n8n, **deactivate** the old workflow that created QuickBooks customers and invoices.
- In ERPNext, open **Webhook** (Integrations) and disable any webhook that sends Sales Invoice events to n8n.

Invoices the old flow already pushed are safe. Either their `QBO ID` is set, so they're skipped, or the new push finds them by invoice number and links them.

### 3. QuickBooks preparation (≈5 min)

1. **Company ID**: ⚙ → Account and settings → Billing & subscription. You'll paste it into n8n as `QBO_REALM_ID`.
2. **Custom transaction numbers ON**: ⚙ → Account and settings → Sales → Sales form content. QuickBooks invoices then carry the ERPNext invoice number, which is also how retries find an invoice that already exists.
3. **Products and services**: create these (Service or Non-inventory, *not taxable*):
   - **`ERPNext Sales`**: income account = your product sales income.
   - **`ERPNext Sales Tax`** (recommended): ERPNext tax and freight rows post here. Point it at the liability account your bookkeeper wants for tax ERPNext collected. If you skip it, those rows post to `ERPNext Sales`.
   - Optional: one item per income account, mapped from ERPNext Item Groups in step 4.
4. **Sales tax**: ERPNext already calculates tax, so every line is sent as non-taxable (`NON`). QuickBooks must not add its own tax. If it does, the push log shows a "QuickBooks total … differs" warning.

### 4. ERPNext → ilL-QBO-Settings

| Field | Value |
|---|---|
| **Inbound** Sync Enabled | ✔ |
| Webhook Shared Secret | Output of `openssl rand -hex 32`. The same value goes into n8n. |
| Paid To Account | `1010 - ilLumenate Lighting WA Trust - ilL` |
| Mode of Payment | `QuickBooks Online` |
| **Outbound** Push Enabled | ☐ leave **off** until step 7 |
| n8n QuickBooks Proxy URL | From step 5 |
| Push Documents Posted On/After | Today (older documents are only sent if you backfill) |
| Push Sales Invoices / Credit Notes / Apply Credit Notes / Customer Payments / Customer Updates | ✔ (defaults) |
| Default QuickBooks Item | `ERPNext Sales` |
| QuickBooks Item for Taxes & Charges | `ERPNext Sales Tax` |
| QuickBooks Line Tax Code | `NON` |
| QuickBooks Deposit Account for Payments | Name of the QuickBooks bank account, or blank for "Payments to deposit" (Undeposited Funds) |
| Item Group → QuickBooks Item | Optional rows, e.g. `Drivers` → `Driver Sales`. Child groups inherit from their parent. |

### 5. n8n

1. **Import both workflows:**
   - `n8n_workflows/quickbooks_api_proxy.json`: ERPNext → QuickBooks.
   - `n8n_workflows/quickbooks_payment_sync.json`: QuickBooks payments → ERPNext. Replace any older copy.
2. **Variables** (Settings → Variables):

   | Variable | Value |
   |---|---|
   | `QBO_WEBHOOK_SECRET` | same as ilL-QBO-Settings |
   | `QBO_REALM_ID` | QuickBooks Company ID |
   | `INTUIT_VERIFIER_TOKEN` | from step 6 |
   | `ILL_ERP_BASE_URL` | `https://illumenatelighting.v.frappe.cloud` |
   | `QBO_API_BASE` (optional) | leave unset for production; `https://sandbox-quickbooks.api.intuit.com` only for a sandbox company |

   If your plan has no Variables, fill in the constants at the top of each workflow's Code nodes instead.
3. **Credentials**: pick your QuickBooks OAuth2 credential (production) on **QuickBooks GET**, **QuickBooks POST** and **Fetch QBO Payment**.
4. Leave **Raw Body** on in both Webhook nodes. In the payment workflow, swap **Send Alert** for Slack or Email. Set an Error Workflow on both workflows.
5. **Activate both**, then copy the two production URLs:
   - **ERPNext Request** URL → ilL-QBO-Settings → *n8n QuickBooks Proxy URL*.
   - **Intuit Webhook** URL → Intuit portal (step 6).

### 6. Intuit Developer portal

Use the same Intuit app whose keys are in the n8n QuickBooks credential.

1. Go to Webhooks → Production. Endpoint = the **Intuit Webhook** URL; events = **Payment** only.
2. Copy the **Verifier Token** into n8n's `INTUIT_VERIFIER_TOKEN`.

### 7. Check both directions, then turn on push

1. **Inbound check** (from your laptop; no money moves). You want `PASS`:
   ```bash
   QBO_WEBHOOK_SECRET=<secret> python3 tools/qbo_smoke_test.py https://illumenatelighting.v.frappe.cloud
   ```
2. **Outbound check**: ilL-QBO-Settings → **Outbound → Test QuickBooks connection**. You want "Connected to *your company*" and a ✅ beside every QuickBooks item and account you named.
3. Tick **Push Enabled** and save.

---

## The test (~15 min, two $1.00 invoices)

Use a test customer, e.g. `ZZ QBO Test`. After each step, check the **QuickBooks** panel on the form: the dashboard line and the QuickBooks ▾ menu → Sync log.

| # | Do this | Expect |
|---|---|---|
| 1 | **ERPNext → QBO invoice.** Submit Sales Invoice A for $1.00. | Within seconds, the form shows "In QuickBooks Online (Id …)". QuickBooks has the customer and an invoice with the same number for $1.00. The push log is **Synced**. |
| 2 | **QBO → ERPNext payment.** In QuickBooks, receive $1.00 on invoice A. | Within 1–5 min: ilL-QBO-Sync-Log **Created**; a submitted Payment Entry on the 1010 account; invoice A **Paid**. Nothing new in the push log (it isn't echoed back). |
| 3 | **QBO void → ERPNext.** In QuickBooks, void that payment. | Sync log **Cancelled**, the Payment Entry cancelled, invoice A back to **Unpaid**. |
| 4 | **ERPNext → QBO payment.** Submit Sales Invoice B for $1.00, then a Payment Entry (Receive) for $1.00 against B. | Push log for the Payment Entry **Synced**. In QuickBooks, invoice B is **Paid**, and the payment's memo reads "ERPNext Payment Entry …". A few minutes later the sync log shows a **Skipped-NoOp** echo. No duplicate Payment Entry. |
| 5 | **ERPNext cancel → QBO.** Cancel that Payment Entry, then cancel invoices A and B. | Push log **Void** rows **Synced**. In QuickBooks the payment and both invoices show as **Voided**. |

That's the full loop. For credit notes: make a return against a $1.00 invoice. QuickBooks gets a Credit Memo applied to that invoice, and its balance drops to $0.

### If something doesn't show up

| Symptom | Look at |
|---|---|
| Push log **Failed** "n8n proxy: bad signature" | `QBO_WEBHOOK_SECRET` in n8n ≠ ilL-QBO-Settings |
| "QBO_REALM_ID is not configured" / "path not allowed" | n8n Variables; re-import the proxy workflow |
| "QuickBooks authorization failed — reconnect…" | Reconnect the QuickBooks credential in n8n, then ilL-QBO-Settings → **Retry all failed pushes** |
| "QuickBooks has no Item named 'ERPNext Sales'" | Create the item in QuickBooks, or fix the name in settings |
| "QuickBooks already has Invoice #… for a different customer or amount" | A hand-made QuickBooks invoice uses that number. Use QuickBooks ▾ → **Link existing record**, or renumber the QuickBooks one. |
| Payment push **Queued** "Waiting for Sales Invoice …" | The invoice push is still pending or failed; fix that one first |
| "Sales Invoice … is not in QuickBooks" | Old invoice from before the start date. Open it → QuickBooks ▾ → **Push now**, then retry the payment. |
| Warning "QuickBooks total … differs from ERPNext" | QuickBooks added its own sales tax. Make the items non-taxable / check the tax code (step 3.4). |
| Nothing arrives from QuickBooks payments | Intuit webhook URL/subscription; payment workflow active; `INTUIT_VERIFIER_TOKEN`; `tools/qbo_smoke_test.py` |
| Sync log `invoice_not_matched` | That invoice was never pushed (no `QBO ID`); push it, then re-run the n8n execution |
| Sync log `invoice_already_paid` | The payment was also entered in ERPNext; remove one |

## Day to day

- **ilL-QBO-Push-Log**, filtered to Status = Failed, shows everything that needs a person. Each log shows the error, the exact request sent and QuickBooks' reply. Fix the cause, then press **Retry now**.
- ilL-QBO-Settings → **Outbound → Retry all failed pushes** after an outage or reconnect.
- ilL-QBO-Settings → **Outbound → Backfill…** sends older invoices and payments in a date range. Run it after the go-live start date if you want history in QuickBooks. Invoices already there are linked, not duplicated.
- Retrying is always safe: ERPNext reuses Intuit request ids and checks QuickBooks for the invoice number and memo before creating anything.
- n8n Cloud executions: each push uses 2–5 proxy executions (lookups plus the create), so budget about 5 per invoice.
