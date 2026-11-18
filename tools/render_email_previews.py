"""Render every customer and supplier email template with sample data into one HTML page.

For reviewing wording without a site: python3 tools/render_email_previews.py [out.html]
Uses the sample contexts the unit tests use (tests/portal_unit/email_template_samples.py).
"""

import html
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "tests" / "portal_unit")]

import email_template_samples as samples

from illumenate_lighting.illumenate_lighting.email_templates import library


def main(out):
	cards = []
	for template in library.TEMPLATES:
		doctype = template.doctype or "Sales Order"
		c = samples.rich(doctype)
		env = samples.environment(lambda *_a, c=c: c)
		top = samples.doc_dict(doctype, c["name"])
		subject = env.from_string(template.subject).render(**top)
		body = env.from_string(template.body()).render(**top)
		cards.append(
			f'<section id="{template.slug}"><h2>{html.escape(template.name)}</h2>'
			f'<p class="meta">{html.escape(template.trigger)} · To: {html.escape(template.to)}</p>'
			f'<div class="mail"><p class="subject">Subject: {html.escape(subject)}</p>{body}</div></section>'
		)
	page = (
		"<!doctype html><meta charset=utf-8><title>Email template previews</title>"
		"<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#111}"
		"section{margin:32px 0}.meta{color:#6b7280;font-size:13px}.mail{border:1px solid #e5e7eb;border-radius:6px;padding:16px 20px}"
		".subject{font-weight:600;border-bottom:1px solid #e5e7eb;padding-bottom:8px}</style>"
		"<h1>Email template previews (sample data)</h1>" + "".join(cards)
	)
	pathlib.Path(out).write_text(page, encoding="utf-8")
	print(f"{len(cards)} templates -> {out}")


if __name__ == "__main__":
	main(sys.argv[1] if len(sys.argv) > 1 else "email_previews.html")
