# Drafting a DXF for ilLumenate draw-to-quote

Use this when you draw without the ilLumenate CAD toolkit. Upload the DXF on the schedule page
(Import Drawing); the portal builds every run with the configurator, exactly as for a toolkit drawing.

## Before you save
1. Set the drawing units (UNITS): inches, feet, millimetres, centimetres or metres. Unitless drawings are refused.
2. Draw at full size (1:1). Calibrate any PDF underlay first.
3. Save as an ASCII DXF (SAVEAS, DXF, not binary). Up to 20 MB.

## Runs
4. One polyline, line or arc per run, drawn along the tape's path. Arcs are measured as arcs.
5. Put each run on a layer named ILM-TAPE-<template code>, for example ILM-TAPE-led-hd-sw
   (LED tape, COB tape or neon). Template codes are in the CAD catalog and on the portal product pages.
6. Linear fixtures go on ILM-LINEAR-<fixture template>, for example ILM-LINEAR-ILL-RA01-SW, and need a
   saved preset for their options: choose it per layer when you import.
7. Runs on one layer share their options (CCT, output, environment). Use a layer per combination, or
   choose a preset per layer on import. Options left open are asked for on the import preview.
8. Do not draw jumpered segments as separate runs: one run per powered length. Add jumpers in the portal.

## Rooms and supplies
9. Draw each room as a closed polyline on ILM-ROOM-<room name>, for example ILM-ROOM-Kitchen.
   A run belongs to the room its first point is in; the room becomes the schedule line's location.
10. Mark power supply locations with a block on layer ILM-CAB with attributes TAG (CAB-1) and RATING
    (Dry, Damp or Wet).

## After import
11. Check the preview: drawn against built lengths, splits over the max run, and runs that need a choice.
12. The schedule Type of each layer defaults to D1, D2...; rename the lines on the schedule if needed.
13. Wire paths are not read from a DXF: the System Designer estimates home runs. Use the CAD toolkit
    (ILWIRE) to measure them.
