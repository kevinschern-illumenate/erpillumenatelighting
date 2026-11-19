# Print fonts

TrueType copies of the brand webfonts for the ilL print formats
(`templates/print/ill_print.html`). Frappe renders PDFs with wkhtmltopdf, which cannot
read woff2, so these are converted from the woff2 files one folder up with fontTools:

- `Poppins-Regular/Medium/SemiBold.ttf`: the Poppins woff2 files, re-wrapped as TrueType.
- `Manrope-SemiBold/Bold.ttf`: static 600 and 700 instances of `Manrope-Variable.woff2`.

Both families are licensed under the SIL Open Font License 1.1 (see `../Poppins-OFL.txt`;
Manrope uses the same license).
