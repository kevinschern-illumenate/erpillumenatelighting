# Purchasing workflow and landed cost in the Command Center: implementation plan

Date: 2026-11-18. Status: **proposed**. Audience: the engineer (or coding agent) building it, and Jay and Charlotte (owners; Charlotte runs accounting), who will use it. Decisions to confirm are in section 9.

## Goal

Turn the **Purchasing** step of the Command Center sales pipeline (`/command-center#purch`) into a one-stop purchasing desk. Jay and Charlotte should be able to open it and see, without going into ERPNext:

1. **What needs ordering**: material requests, shortages against orders, and items below their reorder level.
2. **Vendor quotes**: which RFQs and supplier quotations are out, with whom, their status and when they expire.
3. **Purchase orders**: quote accepted → PO drafted → submitted → sent to the vendor → vendor confirmed → shipped → received. Each step has a status, an estimated lead time and an ETA the team can edit.
4. **Shipments and receipts**: inbound shipments (container, air, courier, LTL) with tracking and every cost on them (freight, duty, tariffs, brokerage, insurance, taxes), and the Purchase Receipts that bring the goods into stock.
5. **Bills**: Purchase Invoices from vendors, forwarders and customs brokers, matched to POs and receipts, and their QuickBooks status.
6. **Landed cost**: which receipts still need their freight, duty and tariffs added (a Landed Cost Voucher), estimated against actual, and the true landed cost per unit by item.

It should be as visual and simple as the Manufacturing production board, and cover every purchasing document type.

---

## 1. What exists today (read this first)

### 1.1 The Command Center

| Piece | File | Notes |
|---|---|---|
| Page JS (single IIFE, ~2.3k long lines) | `illumenate_lighting/command_center/page/cc.js` | Pipeline config `STAGES` (line ~183), quick links `QL.purch` (~197), Purchasing view `V.purch` (~224-246), per-SO "Purchasing needed" card (~892), general low-stock card (~903), "Draft MR" buttons (`data-mr` ~1441, `data-mrlow` ~979) |
| Page CSS | `illumenate_lighting/command_center/page/cc.css` | |
| Gateway (Server Script, RestrictedPython) | `illumenate_lighting/command_center/ss/cc_gateway.py` | `SECTIONS` + `ALLOWED` (only `Material Request` and `Purchase Order` in `purchasing`), `overview` "Decisions" signals `po_late` and `mr_late` (~492) |
| Deploy | `illumenate_lighting/command_center_sync.py` | Copies page + gateway into the Web Page / Server Script on every migrate. Grants Command Center roles on app doctypes (see `_sync_agenda_permissions`, reuse the pattern) |
| Docs | `illumenate_lighting/command_center/README.md` | Add a "Purchasing (v8)" section when done |
| Tests | `command_center/tests/smoke.js` (jsdom), `command_center/tests/check_gateway_sandbox.py` | Both must keep passing; add purchasing cases |

**Where today's Purchasing data comes from:** `D.purch` and `D.lowstock` come from the older Server Script **"ilL Command Center API"** (`ill_command_center`, file `cc_api.py`), which **is not in this repo** (README "Known limits"). From how `cc.js` uses it, each `D.purch` row has:
`item, group, lead, lead_src ('item' | category default), on_hand, on_order, supplier, need_by, order_by, late, short_firm, short_all, draft_po, mr, manufactured, docs[{src, doc, draft}]`.
Logic, per the page text: *short = open demand from submitted Sales Orders and active Work Orders − stock on hand − on order*; `order_by = need_by − lead time`; missing lead times fall back to category defaults (**extrusions 10 days, tape/neon/sheet 35, power and controls 28**). `short_all` also counts draft Sales Orders.

Today's page also says: *"no item has a reorder level or default supplier"* and work orders stay in Draft. Expect thin master data (section 7, Phase 0).

### 1.2 The pattern to copy: the Manufacturing production board

Manufacturing moved its heavy logic out of the Server Script into ordinary app code, and Purchasing should do the same:

- `illumenate_lighting/illumenate_lighting/api/production_board.py`: pure helpers at the top (unit-tested without a database), readers in the middle, one `@frappe.whitelist() get_board()` at the bottom that checks `VIEW_ROLES` and blanks money for users without `MONEY_ROLES` (`scrub`).
- Front end: `PB` object in `cc.js` (`PB_API`, `pbFetch`, `PB.body`, `PB.bind`, `PB.mount`, sub-tabs `PB_TABS` rendered as a `.seg` button row). Refreshes on demand, re-fetches when older than 2 minutes.
- Settings Single doctype `ilL-Production-Settings`, opened from a toolbar button on the page.
- Tests in `tests/portal_unit/test_production_board.py` via `test_services.load_service`.

Reusable readers already in `production_board.py`: `stock_on_hand(items)` (Bin), `incoming_purchases(items)` (open PO lines → `(date, qty)`), `holiday_dates`, `workdays`, `as_date`, `_fields` (drops columns missing on the site).

### 1.3 Purchasing code already in the app

| What | Where | Impact on this plan |
|---|---|---|
| PO may be saved without "Required By" | `api/purchase_order.py`, hook `Purchase Order.before_validate`; patch `make_po_schedule_date_optional` | ETA logic must cope with blank `schedule_date` (fall back to lead-time ETA) |
| MR built from a Sales Order must explode the **pinned** BOM | `api/material_planning.py` `validate_material_request` (`Material Request.before_insert`) | Any "create MR" button must set `sales_order` on rows only when the BOM matches, or leave it off (the existing Draft MR button leaves it off) |
| Purchase Invoice → QuickBooks Bill | `api/qbo_bills.py` (on_submit/on_cancel, hourly `send_pending`), n8n `purchase_invoice_qbo_bill.json`, `docs/QBO_PAYABLES_SYNC.md` | **QuickBooks is the book of record for payables.** Every submitted PI (including freight/broker bills) becomes a QBO Bill whose item lines all go to **one** expense account (`QBO_BILL_EXPENSE_ACCOUNT_ID`). See section 6 and Decision D1 |
| Bill payments from QBO → Payment Entry | `api/qbo_sync.py` | Lets the board show Paid / Partly paid on bills |
| "Bills not in QuickBooks" list | Portal Operations page (`page/ill_portal_operations`) | Reuse `qbo_bills.queue_filters()` for a badge on the Bills tab |
| PO print format | `print_format/ill_purchase_order` | Used when emailing the PO to the vendor |
| Paint supplier group | `ilL-Production-Settings.paint_supplier_group` | Paint POs appear on Manufacturing; on Purchasing they show a "Paint" chip, not twice |
| Custom fields | `fixtures/custom_field.json` has only `Purchase Order Item.ill_section_label`, `Supplier.custom_qbo_id`, `Purchase Invoice.custom_qbo_id` | New fields go in a **patch** (`create_custom_fields`), like `patches/add_production_board_fields.py` |

