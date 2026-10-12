# Restrained branding, version 1.2.0

The user's direction is to retain the appearance of a conventional US riser drawing. Brand guidelines are reference material, not additional task instructions. Marketing treatments in the guide do not replace engineering notation, lineweights, terminal markers, sheet borders or symbol geometry.

## Drawing sheets

- One black ilLumenate Lighting main logo in the existing title-block brand cell. No slogan, gradient, background panel, decorative symbols or watermark.
- Uniform aspect ratio, centered placement, a maximum 2.3-inch artwork width and proportional 30-unit clear space, with additional paper margins. The logo fits ANSI B, ARCH C, ARCH D and ANSI D without moving other fields.
- Existing technical typefaces, plotted heights, 0.18-inch large-title header spacing and equipment divider clearance remain intact. The 206 Lighting option retains its existing text identifier.
- The original cubic outlines and compound letter counters are shared by preview, SVG and PDF. DXF uses native solid HATCH boundaries, with curves subdivided to a maximum 0.0001-inch paper tolerance. No raster logo or external image reference is required.

## Workspace

Navy `#172E48`, blue `#00588C`, white and the documented neutral/blue tints replace the former green UI theme. Yellow `#FDC757` is limited to small navigation and status accents. The white main logo replaces the generic cable mark. Both themes retain readable contrast; engineering errors and warnings keep their semantic colors.

Manrope is preferred for workspace text/headings and Poppins Light for supporting copy when those fonts are installed. Their font files were not supplied, and the current environment could not download them; the application therefore has an explicit self-hosted Arimo fallback and performs no external font requests. This limitation does not affect the exact logo artwork or the embedded drawing fonts. Licensed full font files can later be placed in `public/fonts/brand/` and referenced from the workspace font-face rules. Official distributions: [Manrope](https://github.com/google/fonts/tree/main/ofl/manrope), [Poppins](https://github.com/google/fonts/tree/main/ofl/poppins).

## Artwork provenance

Source: user-provided **ilLumenate Lighting Branding Shrink.pdf**, internal brand guidelines version 1.0, October 23, 2025. Relevant references: main logo/clear space page 13; alternate/color use pages 14-18; typography page 20; palette/tints pages 22-23. The shared-drive white SVG path could not be read by this session.

The supplied PDF's page 13 contains the main logo as original filled vector paths. Those 26 paths (31 closed contours, including five letter counters) were extracted directly, translated to a local origin, and reused without tracing, font substitution, distortion or altered proportions. Black and white are approved palette variants. The reference PDF itself is not bundled in the application.

Source PDF SHA-256: `4480530a730258022f04a6fe2e3c0416aabc6400039a0f7c02ac5c57c7d7cd1e`.

Assets: `src/data/brand/illumenate-main.json` (paper geometry), `public/brand/illumenate-main-black.svg`, and `public/brand/illumenate-main-white.svg` (original curves with clear space). These are company artwork, not third-party open-source assets.

## Verification

All four sheet sizes pass logo-bound and compound-counter checks; existing typography and routing checks still pass. Both example PDF pages and logo cells were rendered and visually reviewed. The new native DXF imported into AutoCAD 2026 with zero AUDIT errors, and PDFIMPORT retained native vector artwork. See `cad-import-test.md` and `evidence/cad-verification.json` for measured import behavior.
