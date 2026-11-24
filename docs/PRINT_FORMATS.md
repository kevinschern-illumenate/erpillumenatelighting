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

- **Scale.** Frappe's wkhtmltopdf prints about 0.94pt per CSS px (15mm margins, smart
  shrinking off), so CSS sizes read close to point sizes. Body 8.5px, part numbers and specs
  7.5px, labels 6.5px small caps, titles 18px. Spacing runs on a 4px rhythm.
- **Type.** Documents use a standard sans-serif: `"Helvetica Neue", Helvetica, Arial`, which
  Frappe's wkhtmltopdf renders as Nimbus Sans (regular and bold only, so 500/600 weights
  print as regular/bold). No font files are linked.
  The **Fixture Schedule** alone is set in the brand typefaces: `styles(brand=True)` plus the
  `ill-brand` class on its `.ill-doc` give it Manrope for titles, labels and totals and
  Poppins for everything else. They ship as TrueType in `public/fonts/print/`, which the
  server's wkhtmltopdf embeds as searchable text. `ill_print_fonts()` links a font only when
  its file is installed: Frappe refuses the whole PDF when any linked resource fails to load,
  so a missing font falls back to Helvetica instead of breaking the print.
- **Colour.** Navy `#172E48` for titles, table headings and rules; muted `#5D6D7F` for labels
  and secondary text; body `#231F20`; hairlines `#D1D6DB`. Gold `#FDC757` appears once, as a
  48px accent under the header rule. Status tags are the only other colour (red for past due /
  on hold / cancelled, blue for paid / completed).
- **Ink.** No filled panels, table headers or zebra rows; tags, boxes and checkboxes are
  outlines. Frappe's print stylesheet gives every `th` a grey fill and removes its border
  (`!important`); `ill_print.html` overrides both.
- **Layout.** Tables only (wkhtmltopdf has no flexbox, grid, CSS variables or CSS columns).
  The header is top-aligned so the title sits in the same place on every document. Table
  headings repeat on each page. Each line is one table row, so a page break never splits a
  line (wkhtmltopdf keeps a row together but not a group of rows).
- **Numbers.** Money prints as `$1,234.56`; quantities as `20 ea` / `134 in`, with a long unit
  ("6.56ft Piece", "Pack of 6") on its own small line under the number; US phone numbers as
  `(559) 916-7300`.

Blocks, top to bottom (each is a macro in `ill_print.html`):

1. **Header**: black logo and company address / phone / email / website on the left. On the
   right: the title, document number, an optional subtitle, and a status tag. The tag shows
   only when the status is not the everyday state the title implies (Draft, Cancelled,
   Expired, On Hold, Past due 11 days, Paid). A navy rule with the gold accent follows.
2. **Facts**: up to four columns of label/value pairs; empty values are dropped, so the strip
   only shows what the document has.
3. **Parties**: Bill to / Ship to / Attention (or Vendor, Ship to, Bill to) under a hairline.
   "Bill to / Ship to" merges into one block when the addresses match.
4. **Line items** (the `line_group` macro), the same layout in every format:

   ```
   KITCHEN                                      <- section / room header row
   1 FIXTURE TYPE  A1                           <- when the line has a fixture type
     Item name                         2 ea …   <- the line
     PART-NUMBER · CCT 3000K · Output … · Length …
     Additional notes                           <- when the line has notes
                              Kitchen subtotal  <- priced documents, 2+ sections
   ```

   The fixture type and notes sit inside the description cell (`line_type` / `line_notes`),
   and the other cells are padded down to line up with the item name.

   A row with a section label, no item code and zero quantity starts a section; the rows
   after it inherit the label. Labels match case-insensitively, and a line's fixture type,
   specs and notes always stay together on a page. Specs come from the
   configured description; its internal "Configured …: ILL-CTN-…" reference, "N/A" values
   and the production "Build Description" dump are left out.

   Documents whose rows don't carry these fields take them from the line they were made
   from: Packing Slip → Delivery Note; Pick List and Material Request → Sales Order;
   Purchase Receipt and Purchase Invoice → Purchase Order → Sales Order. Vendor documents
   (Purchase Order, RFQ) group by the PO's own room labels and never print a customer's
   fixture types or notes.

   **Page Break.** ERPNext's per-line Page Break check is honoured on every item table
   that has it (Quotation, Sales Order, Sales Invoice, Delivery Note, Packing Slip,
   Purchase Order, RFQ, Purchase Receipt, Purchase Invoice, Material Request). After a
   checked line the table closes, a new page starts and the table
   reopens with its column headings. If the room continues, its header repeats as
   "KITCHEN (continued)".

   **Repeated parts.** A configured fixture breaks into parts, so the same part can sit on a
   Purchase Order or Material Request once per fixture. Those prints show one line per part,
   with the quantities and amounts added up, when the rows match on item, unit, price,
   required-by date, supplier part no. and description, warehouses, BOM, room, fixture type
   and notes (`ill_print_sections(..., merge_same=True)`). The line lists every sales order
   it covers. The rows themselves stay separate, so each one keeps its sales order and
   material request link and their ordered / received quantities. A row with a Page Break
   is never merged. The PO emails (`email_templates/formatting.py` `merge_same_lines`)
   combine lines the same way.
