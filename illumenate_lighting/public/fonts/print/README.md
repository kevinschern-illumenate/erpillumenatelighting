# Print fonts

TrueType copies of the brand webfonts for the ilL print formats
(`templates/print/ill_print.html`). Frappe renders PDFs with wkhtmltopdf, which cannot
read woff2, so these are converted from the woff2 files one folder up with fontTools:

- `Poppins-Regular/Medium/SemiBold.ttf`: the Poppins woff2 files, re-wrapped as TrueType.
- `Manrope-Bold.ttf`: a static 700 instance of `Manrope-Variable.woff2`.

Only the Fixture Schedule uses them (`styles(brand=True)`); other documents print in Helvetica.

Each file is renamed internally to its own family ("ilL Print Poppins", "ilL Print Poppins
Medium", "ilL Print Poppins SemiBold", "ilL Print Manrope Bold") with one regular face.
wkhtmltopdf's WebKit groups fonts by their internal family: the stock Poppins Medium declares
its typographic family as "Poppins", so it collided with Poppins Regular and was used for all
body text. The stylesheet names the exact face (printing.PRINT_FONTS) and keeps weights normal.

Both families are licensed under the SIL Open Font License 1.1 (see `../Poppins-OFL.txt`;
Manrope uses the same license).