### 1.4 ERPNext building blocks (standard, no customization needed)

| Step | Doctype | Status values to show | Standard mapper (whitelisted) |
|---|---|---|---|
| Reorder rules | `Item` → `reorder_levels` (Item Reorder: warehouse, `warehouse_reorder_level`, `warehouse_reorder_qty`, `material_request_type`); `Item.lead_time_days`; `Item.item_defaults[].default_supplier`; `Item.supplier_items`; `Item.customs_tariff_number`, `Item.country_of_origin` | n/a | Stock Settings `auto_indent` raises MRs automatically (keep **off**, Decision D4) |
| Need | `Material Request` | Draft, Pending, Partially Ordered, Ordered, Partially Received, Received, Stopped, Cancelled | `erpnext.stock.doctype.material_request.material_request.make_request_for_quotation`, `.make_supplier_quotation`, `.make_purchase_order` |
| Ask vendors | `Request for Quotation` (+ `suppliers[]` with `quote_status` Pending/Received, `email_sent`) | Draft, Submitted, Cancelled | `erpnext.buying.doctype.request_for_quotation.request_for_quotation.make_supplier_quotation_from_rfq` |
| Vendor's price | `Supplier Quotation` (`valid_till`; item `lead_time_days`, `expected_delivery_date`) | Draft, Submitted, Stopped, Expired, Cancelled | `erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order` |
| Order | `Purchase Order` (`schedule_date`, `per_received`, `per_billed`, v15+ `incoterm`/`named_place`) | Draft, On Hold, To Receive and Bill, To Bill, To Receive, Completed, Closed, Cancelled, Delivered | `erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt`, `.make_purchase_invoice` |
| Receive | `Purchase Receipt` (item `landed_cost_voucher_amount`, `valuation_rate`) | Draft, To Bill, Partly Billed, Completed, Return Issued, Closed, Cancelled | `erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice` |
| Bill | `Purchase Invoice` (`bill_no`, `due_date`, `outstanding_amount`, `custom_qbo_id`) | Draft, Unpaid, Overdue, Partly Paid, Paid, Return, Debit Note Issued, Cancelled | n/a |
| Landed cost | `Landed Cost Voucher` (`purchase_receipts[]`, `items[]`, `taxes[]` = Landed Cost Taxes and Charges: `expense_account`, `description`, `amount`; `distribute_charges_based_on` Qty / Amount / Distribute Manually) | Draft, Submitted, Cancelled | Build the doc directly, then call its `get_items_from_purchase_receipts()` method. Newer v15/v16 builds also have a vendor-invoice table on LCV: **check `frappe.get_meta("Landed Cost Voucher")` on the site** and fill it if present |
| Shipment | `Shipment` (standard) is built for **outbound** parcel shipping (pickup/delivery addresses, parcels, carrier booking). It is a poor fit for inbound containers with cost lines, so this plan adds a custom doctype (section 3.3) | | |

> Run `bench --site <site> console` → `frappe.__version__`, `erpnext.__version__` before starting. The README says Frappe v16 with a v15 fallback for aggregates; field names above are v15/v16. Use `_fields()`-style guards for anything optional.

---

## 2. The workflow we're modelling

```
 Reorder level / SO shortage / manual need
        │
        ▼
 Material Request ──► RFQ ──► Supplier Quotation(s) ──(accepted)──► Purchase Order (draft)
   (what & when)     (ask)    (price, lead time, valid till)           │ submit
                                                                       ▼
                                          Sent to vendor ──► Vendor confirmed (ack #, promised ship date)
                                                                       │
                                                                       ▼
                                          ilL-Inbound-Shipment (booked → in transit → customs → delivered)
                                           ├─ cost lines: freight, duty, tariffs, MPF/HMF, brokerage, insurance, drayage, taxes
                                           │     estimated first, actual when the bill arrives
                                           ▼
                                   Purchase Receipt (goods into stock)
                                           │
                     ┌─────────────────────┼─────────────────────────────┐
                     ▼                     ▼                             ▼
         Vendor Purchase Invoice   Forwarder / broker Purchase Invoices   Landed Cost Voucher
          (goods, to QBO)           (freight, duty, to QBO)               (adds those costs to the receipt's
                                                                          item valuation → true landed cost)
```

A **PO can arrive in several shipments**, and **a shipment can carry several POs** (consolidated container). The shipment record joins them.

---

## 3. Data model changes

All custom fields go in **one new patch**, `illumenate_lighting/patches/add_purchasing_tracking_fields.py`, added to the end of `patches.txt`. Use `create_custom_fields` with the `_after()` guard from `add_production_board_fields.py`. Every field on a submittable doctype that the team edits after submit gets `allow_on_submit: 1` and `no_copy: 1` (except where noted). Prefix fieldnames with `ill_`.

### 3.1 Purchase Order (header): vendor tracking

| fieldname | type | label | notes |
|---|---|---|---|
| `ill_purchasing_section` | Section Break | Vendor Tracking | collapsible, after `schedule_date` |
| `ill_vendor_status` | Select | Vendor Status | `\nNot sent\nSent\nConfirmed\nIn production\nShipped\nDelivered\nIssue`. Default `Not sent`. Shown as the PO lane on the board |
| `ill_sent_on` | Date | Sent to Vendor On | set automatically (3.6) or by hand |
| `ill_vendor_confirmed_on` | Date | Vendor Confirmed On | |
| `ill_vendor_order_no` | Data | Vendor Order / Ack # | |
| `ill_est_lead_time_days` | Int | Estimated Lead Time (days) | prefilled from the Supplier Quotation / supplier / item (3.7) |
| `ill_promised_ship_date` | Date | Vendor Promised Ship Date | |
| `ill_eta` | Date | Estimated Arrival | **The date the board uses.** Prefilled `transaction_date + lead`; editable |
| `ill_freight_mode` | Select | Freight Mode | `\nOcean FCL\nOcean LCL\nAir\nCourier\nLTL\nFTL\nVendor delivers\nWill call` |
| `ill_purchasing_notes` | Small Text | Purchasing Notes | shows on the board card |

### 3.2 Purchase Order Item, Supplier, Item, Customs Tariff Number

