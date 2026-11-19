# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Starting text for the Terms and Conditions records the ilL print formats use.

patches/seed_print_terms.py inserts each record once, if missing. After that the
records belong to staff (Desk > Terms and Conditions): edit them there, not here, and
every quote, order and invoice prints the current wording. A document's own Terms
field, when filled in, prints instead.

This is a business draft, not legal advice: have counsel review it before relying on it.
"""

SALES_TERMS = """
<p><strong>1. Quotations and pricing.</strong> Prices are in US dollars and hold until the quotation's valid-until date. They are based on the quantities, lengths and options shown; changes to scope may change price and lead time. Sales tax, where it applies, and freight are added to the invoice unless shown otherwise.</p>
<p><strong>2. Orders.</strong> An order is accepted when we issue a Sales Order acknowledgement. Please review it and tell us of any discrepancy within two business days.</p>
<p><strong>3. Payment.</strong> Payment is due in advance of shipment unless your account has approved credit terms. Approved accounts pay Net 30 from the invoice date. We may hold shipments on accounts with past-due balances.</p>
<p><strong>4. Custom products.</strong> Configured, cut-to-length and special-order products are built for your order. Once released to production they cannot be cancelled, changed or returned. Linear products are built to the nearest manufacturable cut increment, so the built length can differ slightly from the requested length; both are shown on the line.</p>
<p><strong>5. Lead times.</strong> Ship dates are estimates that start from order acknowledgement and, where due, receipt of payment. We confirm dates as production is scheduled and are not liable for delays outside our control.</p>
<p><strong>6. Shipping and delivery.</strong> Orders ship from Bothell, WA by the method shown. Inspect shipments on arrival, note any visible damage on the carrier's delivery receipt, and report damage or shortages within five business days.</p>
<p><strong>7. Returns.</strong> Unused stock items in their original packaging may be returned within 30 days of delivery with a return authorization (RMA) from us. A restocking fee may apply, depending on the size of the return. Custom products (section 4) are not returnable.</p>
<p><strong>8. Warranty.</strong> ilLumenate products are warranted against defects in materials and workmanship for the period on the product's spec sheet (five years for most products) from the ship date, when installed and operated per our instructions and applicable electrical codes. We will repair or replace, at our option, a product that fails under warranty. The warranty does not cover labor, removal or reinstallation, damage from improper installation, power or handling, or non-ilLumenate components. To start a claim, contact us with your order number and photos.</p>
<p><strong>9. Installation.</strong> Products must be installed by a qualified electrician to the NEC and local codes, using compatible power supplies, drivers and dimmers.</p>
<p><strong>10. Limitation of liability.</strong> Our liability for any claim is limited to the price paid for the product concerned. We are not liable for incidental or consequential damages, including installation or labor costs.</p>
""".strip()

RETAIL_TERMS = """
<p><strong>Pricing.</strong> Prices shown are manufacturer's suggested retail prices for budgeting. Your dealer sets the final price and quotes freight, sales tax and installation.</p>
<p><strong>Made for your project.</strong> Configured and cut-to-length products are built to order and cannot be cancelled or returned once in production. Linear products are built to the nearest manufacturable length, which can differ slightly from the requested length.</p>
<p><strong>Lead times.</strong> Ship dates are estimates; your dealer will confirm them when the order is placed.</p>
<p><strong>Warranty.</strong> ilLumenate products carry a limited warranty against defects in materials and workmanship for the period on each product's spec sheet (five years for most products), when installed by a qualified electrician to code with compatible power supplies and controls. Your dealer handles warranty claims.</p>
""".strip()

PURCHASE_TERMS = """
<p><strong>1. Acknowledgement.</strong> Please confirm this order within two business days with your pricing and ship date. Quote our PO number on every acknowledgement, packing list, invoice and carton.</p>
<p><strong>2. Prices and changes.</strong> Prices are as shown on this order. Do not change price, quantity, specification, materials or ship date, or substitute parts, without our written approval.</p>
<p><strong>3. Delivery.</strong> Ship by the required-by date, complete unless we approve a partial shipment. Tell us immediately of any delay. Freight terms are as shown on this order.</p>
<p><strong>4. Packing and labeling.</strong> Pack to prevent damage in transit. Label each carton with our PO number and the item code or your part number, and include a packing list.</p>
<p><strong>5. Quality.</strong> Goods must match the agreed specifications, drawings and samples. We may reject nonconforming or damaged goods and return them at your expense for credit, repair or replacement.</p>
<p><strong>6. Invoicing and payment.</strong> Send invoices to our accounts payable team referencing this PO. Payment terms are as agreed on your supplier account.</p>
""".strip()

# Record name -> (terms, selling, buying). Names match printing.TERMS.
RECORDS = {
	"ilL Sales Terms": (SALES_TERMS, 1, 0),
	"ilL Retail Terms": (RETAIL_TERMS, 1, 0),
	"ilL Purchase Terms": (PURCHASE_TERMS, 0, 1),
}
