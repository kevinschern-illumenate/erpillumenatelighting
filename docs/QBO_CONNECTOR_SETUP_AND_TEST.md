# QuickBooks Online ⇄ ERPNext connector: setup and smoke test

Quick setup runbook. Design and edge cases: [QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md](QBO_TWO_WAY_SYNC_IMPLEMENTATION_PLAN.md). Full scenario list: [QA_CHECKLIST.md](QA_CHECKLIST.md) §9.

```
ERPNext ──(Sales Invoice submit)──► n8n "push" workflow ──► QBO Customer/Invoice   [lives only in n8n Cloud]
QBO ──(Intuit webhook)──► n8n quickbooks_payment_sync.json ──► ERPNext Payment Entry [this repo]
```

## 1. Deploy the app

1. Merge this branch and let Frappe Cloud deploy. The migrate runs `harden_qbo_sync_fields`, which makes `custom_qbo_id` / `custom_synced_from` writable after submit and stops Duplicate/Amend from copying them.
2. Check it worked: open any submitted Sales Invoice → Customize Form → `QBO ID` should show **Allow on Submit** and **No Copy**.

## 2. ERPNext settings

Open **ilL-QBO-Settings**:

| Field | Value |
|---|---|
| Sync Enabled | ✔ |
| Webhook Shared Secret | Run `openssl rand -hex 32` and paste the output. Keep it for n8n. |
| Paid To Account | `1010 - ilLumenate Lighting WA Trust - ilL` |
| Mode of Payment | `QuickBooks Online` (open it and confirm the Accounts row maps the company to the 1010 account) |

Then check from your laptop. This makes no changes to money:

```bash
QBO_WEBHOOK_SECRET=<the secret> python3 tools/qbo_smoke_test.py https://illumenatelighting.v.frappe.cloud
```

You want `PASS`. The script also leaves one `Skipped-NoOp` row in **ilL-QBO-Sync-Log**.

## 3. n8n

1. **Import** `n8n_workflows/quickbooks_payment_sync.json`. If you imported an older copy, delete it or deactivate it: its parser only reads the legacy Intuit format.
2. **Variables** (Settings → Variables):
   - `INTUIT_VERIFIER_TOKEN`: from step 4.
   - `QBO_WEBHOOK_SECRET`: same value as ilL-QBO-Settings.
   - `ILL_ERP_BASE_URL`: `https://illumenatelighting.v.frappe.cloud` (the Webflow workflows already use this one).
   - Optional `QBO_API_BASE`: leave it unset for production. Set it to `https://sandbox-quickbooks.api.intuit.com` only when testing against an Intuit sandbox company.

   If your plan has no Variables, paste the values into the constants at the top of the **Verify Intuit Signature**, **Split Payment Entities** and **Sign Request (HMAC)** Code nodes.
3. **Fetch QBO Payment** node: select the same QuickBooks OAuth2 credential the push workflow uses, set to the production environment.
4. **Intuit Webhook** node: leave Options → **Raw Body** on.
5. Replace **Send Alert** with a Slack or Email node that uses `{{ $json.subject }}` and `{{ $json.text }}`. Under Workflow Settings → Error Workflow, pick an error workflow so a bad signature or missing config doesn't fail silently.
6. **Activate** the workflow, then copy the Webhook node's **Production URL**.

## 4. Intuit Developer portal

Use the **same Intuit app** whose Client ID/Secret are in n8n's QuickBooks credential. Intuit only sends webhooks for companies that connected through that app.

1. Go to your app → **Webhooks** → **Production**, and paste the n8n production URL.
2. Subscribe to **Payment** events (Create/Update/Delete/Void). Leave Invoice and Customer off.
3. Copy the **Verifier Token** into the n8n variable `INTUIT_VERIFIER_TOKEN`.
4. Intuit now sends CloudEvents (`qbo.payment.created.v1`, …). The workflow also still reads the old format.

## 5. Check the push (ERPNext → QBO) workflow

That workflow lives only in n8n Cloud, so it couldn't be reviewed here. Confirm these four things:

- After it creates the QBO invoice, it writes the QBO Invoice **Id** (not the DocNumber) into `Sales Invoice.custom_qbo_id`. Payments are matched **only** by this field.
- Before this deploy, writing that field to a *submitted* invoice was rejected by ERPNext ("Not allowed to change QBO ID after submission"). If the push workflow had errors at that step, they should stop now.
- It skips invoices that already have a `custom_qbo_id`, so a re-run doesn't create a duplicate QBO invoice.
- If it ever pushes Payment Entries, it must skip any with `custom_synced_from = "QuickBooks Online"`. Otherwise payments loop back into QBO.

## 6. The test: one invoice, round trip (≈10 minutes)

Use a test customer and a $1.00 invoice.

1. **ERPNext → QBO.** Create and submit a Sales Invoice for $1.00.
   - Expect: the invoice appears in QBO within a minute, and the ERPNext invoice shows a **QBO ID**.
2. **QBO → ERPNext.** In QBO, **Receive payment** for that invoice, full $1.00.
   - Expect, usually within 1–5 minutes (Intuit batches webhooks):
     - **ilL-QBO-Sync-Log** has a row with status **Created**.
     - A submitted **Payment Entry** posted to the 1010 trust account, with QBO ID = the QBO payment Id.
     - The Sales Invoice status is **Paid**.
3. **Void it.** In QBO, void or delete that payment.
   - Expect: a log row with status **Cancelled**, the Payment Entry cancelled (not deleted), and the invoice back to **Unpaid**.
4. **Clean up.** Void the invoice in QBO, then cancel the Sales Invoice in ERPNext.

### If something doesn't show up

| Symptom | Look at |
|---|---|
| No n8n execution at all | Intuit portal webhook URL/subscription; workflow active; the company connected via the same Intuit app |
| n8n fails at **Verify Intuit Signature** | Wrong `INTUIT_VERIFIER_TOKEN`, or Raw Body turned off |
| n8n runs but **Split Payment Entities** outputs nothing | The event wasn't a Payment (expected for invoice/customer events) |
| **Fetch QBO Payment** errors | QuickBooks credential expired or set to the wrong environment; `QBO_API_BASE` sandbox vs production mismatch |
| ERPNext responds `unauthorized` | `QBO_WEBHOOK_SECRET` ≠ ilL-QBO-Settings secret; rerun `tools/qbo_smoke_test.py` |
| Log `Failed` `invoice_not_matched` | The push workflow never wrote `custom_qbo_id` on that Sales Invoice (see step 5) |
| Log `Failed` `invoice_already_paid` / `amount_exceeds_outstanding` | The invoice was also paid in ERPNext. Remove one of the two payments. |
| Log `Failed` `multiple_invoices_linked` | One QBO payment covers 2+ invoices. Not supported; enter it by hand. |

To replay after fixing a problem, re-run the n8n execution. ERPNext deduplicates by QBO payment id, so a replay is safe.