| doctype | fieldname | type | label / notes |
|---|---|---|---|
| Purchase Order Item | `ill_est_lead_time_days` | Int | Estimated Lead Time (days). Line-level override; blank = header |
| Purchase Order Item | `ill_eta` | Date | Line ETA (blank = header `ill_eta`) |
| Supplier | `ill_default_lead_time_days` | Int | Default Lead Time (days) |
| Supplier | `ill_default_freight_mode` | Select | same options as PO |
| Supplier | `ill_purchasing_email` | Data (Options: Email) | where POs and RFQs go |
| Supplier | `ill_supplier_role` | Select | `\nGoods vendor\nFreight forwarder\nCustoms broker\nCarrier\nOther`. Lets the shipment form filter forwarders and brokers |
| Customs Tariff Number | `ill_duty_rate_pct` | Percent | General (MFN) duty rate. **Estimate only**; the broker's entry summary is the actual |
| Customs Tariff Number | `ill_additional_tariff_pct` | Percent | Section 301 / other additional duties combined |
| Customs Tariff Number | `ill_rates_checked_on` | Date | so stale rates are visible |
| Customs Tariff Number | `ill_rate_notes` | Small Text | |

Item already has `lead_time_days`, `customs_tariff_number`, `country_of_origin`, `reorder_levels`, `item_defaults.default_supplier` (standard), so it needs no new Item fields.

### 3.3 New doctype: `ilL-Inbound-Shipment`

Module ilLumenate Lighting, autoname `ILL-SHP-.YYYY.-.####`, **not submittable** (status driven), track changes on.

| fieldname | type | notes |
|---|---|---|
| `status` | Select | `Planned\nBooked\nIn transit\nAt port / customs\nCleared\nOut for delivery\nDelivered\nCosts final\nCancelled` (in list view, standard filter) |
| `supplier` | Link Supplier | main goods vendor |
| `freight_mode` | Select | same options as PO |
| `forwarder` | Link Supplier | filter `ill_supplier_role = Freight forwarder / Carrier` |
| `customs_broker` | Link Supplier | |
| `tracking_no` | Data | BOL / AWB / PRO |
| `tracking_url` | Data (URL) | |
| `container_no` | Data | |
| `incoterm` | Link Incoterm | standard doctype in v15+ (guard: Data if missing) |
| `origin_country` | Link Country | |
| `port_of_loading`, `port_of_entry` | Data | |
| `etd`, `atd`, `eta`, `ata`, `cleared_on`, `delivered_on` | Date | estimated / actual |
| `entry_no` | Data | CBP entry number (7501) |
| `entered_value` | Currency | customs value |
| `purchase_orders` | Table `ilL-Child-Shipment-PO` | `purchase_order` (Link), `supplier` (fetch), `po_value` (Currency, fetch `base_net_total`), `share_pct` (Percent, editable; for allocating costs across POs) |
| `receipts` | Table `ilL-Child-Shipment-Receipt` | `purchase_receipt` (Link), `posting_date` (fetch), `value` (fetch) |
| `costs` | Table `ilL-Child-Shipment-Cost` | see below |
| `estimated_cost_total`, `actual_cost_total`, `variance` | Currency, read-only | computed in `validate` |
| `goods_value` | Currency, read-only | sum of linked PO values |
| `landed_cost_pct` | Percent, read-only | `(actual or estimated) / goods_value` |
| `landed_cost_vouchers` | Table `ilL-Child-Shipment-LCV` | `landed_cost_voucher` (Link), `docstatus` (fetch) |
| `notes` | Text Editor | |
| attachments | standard sidebar | BOL, commercial invoice, packing list, 7501 |

**`ilL-Child-Shipment-Cost`** (istable):

| fieldname | type | notes |
|---|---|---|
| `cost_type` | Select | `Freight\nDuty\nTariff (additional)\nMPF / HMF\nBrokerage\nInsurance\nDrayage / delivery\nStorage / demurrage\nSales / use tax\nOther` |
| `description` | Data | |
| `estimated_amount` | Currency | |
| `actual_amount` | Currency | blank until billed |
| `vendor` | Link Supplier | who bills it (forwarder, broker, carrier, vendor) |
| `purchase_invoice` | Link Purchase Invoice | the bill; once linked, `actual_amount` defaults to that PI's net amount for this cost if blank |
| `include_in_landed_cost` | Check | default from settings per cost type (3.4) |
| `expense_account` | Link Account | default from settings per cost type; the account the LCV credits (must match the account the bill debits) |
| `allocation` | Select | `By value\nBy qty\nManual` (default from settings); maps to LCV `distribute_charges_based_on` |