5. **Totals** on the right (subtotal, discount, each shipping / tax / fee row, total, then
   paid / balance due). The left side carries context: dealer savings, payment schedule,
   payments received, order progress.
6. **Notes / instructions** boxes, **Terms** in two columns of 7px type (kept together with
   their title), **signature lines**, and a one-line **closing** (who to contact).

The rep agency (sales partner) stays off customer-facing documents.

The dealer portal's schedule PDF exports (`api/exports.generate_schedule_pdf`) print with
**ilL Fixture Schedule** and, for the priced export, **ilL Fixture Schedule - MSRP**
(`exports.print_schedule_pdf`). Spec submittal packets open with the ilL Fixture Schedule
pages when site config `generated_spec_submittals` is on. The older HTML layout
(`exports._generate_pdf_content`) is only the fallback when a print format fails.

## Pricing modes

- **Dealer** (Quotation, Sales Order, Sales Invoice): always Qty, List, Disc, Net and Amount.
  Pricing rules discount by brand, so each line shows its own discount ("—" when none); a
  document-level discount prints in the totals. Quotes and orders show "List value $X ·
  you save $Y" beside the totals.
- **MSRP** (`ilL Quotation - MSRP`, `ilL Sales Order - MSRP`): for the dealer's client.
  The unit price is the Standard Selling list rate (the price before the customer-group
  dealer discount), or the selling rate when that is higher. There are no discounts,
  freight, tax, billing address or payment terms. The dealer is shown as the contact, and
  the short `ilL Retail Terms` apply.

## Outlines

