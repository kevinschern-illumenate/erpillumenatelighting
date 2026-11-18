# Print formats

Every customer, vendor and shop document prints from one design template, with a field
outline per document. Fields were chosen from 40 recent records of each DocType on the live
site (November 2026). A field filled on fewer than ~5% of records is printed only when it
has a value.

## Files

| What | Where |
|------|-------|
| Design template: stylesheet and macros | `illumenate_lighting/templates/print/ill_print.html` |
| Lookups and formatting (`ill_print_*` jinja methods) | `illumenate_lighting/illumenate_lighting/printing.py` |
| One folder per format (`.json` record + `.html`) | `illumenate_lighting/illumenate_lighting/print_format/ill_*` |
| Starting Terms and Conditions text | `illumenate_lighting/illumenate_lighting/print_terms.py` |
| Seeds terms records and default formats (insert-only) | `illumenate_lighting/patches/seed_print_terms.py` |
| Brand fonts as TrueType for wkhtmltopdf | `illumenate_lighting/public/fonts/print/` |
| Tests | `tests/portal_unit/test_print_formats.py` |

Frappe reads each format's `.html` from disk at print time, so a deploy (migrate) updates
every format. Edits made to the HTML in Desk are ignored for these formats.

## Design template

The ilLumenate Design System, kept light on ink.

- **Type.** Manrope headings and labels, Poppins body (TrueType copies, which the server's
  wkhtmltopdf embeds as real text). Body 9.5px, labels 7px small caps.
- **Colour.** Navy `#172E48` for titles and rules; blue `#00588C` only for small field labels;
  gold `#FDC757` only as a 56px accent under the header and a 2.5px bar on section rows.
  Body text `#231F20`; muted `#5D6D7F`; hairlines `#D1D6DB`.
- **Ink.** No filled panels, table headers or zebra rows. Status tags, fixture-type tags,
  notes boxes and checkboxes are outlines.
- **Layout.** Tables only (wkhtmltopdf has no flexbox, grid, CSS variables or CSS columns).
  Table headers repeat on each page, and rows don't split across pages.

Blocks, top to bottom (each is a macro in `ill_print.html`):

1. **Header**: black logo and company address / phone / email / website on the left. On the
   right: the title, document number, an optional subtitle, and a status tag. The tag shows
   only when the status is not the everyday state the title implies (Draft, Cancelled,
   Expired, On Hold, Past due 11 days, Paid). A navy rule with the gold accent follows.
2. **Facts**: up to four columns of label/value pairs; empty values are dropped, so the strip
   only shows what the document has.
3. **Parties**: Bill to / Ship to / Attention (or Vendor, Ship to, Bill to) under a hairline.
   "Bill to / Ship to" merges into one block when the addresses match.
4. **Line items**, grouped by section (room / area) with section subtotals when there is more
   than one section. The description cell holds:
   - the fixture type tag and the item name;
   - the part number;
   - the specs: CCT, output, built length, watts, environment, finish. These come from the
     configured description. Its internal "Configured …: ILL-CTN-…" reference, "N/A" values
     and the production "Build Description" dump are left out;
   - kit notes and the line's additional notes.
5. **Totals** on the right (subtotal, discount, each shipping / tax / fee row, total, then
   paid / balance due). The left side carries context: dealer savings, payment schedule,
   payments received, order progress.
6. **Notes / instructions** boxes, **Terms** in two columns of 7.5px type, **signature lines**,
   and a one-line **closing** (who to contact).

## Pricing modes

- **Dealer** (Quotation, Sales Order, Sales Invoice): List, Disc %, Net and Amount when any
  line is discounted; otherwise one Unit Price column. The quote shows "List value $X; your
  dealer pricing saves $Y (Z%)".
- **MSRP** (`ilL Quotation - MSRP`, `ilL Sales Order - MSRP`): for the dealer's client.
  The unit price is the Standard Selling list rate (the price before the customer-group
  dealer discount), or the selling rate when that is higher. There are no discounts,
  freight, tax, billing address or payment terms. The dealer is shown as the contact, and
  the short `ilL Retail Terms` apply.

## Outlines

