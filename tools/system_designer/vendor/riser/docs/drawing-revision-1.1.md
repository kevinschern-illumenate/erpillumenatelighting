# Drawing revision 1.1

## Typography update 1.1.1

Company branding now reads **ilLumenate Lighting** in the app, title blocks and PDF metadata. Large title-block values have 0.18 inch of clear space below their headers, measured to the top of the printed letters. Equipment blocks have an additional 1/8 inch below the header divider, giving model text over 0.15 inch of clearance. Long model names retain space above the lower ratings rows. ANSI B and ARCH C title-block rows were adjusted to fit full company names and sheet titles without shrinking the type.

All four paper sizes were checked for complete titles/branding, header clearance, field bounds and symbol-divider clearance. The example PDF was rendered and visually inspected after the update.

## Layout revision 1.1

The initial drawing used pictorial glyphs, generic shared connection points and independent routing passes. Wires could overlap, data endpoints could float above equipment, and AC feed-through could move a power supply into the wrong column.

Version 1.1 replaces that presentation with plain rectangular equipment blocks, internal tags/model/rating text, aligned equipment stages and explicit cable terminals. Power, AC feed-through and control paths attach to the equipment outline and retain physical port names from the calculation engine. The new deterministic placement runs in the existing layout worker; ELK is no longer used.

Every cable now shares one routing pass with reserved terminal stubs, equipment obstacles and occupied wire lanes. Parallel cables have at least 1/8 inch separation at plotted scale in the tested automatic layouts. Unavoidable crossings have bridges. Labels avoid wires, equipment and enclosure boundaries; compact W-tags refer to complete wire schedules. Off-sheet X references have a continuation index. Preview and exports use the same geometry; the preview now defaults to black drafting lines.

Regression checks cover outline-connected endpoints, cable/equipment collisions, independent wire separation, label/wire collisions, crossing bridges, AC feed-through port identity and all wire tags in the complete example. Both flow directions and all four paper sizes are checked. Existing 40/200-load pagination and saved-pin checks continue to pass.

The revised example has 14 devices and 14 labeled runs on its riser sheet, with schedules and legends on a second ARCH D sheet. Both PDF pages were rendered and visually checked. See `acceptance-report.md` and `evidence/` for final software and CAD validation.

Open Drawing to see the revision. Saved manual pins are still respected; **Reset all pins** restores the new automatic arrangement. Connection locations are diagrammatic and are not a manufacturer's terminal layout. No electrical calculations, product ratings or saved project data were changed by this drafting revision.