| Format | DocType | Facts | Lines | After the lines |
|---|---|---|---|---|
| ilL Quotation | Quotation | Quote date, valid until, project, fixture schedule, prepared by, payment terms, shipping, quote request | Dealer pricing | Savings, payment schedule; sales terms; acceptance signature (signature, name, date, PO no.) |
| ilL Quotation - MSRP | Quotation | Quote date, valid until, project, fixture schedule | MSRP | "About these prices"; retail terms |
| ilL Sales Order | Sales Order | Order date, your PO (+date), requested delivery, confirmed / estimated ship date, project, schedule, quotation, prepared by, payment terms, shipping, will call | Dealer pricing | Hold reason, shipping / receiving instructions; progress (shipped / billed %), advance paid and balance; "Please review" box; sales terms |
| ilL Sales Order - MSRP | Sales Order | Order date, estimated ship date, project, schedule | MSRP | Retail terms |
| ilL Sales Invoice | Sales Invoice (Credit Note when a return) | Invoice and due dates, your PO, payment terms, sales orders, shipments, project, schedule, tax IDs | Dealer pricing | Payments received; paid and balance due; "How to pay" box (schedule, past-due days, QuickBooks pay link, Company remittance instructions); sales terms |
| ilL Delivery Note | Delivery Note (packing / return slip) | Ship date, your PO, sales orders, carrier, tracking, waybill, project, schedule | No prices; kit contents ("Includes 3 ea × …"), packed checkbox | Total qty; received-by signature; damage / shortage reporting line |
| ilL Packing List | Packing Slip | Delivery note, ship date, PO, case no., carrier, tracking, net / gross weight | Qty, net weight, checked box | Damage / shortage line |
| ilL Pick List | Pick List | Customer, sales orders, project, warehouse, created | Warehouse / batch / serial, to pick, picked (write-in) | Picked by / checked by |
| ilL Payment Receipt | Payment Entry (Remittance Advice when paying a supplier) | Date, amount, method, reference (QBO-123 prints as QuickBooks #123), project | Invoices applied: due date, total, outstanding before, applied | Applied, deductions, total, unapplied |
| ilL Purchase Order | Purchase Order | Order date, required by, vendor ack no., promised ship date, freight mode, payment terms, buyer, project | Supplier part no. column (the PO row's, else the Item's supplier row); the supplier description (Item Supplier › Supplier Description) leads the line with only our part no. beneath it (our item name leads when there is no supplier description); required by, qty, price | Totals; purchase terms; authorized-by signature; "confirm to purchasing@" |
| ilL Request for Quotation | Request for Quotation | Request date, required by, buyer, reply-to | No prices; write-in unit price and lead time | Purchase terms; vendor quote signature block |
| ilL Receiving Report | Purchase Receipt | Received, POs, vendor packing slip, received by, project | Received / accepted / rejected, put-away location, OK box | Received by, inspected by, discrepancies |
| ilL Purchase Invoice | Purchase Invoice (titled Vendor Bill) | Vendor invoice no. and date, posted, due, POs, receipts, terms, project | Order / receipt per line, expense account | Paid and balance; match-and-approve signatures |
| ilL Material Request | Material Request | Requested, required by, requested by, warehouses, sales orders, project | From → to, required by, qty, in stock, done | Requested / approved / fulfilled by |
| ilL Work Order Traveler | Work Order | Sales order, customer, fixture type, location, project, schedule, planned start, ship by, build points, BOM | Build specs from the configured record; cut list per segment and run plan, each with done boxes; full build description; materials with pulled boxes | Six-point QC checklist (pass / fail / initials); built by and QC by sign-off |
| ilL Fixture Schedule | ilL-Project-Fixture-Schedule | Project, dealer, location, version, sales order, printed | By location: type tag, name, part no., specs, which line a power supply feeds, notes, maker, qty; other manufacturers' model and electrical details | Built-length note |
| ilL Fixture Schedule - MSRP | ilL-Project-Fixture-Schedule | As ilL Fixture Schedule, plus "Prices: MSRP" | The same rows plus MSRP Unit and MSRP Amount (a fixture's included power supply on its own sub-line); "—" when unpriced | MSRP total; "About these prices" box saying every price is MSRP, not dealer net and not a quotation. Prices from `ill_print_schedule_prices`, empty without pricing permission. The dealer portal's "PDF (MSRP)" export |

Supplier part numbers and descriptions live on the Item's Supplier Items row for each supplier (`api/supplier_parts.py`). Purchase Order and Request for Quotation lines show **Supplier Part Number** and **Supplier Description**: picking an item or supplier fills them from the Item, and saving the document writes changed values back to the Item for its supplier (adding the row if needed) when the user can edit Items. A blank line value never clears the Item's. An RFQ does this only when it lists one supplier; with several, its lines are read-only and the **Supplier Parts** button sets the values one supplier at a time. That button, on both forms, edits every line at once (and can clear values); it needs edit rights on the document and on Items. On a submitted PO it corrects the lines in place and a comment records the change. The PO print uses the line's values first; the RFQ print, made once per supplier, uses that supplier's part number and description from the Item, so values set on the RFQ carry into the Supplier Quotation and Purchase Order.

The **Supplier Parts** button is also on Material Request, Quotation, Sales Order, Supplier Quotation, Purchase Receipt and Purchase Invoice. There it edits the Items only (their lines are left alone): it uses the document's supplier when it has one, and otherwise asks for a supplier, suggesting the ones already set on those items (Supplier Items rows and default suppliers), most items first, with a Sales Order's single drop-ship supplier preferred. It needs edit rights on Items and read access to the document.

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

## Paper and margins

PDFs are US Letter with 15mm margins on every side. Frappe takes the paper size from
Print Settings › PDF Page Size (Letter on the live site) and gives wkhtmltopdf 15mm margins
when a format has no header or footer HTML, which these don't. The template adds a 1px
inset on each side so right-aligned figures and tag borders never sit exactly on the clip
edge.

## Previewing a change

Local wkhtmltopdf builds are not the server's patched build and render about 25% small, so
judge layout against the server: render the format inside Frappe's printview shell and post
it to `frappe.utils.print_format.report_to_pdf` with `html { zoom: 1.25 }` (that endpoint
shrinks to fit; the zoom brings it within ~1pt of a real download). Brand fonts can't be
previewed that way until they are deployed, so check typography in Chromium with `html { zoom: 1.25 }`. Chromium zooms the PDF margins too, so pass 12mm there to get a true 15mm (its `scale` option clips the right edge instead).

## Checking a change

```bash
python -B -m unittest discover -s tests/portal_unit -p "test_print_formats.py"
```

```bash
python -B tools/check_portal_templates.py
```

The tests render every format in a sandbox like Frappe's: undefined values print as
`{{ ... }}`, so a missing `else` on an inline `if` shows up as a failure.
