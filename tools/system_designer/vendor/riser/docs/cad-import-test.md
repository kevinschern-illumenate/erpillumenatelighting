# CAD import validation

Tested on 2026-09-25 with installed AutoCAD 2026 Core Console, build W.74.0.0, using an isolated temporary profile and disposable drawing. No existing user drawing was opened or saved. The exported two-sheet example uses ARCH D 36 × 24 paper-inch geometry. Machine-readable import measurements and the relevant console output are in `docs/evidence/`.

## Native DXF

Open a per-sheet DXF, or use DXFIN on `example-riser-tiled.dxf` in a new inch-unit drawing. Run AUDIT with **No** to inspect without repair. Verify:

1. `$INSUNITS=1`, `$MEASUREMENT=0`, `$LTSCALE=1` and R2007 `AC1021`.
2. Each border reference square measures exactly 1.000 × 1.000 inch. Tiled ARCH D sheet origins differ by 38 inches (36-inch sheet plus 2-inch gap).
3. Named NCS layers and plotted lineweights/linetypes exist; `E-ANNO-QAFL` is absent.
4. Device symbols are INSERTs of native BLOCKs. Each insert contains TAG, MODEL, VIN, VOUT, WATTS, LOAD_PCT, DMX_ADDR and LOCATION attributes, including invisible data fields. Use Data Extraction on the diagram inserts; legend inserts are also blocks and can be filtered by their descriptive tags.
5. Single-line annotations are TEXT, paragraphs are MTEXT. Body TEXT/MTEXT group 40 is 0.09375 inch. Font styles MAIN/BOLD reference `arial.ttf`/`arialbd.ttf` by default.

**Result:** AutoCAD imported the generated DXF and AUDIT reported **0 errors found, 0 fixed**. Native text, lines/polylines, symbols and all eight attributes per insert were independently counted. Version 1.2.0 adds 52 native SOLID HATCH entities for the two title-block logos, with five compound letter counters per logo; AUDIT still reports zero errors. The two one-inch reference squares measured correctly. Unit tests also round-trip layers, entities, attributes, tile offsets, arcs and text with dxf-parser. Solid-hatch and Unicode encodings receive structural checks; dxf-parser does not implement HATCH.

For Roboto Condensed, install the supplied TTF files before opening; DXF references fonts rather than embedding them. ODA Viewer was not installed and its manual viewing check remains unperformed. No ODA result is claimed.

## Layered PDF and PDFIMPORT

The PDF contains full embedded Arimo (or chosen Roboto Condensed) TrueType fonts without subsetting, whole-string text-show operations, vector paths, matching dash arrays and optional-content layer dictionaries. It has no images, clipping paths, transparency or per-glyph text positioning. PDF body capital height is 3/32 inch; PDF font em sizes are adjusted for the font cap-height ratio.

For a new inch-unit drawing, import a page at insertion 0,0, scale 1 and rotation 0. Enable vector geometry and TrueType text; choose **Use PDF layers**, **Join line and arc segments**, **Apply lineweight properties** and **Infer linetypes from collinear dashes**. Disable raster import and block import when inspecting individual entities. Equivalent test settings are `PDFIMPORTFILTER=8`, `PDFIMPORTLAYERS=0`, `PDFIMPORTMODE=22` (2 + 4 + 16). Record and restore existing system-variable settings if testing in your usual profile.

**Observed behavior:** the one-inch square imports at exactly 1.000 inch and geometry retains distinct `PDF_E-*` layers and lineweights (for example, 0.35 mm power wiring). Whole strings remain editable/searchable, without exploded glyph entities.

**Deviation from the original Phase 8 acceptance wording:** AutoCAD 2026 imports PDF TrueType strings as **MTEXT**, groups imported text on **`PDF_Text`**, and adds **`PDF_`** to geometry layer names. Imported text's nominal CAD height is remapped by AutoCAD/font metrics (the 3/32-inch plotted body becomes approximately 0.0981-inch MTEXT height). This does not meet the requested literal “TEXT objects on identical original layers with identical nominal height” criterion. The PDF content itself has the correct plotted size and OCG names; those import transformations are not controlled by the exporter. Use the native DXF when exact CAD text entities, heights, layers and attributes are required. No destructive post-import normalization is performed automatically.

The version 1.2.0 logo imports as native spline/solid/hatch geometry on the title-block layer (128 SPLINE, 5 SOLID and 18 HATCH entities on the first page). The logo is intentionally outlined artwork; engineering text remains editable.

The PDF structure is tested independently, and every exported example page is rendered for visual inspection. Deterministic PDF/DXF bytes are checked for identical project/model inputs. The exported project date supplies PDF metadata dates; ZIP entries use a fixed timestamp.

## References

- [AutoCAD PDFIMPORT](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Core/files/GUID-ADEE1DE4-3CEF-432D-95F2-014F326E8B2A.htm)
- [PDFIMPORTMODE flags](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Core/files/GUID-669F39FF-972F-4C24-8841-E42185A44843.htm)
- [PDFIMPORTLAYERS and layer prefixes](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-LT/files/GUID-F5A62383-B2F2-4003-8BE2-5E3E5419593D.htm)
- [DXF TEXT group codes](https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-DXF/files/GUID-62E5383D-8A14-47B4-BFC4-35824CAE8363.htm)
- [DXF MTEXT, including rotation in radians](https://help.autodesk.com/cloudhelp/2023/ENU/AutoCAD-DXF/files/GUID-5E5DB93B-F8D3-4433-ADF7-E92E250D2BAB.htm)
