# QuickBooks payables and multi-invoice payments

QuickBooks Online is the book of record for payables. Purchasing stays in ERPNext (Material Request → Purchase Order → Purchase Receipt → Purchase Invoice); each submitted Purchase Invoice becomes a QuickBooks Bill, and Accounting pays bills in QuickBooks. Those bill payments, and customer payments that cover several invoices, come back to ERPNext as Payment Entries.

| Direction | Trigger | Code | n8n workflow |
|---|---|---|---|
| Purchase Invoice → QuickBooks Bill | Purchase Invoice submit (delete on cancel), hourly resend | [`api/qbo_bills.py`](../illumenate_lighting/illumenate_lighting/api/qbo_bills.py) | [`purchase_invoice_qbo_bill.json`](../n8n_workflows/purchase_invoice_qbo_bill.json) |
| QuickBooks BillPayment → Pay Payment Entry | Intuit webhook | [`api/qbo_sync.py`](../illumenate_lighting/illumenate_lighting/api/qbo_sync.py) `receive_bill_payment_event` | [`quickbooks_payment_sync.json`](../n8n_workflows/quickbooks_payment_sync.json) |
| QuickBooks Payment → Receive Payment Entry | Intuit webhook | `qbo_sync.receive_payment_event` | same workflow |
| Sales Invoice → QuickBooks Invoice id write-back | n8n invoice workflow, after it creates the Invoice | [`api/qbo_invoices.py`](../illumenate_lighting/illumenate_lighting/api/qbo_invoices.py) `receive_invoice_link` | live invoice workflow (not in this repo) |

All four calls into ERPNext are Guest endpoints signed with `X-QBO-Signature` (hex HMAC-SHA256 of the raw body, keyed with **ilL-QBO-Settings → Webhook Shared Secret**). ERPNext signs the bills it sends to n8n the same way.

## Supplier bills

On submit, ERPNext posts the Purchase Invoice to the n8n **Bill Webhook URL**. n8n:

1. Looks for a Bill whose DocNumber is the Purchase Invoice name. If one exists (a resend), it only writes the ids back.
2. Finds the Vendor by the Supplier's QuickBooks id, else by display name, else creates it.
3. Creates the Bill: one expense line per item (`net_amount`, so document discounts are included) on `QBO_BILL_EXPENSE_ACCOUNT_ID`, plus one line for taxes, charges and rounding on `QBO_BILL_ADJUSTMENT_ACCOUNT_ID` (falls back to the expense account). The Bill total equals the Purchase Invoice's rounded total. The supplier's invoice number goes in the private note.
4. Calls `qbo_bills.receive_bill_link`, which stores the Bill id on the Purchase Invoice and the Vendor id on the Supplier. A different id already stored is refused (409), never overwritten.

Cancelling the Purchase Invoice deletes the Bill. QuickBooks refuses to delete a Bill with payments applied; that n8n execution fails and the Bill is sorted out in QuickBooks.

Not sent: debit notes (returns), invoices posted before **Send Bills Posted On or After**, and anything while the URL or date is blank. Multi-currency bills are out of scope: the company runs in one currency.

**Bills not in QuickBooks** in Portal Operations (accounts roles, needs Purchase Invoice read) lists submitted invoices from the cutover date with no Bill id yet. An hourly job resends them after 15 minutes; a failed send is in the Error Log as "QBO bill push failed".

## Sales invoice ids

`custom_qbo_id` can't change on a submitted Sales Invoice, so the n8n invoice workflow calls `qbo_invoices.receive_invoice_link` with `{"sales_invoice", "qbo_invoice_id", "customer_qbo_id"?}` after creating the QuickBooks Invoice. It stores the Invoice id on the Sales Invoice and, when given, the Customer id on the invoice's Customer, with the same contract as `receive_bill_link`: signed, and a different id already stored is refused (409). Customer payments are matched to Sales Invoices by this id.

The QuickBooks id fields on Sales and Purchase Invoices are "no copy", so an amendment starts without an id. An amendment that still carries its cancelled original's id (made before that change) may have it replaced.

## Bill payments and multi-invoice payments

The payment workflow now accepts both Intuit entities. For each payment line applied to exactly one invoice (or bill) it sends an allocation:

```json
{
  "qbo_payment_id": "182",
  "event_type": "Create",
  "amount": 1234.56,
  "txn_date": "2026-10-15",
  "allocations": [{"qbo_invoice_id": "145", "amount": 1000.0}, {"qbo_invoice_id": "146", "amount": 234.56}],
  "customer_qbo_id": "62"
}
```

A bill payment uses `qbo_bill_id` in each allocation and `vendor_qbo_id`. ERPNext then:

- matches every invoice strictly by `custom_qbo_id` (Sales Invoice for payments, Purchase Invoice for bill payments) and fails the event if any is missing or unsubmitted;
- refuses allocations that total more than the payment, or invoices of different parties (`allocation_exceeds_payment`, `mixed_parties`);
- writes one Payment Entry with one reference per invoice. A remainder above the allocations stays unallocated on the Payment Entry and is logged as a warning;
- on Update or Merge, compares amount, date and every invoice/amount pair, and cancels and recreates the Payment Entry when any changed. Delete or Void cancels it.

Payments and bill payments are numbered separately in QuickBooks, so existing Payment Entries are looked up by id **and** payment type. **ilL-QBO-Sync-Log** shows the entity, every invoice applied to (**Applied To**) and the Sales or Purchase Invoice.

Still manual: a payment line linked to several invoices at once, and payments that also apply a credit memo or vendor credit. These fail with a clear message in the sync log.

## Setup

1. Deploy (migrate adds the new settings and log fields).
2. **ilL-QBO-Settings**: set **Paid From Account** (the bank bill payments leave from). Then, when ready to switch bills on, set **Bill Webhook URL** to the production URL of the bill workflow's webhook node, and **Send Bills Posted On or After** to the first day ERPNext bills should reach QuickBooks. Bills dated earlier must already be in QuickBooks.
3. n8n variables: `QBO_REALM_ID` (QuickBooks company id), `QBO_BILL_EXPENSE_ACCOUNT_ID`, optional `QBO_BILL_ADJUSTMENT_ACCOUNT_ID`; `QBO_WEBHOOK_SECRET` is already set for payments. Import `purchase_invoice_qbo_bill.json`, attach the existing QuickBooks OAuth2 credential to its HTTP nodes, and activate it. Re-import `quickbooks_payment_sync.json` over the current payment workflow.
4. Intuit Developer Dashboard → Webhooks: add the **BillPayment** entity to the existing subscription (same URL).
5. Acceptance on staging or the QuickBooks sandbox: submit a test Purchase Invoice and see the Bill; pay it in QuickBooks and see a Pay Payment Entry; pay two test Sales Invoices with one QuickBooks payment and see one Payment Entry with two references; cancel a test Purchase Invoice and see the Bill deleted.
