# Drawing boundary

Zod validates the shared geometry model in paper inches with a lower-left origin. Layout is calculated before any wire or continuation is drawn. SVG, PDF and DXF serialize the same blocks, terminals, paths, bridges and annotations.

## Placement and pagination

The invisible functional columns run from panels on the left through enclosures, downstream supplies, controls, and loads on the right. A supply feeding a cabinet stays upstream of that cabinet. Within each named enclosure, supplies occupy the left column, controls the middle, and assigned loads/accessories the right. Top-to-bottom flow applies the corresponding row order.

Cabinets are compound layout units. The complete project's power graph determines their stage order once, so pagination does not change the meaning of a column. Feedback between cabinets on different circuits is condensed before ranking. DMX daisy-chain order helps sort control rows. Independent column stacks align to connected neighbors; a large load fanout does not reserve empty rows in every upstream column. AC feed-through retains the supply column.

Pagination keeps fitting enclosures together across circuits. It recombines fitting groups and brings a fitting prefix of load receivers onto their source's sheet. Parallel receiver banks wrap only on sheets without their local power source, avoiding tangled feeders across intervening load banks. Wider row channels are tried before subdividing a congested page. Equipment is never moved after routing. Therefore, same-sheet cables are actual connections; X references exist only across sheet boundaries.

Show schedules reserves a lower band for schedule content before placement. Turning it off makes that space available to the column layout and can reduce the number of diagram sheets. The composer fills clear regions below diagram primitives before creating schedule-only sheets. No text or symbols are scaled down to fit. Body capital height remains at least 3/32 inch.

Absolute manual pins remain authoritative. Automatic groups colliding with a pin can move within their own column. A pin that separates enclosure members may require split outlines to avoid enclosing unrelated devices. Reset all pins restores the fully automatic arrangement.

## Wires and clearances

Equipment uses plain labeled rectangles. Cables attach to the facing equipment edges; same-column chains use the facing top/bottom edges in left-to-right flow. Port labels retain the engine's physical port names. Attachment positions are diagrammatic and do not specify a manufacturer's terminal arrangement or authorize extra terminal conductors.

All cables use the same orthogonal obstacle/occupancy router. It reserves equipment clearances and other cables' terminal stubs, prohibits parallel lane sharing within 1/8 plotted inch, requires 0.20 plotted inch between parallel cables and enclosure edges, penalizes cable crossings, and simplifies paths. Perpendicular enclosure entries remain allowed. Borders reserve 0.55 inch around equipment and 0.75 inch above it. Enclosure headings are obstacles. Horizontal bridges indicate a crossing without a connection. Complete routed paths, including terminal stubs, are checked against occupied cable lanes.

Continuation bubbles and complete TO/FROM labels are reserved before routing. Callouts stay outside enclosures and avoid equipment, wires, headings, QA text, other callouts and other bubbles. Dense output banks use taller symbols and aligned continuation rows. Grouped outgoing power references retain every destination in the continuation index. Every control cable keeps an individual paired reference, exact protocol, W-tag and remote device/port.

Signal labels take precedence over optional power details and terminal captions. If no clear signal label fits, the layout widens row channels or subdivides the page; pinned layouts report an obstruction. Power callouts can fall back to compact W-tags, with a layout note if no label fits. Electrical calculations, cable identities and schedules are independent of the placement algorithm.
