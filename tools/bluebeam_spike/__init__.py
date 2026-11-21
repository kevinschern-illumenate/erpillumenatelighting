"""Bluebeam Revu spike tooling for draw-to-quote (implementation plan WP 2.1-2.7).

``probe_pdf`` dumps what a marked-up PDF actually stores (viewports, measure dictionaries,
annotations, private keys); ``compare_lengths`` checks the lengths it computes against the
AutoCAD toolkit's ``ilq/2`` ground truth. Both are read-only and never execute PDF content.
See ``tools/bluebeam_spike/README.md``.
"""
