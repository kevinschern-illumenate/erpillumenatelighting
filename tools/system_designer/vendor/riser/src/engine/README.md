# Pure engine boundary

Phase 4 owns graph resolution, electrical calculations, wire selection, DMX validation, and BOM aggregation. No React imports, DOM access, persistence, or drawing logic belong here. Add unit tests covering every calculation and validation branch. UI, drawing, and serializers consume these results; they must not independently recompute electrical values.