| Format | DocType | Facts | Lines | After the lines |
|---|---|---|---|---|
| ilL Quotation | Quotation | Quote date, valid until, project, fixture schedule, prepared by, payment terms, shipping, quote request, rep agency | Dealer pricing | Savings, payment schedule; sales terms; acceptance signature (signature, name, date, PO no.) |
| ilL Quotation - MSRP | Quotation | Quote date, valid until, project, fixture schedule | MSRP | "About these prices"; retail terms |
| ilL Sales Order | Sales Order | Order date, your PO (+date), requested delivery, confirmed / estimated ship date, project, schedule, quotation, prepared by, payment terms, shipping, will call, rep agency | Dealer pricing | Hold reason, shipping / receiving instructions; progress (shipped / billed %), advance paid and balance; "Please review" box; sales terms |
| ilL Sales Order - MSRP | Sales Order | Order date, estimated ship date, project, schedule | MSRP | Retail terms |
| ilL Sales Invoice | Sales Invoice (Credit Note when a return) | Invoice and due dates, your PO, payment terms, sales orders, shipments, project, schedule, tax IDs | Dealer pricing | Payments received; paid and balance due; "How to pay" box (schedule, past-due days, QuickBooks pay link, Company remittance instructions); sales terms |
| ilL Delivery Note | Delivery Note (packing / return slip) | Ship date, your PO, sales orders, carrier, tracking, waybill, project, schedule | No prices; kit contents ("Includes 3 ea × …"), packed checkbox | Total qty; received-by signature; damage / shortage reporting line |
| ilL Packing List | Packing Slip | Delivery note, ship date, PO, case no., carrier, tracking, net / gross weight | Qty, net weight, checked box | Damage / shortage line |
| ilL Pick List | Pick List | Customer, sales orders, project, warehouse, created | Warehouse / batch / serial, to pick, picked (write-in) | Picked by / checked by |
| ilL Payment Receipt | Payment Entry (Remittance Advice when paying a supplier) | Date, amount, method, reference (QBO-123 prints as QuickBooks #123), project | Invoices applied: due date, total, outstanding before, applied | Applied, deductions, total, unapplied |
| ilL Purchase Order | Purchase Order | Order date, required by, vendor ack no., promised ship date, freight mode, payment terms, buyer, project | Vendor's part no. and description (Item Supplier) first, our part, required by, qty, price | Totals; purchase terms; authorized-by signature; "confirm to purchasing@" |
| ilL Request for Quotation | Request for Quotation | Request date, required by, buyer, reply-to | No prices; write-in unit price and lead time | Purchase terms; vendor quote signature block |
| ilL Receiving Report | Purchase Receipt | Received, POs, vendor packing slip, received by, project | Received / accepted / rejected, put-away location, OK box | Received by, inspected by, discrepancies |
| ilL Purchase Invoice | Purchase Invoice (titled Vendor Bill) | Vendor invoice no. and date, posted, due, POs, receipts, terms, project | Order / receipt per line, expense account | Paid and balance; match-and-approve signatures |
| ilL Material Request | Material Request | Requested, required by, requested by, warehouses, sales orders, project | From → to, required by, qty, in stock, done | Requested / approved / fulfilled by |
| ilL Work Order Traveler | Work Order | Sales order, customer, fixture type, location, project, schedule, planned start, ship by, build points, BOM | Build specs from the configured record; cut list per segment and run plan, each with done boxes; full build description; materials with pulled boxes | Six-point QC checklist (pass / fail / initials); built by and QC by sign-off |
| ilL Fixture Schedule | ilL-Project-Fixture-Schedule | Project, dealer, location, version, sales order, printed | By location: type tag, name, part no., specs, which line a power supply feeds, notes, maker, qty; other manufacturers' model and electrical details | Built-length note |

## Terms and conditions

Three Terms and Conditions records, created once by the patch and edited by staff in Desk
from then on:

- **ilL Sales Terms**: quotes, orders, invoices. Covers pricing and validity, order
  acceptance, payment (prepay unless approved for Net 30), custom products
  (non-cancellable and non-returnable once in production), lead times, shipping and damage
  claims, returns (stock items within 30 days with an RMA, restocking fee depending on
  size), warranty (per spec sheet, five years for most), installation, and limitation of
  liability.
- **ilL Retail Terms**: the MSRP formats.
- **ilL Purchase Terms**: purchase orders and RFQs.

A document's own Terms field prints instead when it is filled in. The text is a business
draft: have counsel review it.

## Settings the formats read

- **Company**: Phone No, Email, Website. Until set, the header shows (425) 381-2447,
  sales@illumenate.lighting and illumenate.lighting. Vendor documents ask for replies at
  purchasing@illumenate.lighting (`printing.COMPANY_FALLBACK`).
- **Company > Invoice Payment Instructions** (custom field): printed in the invoice's "How to
  pay" box. It is empty today.
- **Sales Invoice > QuickBooks Payment Link**: printed as "Pay online" on unpaid invoices.

## Checking a change

```bash
python -B -m unittest discover -s tests/portal_unit -p "test_print_formats.py"
```

```bash
python -B tools/check_portal_templates.py
```

The tests render every format in a sandbox like Frappe's: undefined values print as
`{{ ... }}`, so a missing `else` on an inline `if` shows up as a failure.
