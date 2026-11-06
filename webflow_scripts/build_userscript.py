"""Build staging.user.js: the product page scripts as one Tampermonkey userscript for the staging
site, which has no Site plan and so cannot hold custom code.

    python3 webflow_scripts/build_userscript.py

The userscript runs only on staging-illumenate.webflow.io product pages, at document-start in the
page itself (so jQuery, Webflow and the DOMContentLoaded listeners work as they do in custom code).
<script src> tags become @require, <style> blocks are added to the page, inline scripts run in
file order. Elements that hold CMS data ({{wf:...}} placeholders) cannot come from a userscript:
on staging they must exist on the page as Designer text elements with the same id (listed in the
header).
"""

import re
from pathlib import Path

HERE = Path(__file__).parent
ORDER = [
	"products-collection-head.html",
	"specifications-json.html",
	"features-json.html",
	"documents-json.html",
	"kit-components-json.html",
	"configurator-options-json.html",
	"compatible-products-json.html",
	"products-collection-before-body.html",
]
MATCH = "https://staging-illumenate.webflow.io/products/*"


def parts(html):
	requires = re.findall(r'<script[^>]*\bsrc="([^"]+)"[^>]*>\s*</script>', html)
	styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
	links = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
	scripts = [
		body
		for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", html, re.S)
		if "src=" not in attrs and "application/json" not in attrs
	]
	holders = re.findall(r'id="([^"]+)"[^>]*>\s*\{\{wf:([a-z0-9-]+)', html)
	return requires, styles, links, scripts, holders


DATA_IDS = re.compile(r"getElementById\('([a-z][a-z-]*)'\)")


def others(code, known):
	found = []
	for body in code:
		for element_id in DATA_IDS.findall(body):
			if element_id not in known and element_id not in found:
				found.append(element_id)
	return found


def build():
	requires, css, links, code, holders = [], [], [], [], []
	for name in ORDER:
		r, s, link, c, h = parts((HERE / name).read_text(encoding="utf-8"))
		requires += [u for u in r if u not in requires]
		links += [u for u in link if u not in links]
		css += s
		code += [f"// ---- {name} ----\n{body.strip()}" for body in c]
		holders += h
	header = [
		"// ==UserScript==",
		"// @name         ilLumenate staging product page scripts",
		"// @namespace    https://illumenate.lighting/",
		"// @version      1",
		"// @description  Main-site product page custom code, for testing on the staging Webflow site",
		f"// @match        {MATCH}",
		"// @run-at       document-start",
		"// @grant        none",
		*[f"// @require      {url}" for url in requires],
		"// ==/UserScript==",
		"// Built by webflow_scripts/build_userscript.py; edit the .html files, not this file.",
		"// CMS data holders the page needs (Designer text elements bound to the field, hidden):",
		*[f"//   #{element_id} <- {field}" for element_id, field in holders],
		"// Also read by the scripts (their holders are set up in the Designer, not in these files):",
		*[f"//   #{element_id}" for element_id in others(code, {h for h, _ in holders})],
	]
	style = "\n".join(css).replace("`", "\\`")
	body = (
		f"""
(function () {{
  const addStyles = () => {{
    {"".join(f"const l{i} = document.createElement('link'); l{i}.rel = 'stylesheet'; l{i}.href = '{u}'; document.head.appendChild(l{i});" for i, u in enumerate(links))}
    const style = document.createElement('style');
    style.textContent = `{style}`;
    document.head.appendChild(style);
  }};
  if (document.head) addStyles(); else document.addEventListener('DOMContentLoaded', addStyles);
}})();

"""
		+ "\n\n".join(code)
		+ "\n"
	)
	(HERE / "staging.user.js").write_text("\n".join(header) + "\n" + body, encoding="utf-8")


if __name__ == "__main__":
	build()
	print("webflow_scripts/staging.user.js written")