Python controller `ill_inbound_shipment.py`: `validate()` totals and fills defaults; `on_update()` writes `ill_vendor_status = Shipped` / `Delivered` and `ill_eta` back onto linked POs when the shipment status or `eta` changes (only if the PO's own status is earlier in the sequence; never move backwards).

Permissions (doctype JSON): System Manager, Purchase Manager, Accounts Manager full; Purchase User, Stock User, Accounts User read/write/create; Command Center Viewer read; Command Center Editor read/write/create (granted by `command_center_sync.py` like the agenda doctypes).

### 3.4 New Single doctype: `ilL-Purchasing-Settings`

Replaces constants buried in `cc_api.py` and gives Charlotte one place to set landed-cost rules.

| fieldname | type | default / notes |
|---|---|---|
| `company` | Link Company | `ilLumenate Lighting` |
| `default_warehouse` | Link Warehouse | `Stores - ilL` (used today by Draft MR) |
| `default_lead_times` | Table `ilL-Child-Group-Lead-Time` (`item_group` Link Item Group, `lead_time_days` Int) | seed: extrusions 10, tape/neon/sheet 35, power and controls 28 (insert-if-missing patch, **not** a fixture; see `hooks.py` fixture comment) |
| `safety_days` | Int | 3. Added to lead time when computing order-by |
| `reorder_lookback_days` | Int | 90. For suggested reorder levels |
| `quote_expiry_warn_days` | Int | 7 |
| `vendor_confirm_warn_days` | Int | 3. Sent but not confirmed after N days → signal |
| `receipt_bill_warn_days` | Int | 14. Received, no bill |
| `lcv_warn_days` | Int | 30. Shipment delivered, costs not landed |
| `cost_type_defaults` | Table `ilL-Child-Landed-Cost-Type` (`cost_type`, `include_in_landed_cost`, `expense_account`, `allocation`, `estimate_pct_of_value`) | estimate % lets the board show an estimated landed cost before any bill arrives (e.g. ocean freight 8%, duty from HTS) |

Permissions: System Manager, Purchase Manager, Accounts Manager write; Purchase User, Accounts User, Command Center Viewer read.

### 3.5 Accounts (setup, not code; Charlotte decides, see D1/D2)

Create under Stock Expenses (or COGS) as **"Expenses Included In Valuation"**-type accounts so LCV credits and the forwarder/broker bills debit the same account:
`Freight In - ilL`, `Duties & Tariffs - ilL`, `Customs Brokerage - ilL`, `Inbound Insurance - ilL`. Map them in `cost_type_defaults`. Create non-stock service Items for bill lines (e.g. `FREIGHT-IN`, `DUTY`, `TARIFF`, `BROKERAGE`, `MPF-HMF`) whose Item Default expense account is the matching account, so a broker's Purchase Invoice books correctly with no manual account edits.

### 3.6 Hooks (add to `hooks.py` `doc_events`; `hooks.py` is a bug-fix hotspot, so add keys and change nothing else)

| Doctype | Event | Function (new module `api/purchasing.py`) | Does |
|---|---|---|---|
| Purchase Order | `before_insert` (append to existing dict entry; keep `before_validate`) | `purchasing.prefill_po_tracking` | sets `ill_est_lead_time_days` (Supplier Quotation item → Supplier → Item → group default), `ill_eta`, `ill_freight_mode` from supplier, `ill_vendor_status = Not sent` |
| Purchase Order | `on_submit` | `purchasing.on_po_submit` | recompute `ill_eta` if blank |
| Communication | `after_insert` | `purchasing.on_communication` | if `reference_doctype == "Purchase Order"`, `sent_or_received == "Sent"` and status is `Not sent` → `ill_vendor_status = Sent`, `ill_sent_on = today` (db_set, plus "Command Center:"-style comment) |
| Purchase Receipt | `on_submit` | `purchasing.on_receipt_submit` | PO `ill_vendor_status = Delivered` when `per_received >= 100`; append receipt to any `ilL-Inbound-Shipment` that lists its PO and isn't Delivered yet (only if exactly one candidate) |
| Purchase Invoice | `on_submit` (append; keep `qbo_bills` hooks first) | `purchasing.on_invoice_submit` | if a shipment cost line references this PI, fill `actual_amount` when blank |

All hook code: wrap in try/except → `frappe.log_error("Purchasing hook failed: …")` so a tracking failure never blocks a submit.

### 3.7 Lead time precedence (one function, used everywhere)

`lead_time(item, supplier, po_row=None)` → `(days, source)`:
1. PO line `ill_est_lead_time_days` → `"po line"`
2. PO header `ill_est_lead_time_days` → `"po"`
3. latest submitted Supplier Quotation Item for (item, supplier), not expired → `"quote"`
4. `Supplier.ill_default_lead_time_days` → `"supplier"`
5. `Item.lead_time_days` → `"item"`
6. `ilL-Purchasing-Settings.default_lead_times` by item group (walk up the group tree) → `"group default"`
7. none → `(None, "none")`, flagged in Data gaps

---

## 4. Backend: `api/purchasing_board.py`

New module, same shape as `production_board.py`. **Read-only `get_board()` plus a few narrow write endpoints.** Acts as the signed-in user: no `ignore_permissions` on reads or writes. Writes never submit or cancel (same guarantee as the gateway); conversions create **drafts** and return their names.

### 4.1 Roles

```python
VIEW_ROLES  = {"Command Center Viewer", "System Manager", "Purchase Manager", "Purchase User",
               "Stock Manager", "Accounts Manager", "Accounts User"}
MONEY_ROLES = {"Command Center Finance", "System Manager", "Purchase Manager", "Accounts Manager"}
EDIT_ROLES  = {"Command Center Editor", "System Manager", "Purchase Manager", "Purchase User"}
```
Money keys (`*_amount`, `rate`, `value`, `total`, `cost*`, `variance`, `landed_*`) are blanked with a `scrub()` like the production board. Jay and Charlotte need **Command Center Viewer + Editor + Finance**, plus ERPNext **Purchase Manager** (and **Accounts Manager** for Charlotte) to submit in the desk.

### 4.2 Pure helpers (top of file, unit-tested)

- `po_lane(po)` → one of `draft | not_sent | awaiting_confirmation | confirmed | in_transit | partly_received | to_bill | done | on_hold`. Rules, first match wins: docstatus 0 → draft; status On Hold → on_hold; status Completed/Closed/Delivered → done; `per_received >= 100` and `per_billed < 100` → to_bill; `0 < per_received < 100` → partly_received; vendor status Shipped → in_transit; Confirmed/In production → confirmed; Sent → awaiting_confirmation; else not_sent.
- `quote_lane(rfq_or_sq, today, warn_days)` → `rfq_draft | awaiting_reply | quoted | expiring | ordered | expired | lost`.
- `mr_lane(mr)` → `draft | to_quote | quoted | ordered | receiving | done`.
- `shipment_lane(s)` = its status, grouped: `planned | moving (Booked, In transit) | customs (At port / customs, Cleared) | arriving (Out for delivery) | delivered | final`.
- `eta(po_row, header, lead)`: line `ill_eta` → header `ill_eta` → `schedule_date` → `transaction_date + lead`; returns `(date, source)`.
- `late_flags(eta, need_by, today)`: `overdue` (eta < today and not received), `will_miss` (eta > need_by).
- `shortages(demand, stock, incoming, lead_fn, today, safety)`: port of `cc_api.py`'s purchasing math, returning the **same row shape as `D.purch`** (section 1.1) so existing UI code (`V.purch` table, per-SO card, Draft MR) keeps working.
- `reorder_breaches(bins, reorder_rows)`: `projected_qty < warehouse_reorder_level` → row with `suggest_qty = max(warehouse_reorder_qty, level − projected)`.
- `suggest_reorder_level(daily_usage, lead, safety)` → `ceil(daily_usage × (lead + safety))`; daily usage = outbound Stock Ledger qty over `reorder_lookback_days` / workdays.
- `allocate_costs(lines, items, basis)` → per-item share by qty or value (mirror LCV math, so the estimate matches what ERPNext will post).
- `landed_unit_cost(rate, qty, allocated)` and `uplift_pct`.
- `three_way(po_rows, pr_rows, pi_rows)` → qty and price variances per item (PO vs received vs billed), flag > 2% or > $50.

### 4.3 Readers

Use `_fields()` guards; one query per doctype with `limit_page_length=0` and an `in` filter on names (no N+1, which `get_health` already flags 63 times elsewhere). Window: open documents plus anything modified in the last 120 days.

- MRs (type Purchase, docstatus < 2, not Stopped/Cancelled/fully done) + items.
- RFQs (docstatus < 2, last 120 days) + `suppliers` child (`quote_status`, `email_sent`).
- Supplier Quotations (docstatus < 2) + items (`lead_time_days`, `expected_delivery_date`, `request_for_quotation`, `material_request`); "ordered" if any PO Item has `supplier_quotation` = it.
- POs open or completed in window + items (`qty`, `received_qty`, `billed_amt`, `schedule_date`, `ill_eta`, `material_request`, `supplier_quotation`, `sales_order`).
- Purchase Receipts (window) + items (`purchase_order`, `landed_cost_voucher_amount`, `valuation_rate`, `base_net_amount`).
- Purchase Invoices (window, plus all unpaid) incl. `custom_qbo_id`, `outstanding_amount`, `due_date`, `bill_no`; items (`purchase_order`, `purchase_receipt`).
- Landed Cost Vouchers (window) + `purchase_receipts` child.
- `ilL-Inbound-Shipment` (not Cancelled, or delivered in window) + children.
- Bins, Item master gaps (supplier, lead, reorder, HTS, origin) for items that appear in any of the above or have stock.
- Demand for shortages: open submitted SOs and active WOs (reuse `production_board.open_orders`, `work_orders_for`, `material_needs`, `stock_on_hand`, `incoming_purchases`; import, don't copy).

### 4.4 `get_board()` response

```jsonc
{
  "today": "2026-11-18", "money": true, "can_edit": true,
  "settings": { "quote_expiry_warn_days": 7, "vendor_confirm_warn_days": 3, ... },
  "summary": {                       // drives the Overview flow strip + pipeline stage card
    "to_order":   {"count": 12, "late": 3},
    "mrs":        {"count": 5, "amount": 0},
    "quotes":     {"out": 4, "expiring": 1},
    "pos":        {"not_sent": 2, "awaiting_confirmation": 3, "confirmed": 6, "in_transit": 4, "amount": 81234.5},
    "shipments":  {"moving": 3, "customs": 1, "arriving": 1},
    "receipts":   {"to_bill": 2},
    "bills":      {"unpaid_amount": 22100, "overdue": 1, "not_in_qbo": 0},
    "landed":     {"needs_lcv": 4, "est_open_amount": 6400}
  },
  "decisions": [ {"id": "po_not_sent", "label": "Submitted POs not sent to the vendor", "count": 2, "tone": "bad", "tab": "pos", "lane": "not_sent"}, ... ],
  "shortages": [ /* D.purch row shape, section 1.1 */ ],
  "reorder":   [ {item, item_name, warehouse, projected, level, reorder_qty, suggest_qty, supplier, lead, lead_src, open_mr, open_po} ],
  "mrs":       [ {name, status, lane, schedule_date, items:[{item, qty, ordered_qty}], from_so, rfqs:[], sqs:[], pos:[]} ],
  "quotes":    [ {doctype, name, supplier|suppliers:[{supplier, quote_status, email_sent}], lane, valid_till, days_left, total, lead_days, items:n, mr, rfq, po} ],
  "quote_compare": [ {item, rows:[{sq, supplier, rate, lead_days, valid_till}]} ],   // items with 2+ live quotes
  "pos":       [ {name, supplier, lane, status, vendor_status, transaction_date, sent_on, confirmed_on, vendor_order_no,
                  lead_days, lead_src, eta, eta_src, need_by, overdue, will_miss, per_received, per_billed, amount,
                  freight_mode, notes, sales_orders:[], shipments:[], receipts:[], invoices:[], paint:bool} ],
  "shipments": [ {name, status, lane, supplier, forwarder, broker, mode, tracking_no, tracking_url, container_no,
                  etd, eta, ata, pos:[], receipts:[], goods_value, est_cost, actual_cost, variance, landed_pct,
                  costs:[{cost_type, est, actual, vendor, pi, in_lc}], lcvs:[{name, docstatus}], needs_lcv:bool} ],
  "receipts":  [ {name, supplier, posting_date, status, pos:[], amount, billed_pct, shipment, lcv_amount, needs_lcv:bool} ],
  "bills":     [ {name, supplier, bill_no, posting_date, due_date, status, amount, outstanding, qbo_id, pos:[], receipts:[],
                  kind: "goods"|"freight/duty", variance:{qty, price}} ],
  "landed":    { "pending": [ {receipt|shipment, est, actual, missing_bills:[cost_type]} ],
                 "vouchers": [ {name, docstatus, receipts:[], amount, posting_date} ],
                 "by_item":  [ {item, last_receipt, purchase_rate, landed_rate, uplift_pct, avg_uplift_12m} ] },
  "gaps":      { "no_supplier": [...], "no_lead": [...], "no_reorder": [...], "no_hts": [...], "no_origin": [...] },
  "suppliers": [ {supplier, open_pos, open_amount, avg_quoted_lead, avg_actual_lead, on_time_pct, last_po} ]
}
```

`decisions` (ids are used by the gateway too, 5.3): `to_order_late` (shortage past order-by), `reorder_breach`, `mr_unactioned` (Pending MR with no RFQ/SQ/PO > 2 days), `quote_expiring`, `rfq_no_reply` (> 5 days), `po_draft_old` (> 2 days), `po_not_sent`, `po_unconfirmed`, `po_overdue` (ETA passed, not received), `po_will_miss` (ETA after SO need date), `shipment_eta_passed`, `receipt_no_bill`, `bill_overdue`, `bill_not_in_qbo`, `needs_lcv`, `cost_variance` (actual > estimate by 15%).

### 4.5 Write endpoints (all `@frappe.whitelist(methods=["POST"])`, all check `EDIT_ROLES` and doc permission, all leave a `"Command Center: …"` Comment like the gateway's `audit()`)

| Method | Args | Does |
|---|---|---|
| `update_po_tracking` | `po`, `values` | Writes **only** the `ill_*` PO header fields from 3.1 (allowlist). Works on submitted POs because they are `allow_on_submit`. `doc.check_permission("write")`, `doc.save()` |
| `update_po_line_tracking` | `po`, `rows:[{name, ill_est_lead_time_days, ill_eta}]` | same for line fields |
| `set_item_lead_time` | `item`, `days` | `Item.lead_time_days` (needs Item write) |
| `draft_material_request` | `items:[{item, qty, schedule_date}]` | Move the two inline `frappe.client.insert` calls in `cc.js` here; company and warehouse from settings |
| `make_rfq` | `material_request`, `suppliers[]` | standard mapper → set suppliers → insert draft |
| `make_supplier_quotation` | `material_request` or `rfq`, `supplier` | mapper → insert draft (for typing in a quote received by email) |
| `make_po` | `supplier_quotation` (or `material_request` + `supplier`) | mapper → `prefill_po_tracking` → insert draft |
| `make_receipt` | `po` (+ optional `shipment`) | mapper → insert draft PR; link to shipment |
| `make_invoice` | `po` or `purchase_receipt` | mapper → insert draft PI |
| `create_shipment` | `pos[]`, `values` | new `ilL-Inbound-Shipment`, cost lines seeded from settings estimates |
| `update_shipment` | `name`, `values`, `costs[]` | save |
| `make_landed_cost_voucher` | `shipment` | Draft LCV: `purchase_receipts` = shipment receipts (submitted only), `get_items_from_purchase_receipts()`, one `taxes` row per cost type where `include_in_landed_cost` (amount = actual, else refuse unless `allow_estimate=1`), `distribute_charges_based_on` from allocation, vendor-invoice table if the site has it. Append to shipment. **Charlotte reviews and submits in the desk.** |

Refuse with clear messages: PO not submitted (for receipt/invoice), receipt not submitted (for LCV), cost lines without accounts, mixed allocation bases (LCV has one basis per voucher; split into two vouchers or use Manual).

---

## 5. Command Center changes

### 5.1 Purchasing page layout (`V.purch` rewritten, `PU` object like `PB`)

Header: title **Purchasing**, one-line description, toolbar: `Settings` (opens `/app/ill-purchasing-settings`), `+ New` menu (Material request, RFQ, Purchase order, Inbound shipment), `Refresh`. Quick links `QL.purch` extended with RFQs, Supplier quotations, Purchase invoices, Landed cost vouchers, Inbound shipments, Customs tariff numbers.

**Flow strip (always visible above the sub-tabs)**: one clickable tile per step, left to right, each with a count, a $ (money roles) and a red/amber dot when it holds a decision:

```
[ To order 12 ●3 ] → [ Requests 5 ] → [ Vendor quotes 4 ●1 ] → [ POs 15 ●2 ] → [ In transit 4 ] → [ Received 2 ] → [ Bills $22.1K ●1 ] → [ Landed cost 4 ● ]
```
Clicking a tile switches sub-tab. Reuse `.seg` / stat card styles; one new CSS block for the arrow strip, which collapses to a 2-column grid under 700px.

**Sub-tabs** (`PU_TABS`, remembered in `localStorage` like saved views, wrapped in try/catch):

| Tab | Contents |
|---|---|
| **Overview** | Decisions list (cards like Executive's, each opens its tab + lane); "Arriving next 14 days" timeline (POs and shipments by ETA, late ones red); spend by supplier (hbars, money roles); open PO $ by month of ETA (vbars) |
| **To order** | (a) **What to order**: the existing shortage table (keeps `Draft MR` buttons, now via `draft_material_request`), with a multi-select "Draft one MR for selected". (b) **Below reorder level** table with `suggest_qty` and "Draft MR". (c) "Only short if draft SOs go ahead" (existing `<details>`). (d) **Data gaps** card: counts + expandable lists of items with no supplier / lead time / reorder level / HTS / origin, each row with an inline edit of lead time and a link to the Item. Includes "Suggested reorder level" column and an Apply button (writes Item Reorder, Phase 5) |
| **Requests** | Kanban lanes for MRs: Draft · To quote · Quoted · Ordered · Receiving. Card: MR, needed-by (red if past), items × qty, linked RFQ/SQ/PO chips. Buttons: `Request quotes` (→ `make_rfq`, choose suppliers, defaults from item suppliers), `Order directly` (→ `make_po`) |
| **Vendor quotes** | Lanes: RFQ draft · Awaiting reply (per-supplier chips with Pending/Received) · Quoted · Expiring ≤ N days · Ordered · Expired / lost. Card: supplier, total, quoted lead time, valid-till countdown. Buttons: `Enter quote` (→ `make_supplier_quotation`), `Accept → draft PO` (→ `make_po`). Below: **Compare quotes** table (items with 2+ live quotes: supplier, rate, lead, valid till; cheapest and fastest highlighted) |
| **Purchase orders** | Lanes: Draft · Not sent · Awaiting confirmation · Confirmed / in production · In transit · Partly received · To bill · On hold (Done hidden behind a toggle). Card: PO, supplier, $, **lead time chip** (`28d · quote`), **ETA** (red overdue, amber will-miss with the SO it hurts), vendor ack #, notes, paint chip. Card click opens a **side sheet** (reuse `sheet()` at cc.js ~591) with the tracking form (vendor status, sent on, confirmed on, ack #, lead, ETA, promised ship, freight mode, notes) → `update_po_tracking`; a line table with per-line lead/ETA → `update_po_line_tracking`; linked SOs, shipments, receipts, bills; buttons `Email PO` (opens desk PO with `?email=1`, or `frappe.new_doc` email dialog link), `Create shipment`, `Draft receipt`, `Draft bill`, `+ Add to agenda`. Also a table view toggle (lanes ↔ table, sortable by ETA) |
| **Shipments** | Lanes: Planned · Moving · At customs · Arriving · Delivered (costs open) · Costs final. Card: mode icon (text glyph, no image), tracking (link), container, ETA/ATA, POs, goods $, **cost bar** (estimated vs actual stacked by cost type), landed %. Side sheet: header fields + editable cost lines table (type, est, actual, vendor, bill link, in LC ✓) → `update_shipment`; `Draft receipt`, `Draft landed cost voucher` |
| **Receipts** | Table: receipt, supplier, date, POs, $, billed %, shipment, LCV status chip (`Landed` / `Needs LCV` / `No inbound costs`), `Draft bill` button |
| **Bills** | Lanes: Draft · Unpaid · Overdue · Partly paid · Paid (30 days). Columns: supplier, vendor bill #, due, outstanding, kind (goods / freight-duty), **QBO chip** (`In QBO` / `Not sent` from `custom_qbo_id`), **3-way match** chip (`Matches` / `Qty off` / `Price off`, with variance tooltip). Finance-only money |
| **Landed cost** | (a) **Needs landed cost**: delivered shipments / receipts with inbound costs not yet in a submitted LCV, est vs actual, missing bills (e.g. "Duty bill not in yet"), `Draft LCV`. (b) **Vouchers**: recent LCVs and status. (c) **Landed cost by item**: last purchase rate, landed unit cost, uplift %, 12-month average uplift. Exportable via existing print / copy-as-text |
| **Suppliers** | Scorecard: open POs/$, avg quoted vs actual lead time (PR posting − PO date), on-time %, last PO; set supplier default lead time inline |

Every lane and table respects the global search box (`rowOK`) and the Finance money gate (show "—" when `money` is false, like `pbMoney`).

### 5.2 Other `cc.js` touch points

- `phases(m)` / the pipeline stepper card for **Purchasing**: use `PU.data.summary` when loaded (`to_order.count`, `late`, `po_overdue`); fall back to `D.purch` until the first fetch returns.
- Per-SO page "Purchasing needed for this order" (~892) and `soPurch` (~708): read `PU.data.shortages` when present, else `D.purch`. Add the POs feeding that SO with ETA.
- Production board "Waiting for parts" already shows PO ETA. Have `production_board.incoming_purchases` prefer `ill_eta` over `schedule_date` when the field exists (one-line change guarded by `_has_field`), so both boards agree.
- Agenda "Suggested" tab: add `po_overdue`, `po_unconfirmed`, `needs_lcv`.
- Bump the header comment to **v8** and list the change.

### 5.3 Gateway (`cc_gateway.py`)

- `ALLOWED` additions (columns list in brackets):
  - `"Request for Quotation": ("purchasing", ["name", "status", "transaction_date", "schedule_date", "modified"])`
  - `"Supplier Quotation": ("purchasing", ["name", "supplier", "status", "grand_total", "valid_till", "transaction_date", "modified"])`
  - `"Purchase Receipt": ("purchasing", ["name", "supplier", "status", "grand_total", "posting_date", "per_billed", "modified"])`
  - `"ilL-Inbound-Shipment": ("purchasing", ["name", "status", "supplier", "freight_mode", "tracking_no", "eta", "actual_cost_total", "modified"])`
  - `"Supplier": ("purchasing", ["name", "supplier_name", "supplier_group", "country", "ill_default_lead_time_days", "modified"])`
  - `"Purchase Invoice": ("finance", ["name", "supplier", "status", "grand_total", "outstanding_amount", "due_date", "modified"])` (Finance-gated like Sales Invoice)
  - `"Landed Cost Voucher": ("finance", ["name", "posting_date", "total_taxes_and_charges", "docstatus", "modified"])`
  - Extend `Purchase Order` columns with `ill_vendor_status`, `ill_eta`.
- `overview` signals: add `po_not_sent`, `po_unconfirmed`, `sq_expiring`, `receipt_no_bill`, `needs_lcv` (simple filters only; the precise version lives in `purchasing_board`). Keep `po_late` but switch to `ill_eta` when the field exists (the existing `available()` / `real()` guards handle missing columns).
- The gateway still never submits. Its `save` refuses submitted docs, which is why PO tracking edits go through `purchasing_board.update_po_tracking` instead.
- Re-run `check_gateway_sandbox.py` (RestrictedPython rules: no leading `_` names, everything inside `main()`).

### 5.4 `command_center_sync.py`

Generalize `_sync_agenda_permissions` to a list: agenda doctypes + `ilL-Inbound-Shipment` (Viewer read; Editor read/write/create) + `ilL-Purchasing-Settings` (Viewer read). Same "grant once, then Role Permissions Manager is the authority" rule.

### 5.5 README

Add a "Purchasing (v8)" section: tabs, lane rules, lead-time precedence, ETA precedence, what each button creates (always a draft), roles needed, and the landed-cost procedure in 6.

---

## 6. Landed cost: how it works end to end (for Charlotte)

1. **Estimate at PO / shipment time.** When a shipment is created, cost lines are seeded from settings: freight = `estimate_pct_of_value × goods value` by mode; duty and tariff = Σ(item value × HTS `ill_duty_rate_pct` + `ill_additional_tariff_pct`); MPF/HMF and brokerage from settings. The board shows **estimated landed cost %** and **estimated landed unit cost** per item before anything arrives.
2. **Receive.** Goods arrive → Purchase Receipt (draft from the board, submitted in the desk). Stock is valued at the PO rate.
3. **Bills arrive.** Vendor bill → Purchase Invoice against the PO/PR (goods). Forwarder and broker bills → Purchase Invoices using the service items (`FREIGHT-IN`, `DUTY`, …) whose expense account is the "included in valuation" account. Link each bill on the shipment's cost line; actual amounts fill in.
4. **Land it.** When the shipment's included costs all have actual amounts (or Charlotte accepts estimates), **Draft LCV** creates the Landed Cost Voucher. Charlotte checks the distribution and submits. ERPNext raises the valuation of the received items, re-posts consumption already made (Repost Item Valuation), and credits the cost accounts so they net to zero against the bills.
5. **Watch.** Landed cost tab shows uplift % by item and by shipment, and estimate-vs-actual variance, which feeds pricing reviews and the next shipment's estimates.

**QuickBooks implications (Decision D1).** Bills still flow to QBO exactly as today, all lines on `QBO_BILL_EXPENSE_ACCOUNT_ID`. The LCV itself is **not** sent to QBO. So:
- Option A (recommended for phase 1-4): ERPNext carries true landed cost in stock valuation and margins; QBO keeps freight/duty as expense (or COGS) per its existing bill account. Inventory value differs between the two systems by un-sold landed cost; Charlotte trues it up with a periodic QBO journal entry using the Landed cost tab's "landed cost in stock" total (add that figure to the tab).
- Option B (phase 5): extend `qbo_bills.bill_payload` with each line's `expense_account` and add an ERPNext-account → QBO-account map to `ilL-QBO-Settings`, so freight/duty bills post in QBO to an inventory or freight-in COGS account. Needs n8n workflow changes and a QBO sandbox test (`docs/QBO_PAYABLES_SYNC.md` step 5).

---

## 7. Order of work

Each phase is shippable on its own. Keep each PR small, since `hooks.py` and `cc.js` are hotspots.

**Phase 0: setup and data (mostly no code, owners + Charlotte)**
- Export the live Server Script "ilL Command Center API" to `illumenate_lighting/command_center/ss/cc_api.py` (read-only reference, not synced) so the shortage math can be ported exactly. If export isn't possible, implement from section 1.1 and compare outputs on staging.
- Decide D1-D6. Create the accounts and service items (3.5).
- Fill master data for the top ~50 purchased items: default supplier, `lead_time_days`, reorder level/qty for stocked components, HTS code + country of origin. The Data gaps card (Phase 1) lists the rest.

**Phase 1: visibility (read-only board + tracking fields)**
- Patch `add_purchasing_tracking_fields` (3.1, 3.2); `ilL-Purchasing-Settings` + child tables + seed patch; `api/purchasing.py` hooks for `prefill_po_tracking` and `on_communication`.
- `api/purchasing_board.py`: helpers, readers, `get_board`, `update_po_tracking`, `update_po_line_tracking`, `set_item_lead_time`, `draft_material_request`.
- `cc.js`: `PU` object, flow strip, tabs Overview / To order / Requests / Vendor quotes / Purchase orders / Receipts / Bills (lanes + sheets), Data gaps; stage card and SO page switched to `PU.data`. Gateway `ALLOWED` + signals; sync permissions.
- Tests (section 8).
- **Done when:** Jay can see every open MR, quote, PO, receipt and bill with a status lane, edit lead time and ETA on a submitted PO from the page, and the Decisions list matches what's in the desk.

**Phase 2: one-click conversions**
- `make_rfq`, `make_supplier_quotation`, `make_po`, `make_receipt`, `make_invoice` + buttons; multi-select Draft MR; Purchase Receipt `on_submit` hook.
- **Done when:** MR → RFQ → SQ → PO → PR → PI can each be drafted from the board, and every draft opens in the desk for submit.

**Phase 3: inbound shipments**
- `ilL-Inbound-Shipment` + children, controller, permissions; `create_shipment`, `update_shipment`; Shipments tab; shipment → PO status/ETA write-back; PI `on_submit` cost-line fill; estimates from settings + HTS rates.
- **Done when:** a test container with two POs shows estimated and actual costs, ETA flows to the POs and to the production board's Waiting for parts.

**Phase 4: landed cost**
- `make_landed_cost_voucher`; Landed cost tab (needs LCV, vouchers, by item, landed cost in stock total); `needs_lcv` and `cost_variance` decisions.
- **Done when:** on staging, a shipment with freight and duty bills produces a draft LCV that, once Charlotte submits it, changes the received items' valuation rate by the expected amount (verify in Stock Ledger), and the shipment shows Costs final.

**Phase 5: tuning**
- Suppliers scorecard; suggested reorder levels + Apply; optional QBO account mapping (D1 option B); optional Stock Settings `auto_indent` (D4).

---

## 8. Tests

- `tests/portal_unit/test_purchasing_board.py` (pattern: `test_production_board.py`, `load_service`): `po_lane` for every status combo; `quote_lane` expiry edges; lead-time precedence (each source wins over the ones below it); ETA precedence and blank `schedule_date`; `shortages` matches a hand-worked example including draft-SO `short_all`; `reorder_breaches` and `suggest_reorder_level`; `allocate_costs` by qty and by value equals LCV's distribution on a 3-item example (rounding: last item takes the remainder); `three_way` variances; `scrub` blanks every money key for non-money roles; write endpoints refuse without edit role, refuse non-allowlisted fields, never call `submit`.
- `tests/portal_unit/test_inbound_shipment.py`: totals, defaults per cost type, PO write-back never moves status backwards, LCV draft refuses estimates unless `allow_estimate`, refuses unsubmitted receipts, one taxes row per included cost type.
- `command_center/tests/smoke.js`: mock `purchasing_board.get_board` with one record per lane; walk every Purchasing sub-tab; check flow strip counts, a late PO shows red, the sheet opens and posts `update_po_tracking`, money hidden when `money:false`, and fallback to `D.purch` when the board call fails.
- `check_gateway_sandbox.py`: new doctypes in `list`/`counts`/`overview`, both aggregate dialects.
- `ruff check .` and `ruff format .`.
- Manual on staging: one full cycle MR → RFQ → SQ → PO → email → shipment → PR → vendor PI + broker PI → LCV, with Charlotte, before turning it on for production use. README note: "Writes have never run against real ERPNext. First test with a throwaway Task" applies here too.

---

## 9. Decisions for Jay and Charlotte

| # | Question | Recommendation |
|---|---|---|
| D1 | How landed cost shows up in QuickBooks | Option A for now (ERPNext valuation only, periodic QBO true-up); revisit Option B after three months |
| D2 | Which costs are capitalized into inventory (landed) vs expensed | Freight-in, duty, tariffs, MPF/HMF, brokerage, inbound insurance = landed. Storage/demurrage and sales/use tax = expensed (per-type default in settings, overridable per line) |
| D3 | Allocation basis | By value for duty/tariff/insurance; by qty for freight on uniform items. Manual when one container mixes very different goods |
| D4 | Automatic material requests from reorder levels (`auto_indent`) | Off. The board suggests and drafts; a person submits |
| D5 | Can the Command Center submit POs / receipts / LCVs? | No (keeps today's "never submits" guarantee). Drafts are created on the page; submit is one click in the desk, which also runs ERPNext's own validations |
| D6 | Who maintains HTS duty rates | Charlotte, with `ill_rates_checked_on`; broker's 7501 is the actual. Board flags rates older than 90 days |
| D7 | Lead-time defaults per category | Confirm 10 / 35 / 28 days and add safety days (proposed 3) |
| D8 | Roles | Jay, Charlotte: Command Center Viewer + Editor + Finance, Purchase Manager; Charlotte also Accounts Manager. Warehouse (Ryan): Viewer + Purchase User, no Finance |

---

## 10. Risks and notes

- **Thin master data** is the biggest risk: without suppliers, lead times and reorder levels, the To order tab is mostly flags. Phase 0 and the Data gaps card are part of the deliverable.
- **Hotspots** (`hooks.py`, `cc.js`): add, don't rewrite. Run both test suites on every PR.
- **Performance:** one board call, bulk queries, 2-minute client cache, same as the production board. Don't add per-row queries.
- **LCV after sales:** ERPNext re-posts valuation for stock already consumed; on a busy item this queues a Repost Item Valuation job. Expect a short delay before the Stock Ledger reflects it.
- **Multi-currency** stays out of scope (company is single currency per `QBO_PAYABLES_SYNC.md`); a foreign-currency vendor bill needs the PI's exchange rate and is handled in the desk.
- **The older `cc_api.py` feed still gives every Viewer the finance data** (README known limit). The new board gates money properly, so once Phase 1 ships, remove purchasing money from `cc_api.py` if it carries any.
