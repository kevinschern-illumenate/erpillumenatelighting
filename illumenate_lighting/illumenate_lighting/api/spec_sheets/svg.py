# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Point-accurate page description rendered as inline SVG.

Each page is one SVG whose user unit is a PDF point, so coordinates measured
from the InDesign exports are used as-is. SVG text is positioned by baseline,
which is how InDesign positions type; HTML boxes would add font-dependent
rounding. The document is self-contained: fonts and images are data URIs.
"""

import base64
import re
from html import escape
from pathlib import Path

from illumenate_lighting.illumenate_lighting.api.spec_sheets import tokens
from illumenate_lighting.illumenate_lighting.api.spec_sheets.text import FONTS_DIR, text_width

IMAGE_TYPES = {
	".svg": "image/svg+xml",
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".webp": "image/webp",
}


def _num(value):
	return f"{value:.3f}".rstrip("0").rstrip(".")


_SVG_ROOT = re.compile(rb"<svg\b[^>]*>", re.S)
_SVG_LENGTH = re.compile(r"^\s*([0-9.]+)\s*(pt|px)?\s*$")


def svg_size(content):
	"""Natural (width, height) in points of an SVG exported at print size.

	Illustrator writes lengths in px at 72 per inch, so px and unitless values are points.
	"""
	root = _SVG_ROOT.search(content)
	if not root:
		raise ValueError("Not an SVG document")
	size = []
	for attribute in ("width", "height"):
		found = re.search(rf'\b{attribute}="([^"]+)"'.encode(), root.group(0))
		match = _SVG_LENGTH.match(found.group(1).decode()) if found else None
		if not match:
			raise ValueError(f"SVG {attribute} must be a point or pixel length")
		size.append(float(match.group(1)))
	return tuple(size)


def data_uri(content, mime):
	return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


# Marketing marks FPO ("for position only") placeholder artwork with InDesign's
# "C=0 M=100 Y=0 K=0" magenta swatch. It must never reach a customer sheet.
# sRGB renderings of that swatch under common CMYK profiles, plus pure magenta.
_FPO_COLOR = re.compile(
	rb"#(?:ec008c|e6007e|e4007c|ff00ff|f0f)\b|rgb\(\s*(?:236\s*,\s*0\s*,\s*140|255\s*,\s*0\s*,\s*255)\s*\)",
	re.I,
)


def has_fpo(content):
	"""True if SVG bytes use the FPO magenta swatch."""
	return bool(_FPO_COLOR.search(content))


def reject_fpo(content, ref):
	"""Raise if SVG artwork still contains FPO magenta."""
	if has_fpo(content):
		raise ValueError(f"{ref!r} contains FPO magenta placeholder artwork; replace it before publishing")


def image_mime(name):
	"""MIME type for artwork Chromium can print (not TIFF, EPS or AI)."""
	mime = IMAGE_TYPES.get(Path(name.split("?", 1)[0]).suffix.lower())
	if not mime:
		raise ValueError(f"Unsupported asset type: {name!r} (use SVG, PNG, JPEG or WebP)")
	return mime


class DirectoryAssets:
	"""Resolve asset references to files in one directory (fixtures and local tools)."""

	def __init__(self, root):
		self.root = Path(root)

	def get(self, ref):
		path = (self.root / ref).resolve()
		if self.root.resolve() not in path.parents:
			raise ValueError(f"Asset outside the asset directory: {ref!r}")
		return path.read_bytes(), image_mime(path.name)


FILE_URL_PREFIXES = ("/files/", "/private/files/")


class FileURLAssets:
	"""Resolve Frappe File URLs through ``load(url) -> bytes`` (see ``spec_sheets.site``).

	Each URL is loaded once per instance; build one per document.
	"""

	def __init__(self, load):
		self.load = load
		self._loaded = {}

	def get(self, ref):
		if not ref.startswith(FILE_URL_PREFIXES):
			raise ValueError(f"Not a File URL: {ref!r}")
		mime = image_mime(ref)
		if ref not in self._loaded:
			self._loaded[ref] = self.load(ref)
		return self._loaded[ref], mime


class CompositeAssets:
	"""File URLs go to ``files``; everything else to ``default`` (a directory)."""

	def __init__(self, default, files=None):
		self.default = default
		self.files = files

	def get(self, ref):
		if ref.startswith(FILE_URL_PREFIXES):
			if not self.files:
				raise ValueError(f"No File resolver for {ref!r}")
			return self.files.get(ref)
		return self.default.get(ref)


class Page:
	def __init__(self, colors, assets, brand_assets=None):
		self.colors = colors
		self.assets = assets
		self.brand_assets = brand_assets
		self.fonts = set()
		self._defs = []
		self._body = []

	def _color(self, role_or_hex):
		return role_or_hex if role_or_hex.startswith("#") else self.colors[role_or_hex]

	def text(self, x, baseline, content, style, anchor="start", color=None):
		spec = tokens.STYLES[style]
		self.fonts.add(spec.font)
		anchor_attr = "" if anchor == "start" else f' text-anchor="{anchor}"'
		self._body.append(
			f'<text x="{_num(x)}" y="{_num(baseline)}"{anchor_attr} '
			f"style=\"font-family:'{spec.font}';font-size:{_num(spec.size)}px;"
			f'letter-spacing:{_num(spec.letter_spacing)}px;fill:{self._color(color or spec.color)}">'
			f"{escape(content)}</text>"
		)

	def width(self, content, style):
		spec = tokens.STYLES[style]
		return text_width(content, spec.font, spec.size, spec.tracking)

	def line(self, x1, y1, x2, y2, color, width):
		self._body.append(
			f'<line x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(x2)}" y2="{_num(y2)}" '
			f'stroke="{self._color(color)}" stroke-width="{_num(width)}"/>'
		)

	def circle(self, cx, cy, r, color):
		self._body.append(
			f'<circle cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}" fill="{self._color(color)}"/>'
		)

	def gradient_rect(self, x, y, width, height, stops, reverse=False):
		"""Horizontal linear gradient; ``stops`` are (colour, opacity, offset %) triples."""
		if reverse:
			stops = [(color, opacity, 100 - offset) for color, opacity, offset in reversed(stops)]
		gradient_id = f"g{len(self._defs)}"
		stop_tags = "".join(
			f'<stop offset="{_num(offset)}%" stop-color="{color}"'
			+ (f' stop-opacity="{_num(opacity)}"' if opacity < 1 else "")
			+ "/>"
			for color, opacity, offset in stops
		)
		self._defs.append(
			f'<linearGradient id="{gradient_id}" x1="0" y1="0" x2="1" y2="0">{stop_tags}</linearGradient>'
		)
		self._body.append(
			f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" fill="url(#{gradient_id})"/>'
		)

	def natural_size(self, ref, brand=False):
		content, mime = (self.brand_assets if brand else self.assets).get(ref)
		if mime != "image/svg+xml":
			raise ValueError(f"Natural size needs an SVG asset: {ref!r}")
		return svg_size(content)

	def image(self, ref, x, y, width, height, radius=None, fit="none", brand=False):
		content, mime = (self.brand_assets if brand else self.assets).get(ref)
		if mime == "image/svg+xml":
			reject_fpo(content, ref)
		clip = ""
		if radius:
			clip_id = f"c{len(self._defs)}"
			self._defs.append(
				f'<clipPath id="{clip_id}"><rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" '
				f'height="{_num(height)}" rx="{_num(radius)}" ry="{_num(radius)}"/></clipPath>'
			)
			clip = f' clip-path="url(#{clip_id})"'
		aspect = {"none": "none", "cover": "xMidYMid slice", "contain": "xMidYMid meet"}[fit]
		self._body.append(
			f'<image href="{data_uri(content, mime)}" x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" '
			f'height="{_num(height)}" preserveAspectRatio="{aspect}"{clip}/>'
		)

	def svg(self):
		defs = f"<defs>{''.join(self._defs)}</defs>" if self._defs else ""
		return (
			f'<svg class="page" xmlns="http://www.w3.org/2000/svg" width="{_num(tokens.PAGE_WIDTH)}pt" '
			f'height="{_num(tokens.PAGE_HEIGHT)}pt" viewBox="0 0 {_num(tokens.PAGE_WIDTH)} {_num(tokens.PAGE_HEIGHT)}">'
			f"{defs}{''.join(self._body)}</svg>"
		)


def _font_faces(fonts):
	faces = []
	for font in sorted(fonts):
		content = (FONTS_DIR / f"{font}.ttf").read_bytes()
		faces.append(
			f"@font-face{{font-family:'{font}';src:url({data_uri(content, 'font/ttf')}) format('truetype')}}"
		)
	return "".join(faces)


def document(pages, title):
	fonts = set().union(*(page.fonts for page in pages)) if pages else set()
	style = (
		f"{_font_faces(fonts)}"
		f"@page{{size:{_num(tokens.PAGE_WIDTH)}pt {_num(tokens.PAGE_HEIGHT)}pt;margin:0}}"
		"html,body{margin:0;padding:0}"
		"svg.page{display:block;break-after:page}svg.page:last-child{break-after:auto}"
		"text{white-space:pre;font-kerning:normal;font-feature-settings:'liga' 1,'kern' 1}"
	)
	return (
		f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
		f"<style>{style}</style></head><body>{''.join(page.svg() for page in pages)}</body></html>"
	)
