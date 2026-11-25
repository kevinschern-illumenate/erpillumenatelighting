// Downloads embed (webflow_scripts/documents-json.html).
// The sync sends the ERP rows [{document_type, document_title, document_file, display_order}];
// production's CMS still holds the old shape [{type, title, url, order}] until each product is
// synced again (illumenate.lighting, 2026-11-24). The embed must draw the cards from either.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "../..");
const HTML = fs.readFileSync(path.join(ROOT, "webflow_scripts/documents-json.html"), "utf8");
const SCRIPT = HTML.replace(/^\s*<script>/, "").replace(/<\/script>\s*$/, "");

async function render(docs) {
  const dom = new JSDOM(
    `<div id="raw-documents-json"></div>
     <div id="empty-docs-message" style="display:none"></div>
     <div id="downloads-container">
       <div id="download-template"><span class="doc-type"></span><span class="doc-title"></span>
         <a class="reg-spec-download" href="#"></a></div>
     </div>`,
    { runScripts: "outside-only" }
  );
  const { window } = dom;
  // jsdom has no innerText; the embed sets it on the type and title.
  Object.defineProperty(window.HTMLElement.prototype, "innerText", {
    get() { return this.textContent; },
    set(value) { this.textContent = value; },
  });
  window.document.getElementById("raw-documents-json").textContent = JSON.stringify(docs);
  window.eval(SCRIPT);
  if (window.document.readyState === "loading") {
    await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
  }
  return [...window.document.querySelectorAll("#downloads-container > div")].map((card) => ({
    type: card.querySelector(".doc-type").textContent,
    title: card.querySelector(".doc-title").textContent,
    href: card.querySelector(".reg-spec-download").getAttribute("href"),
  }));
}

const EXPECTED = [
  { type: "SPEC SHEET(S)", title: "Rainier Spec Sheet", href: "https://erp.example/spec.pdf" },
  { type: "IES FILE(S)", title: "Rainier IES Files", href: "https://erp.example/ies.zip" },
];

test("draws cards from the rows the sync sends, in display order", async () => {
  const cards = await render([
    { document_type: "IES File", document_title: "Rainier IES Files", document_file: "https://erp.example/ies.zip", display_order: 2 },
    { document_type: "Spec Sheet", document_title: "Rainier Spec Sheet", document_file: "https://erp.example/spec.pdf", display_order: 1 },
    { document_type: "Spec Submittal", document_title: "Old submittal", document_file: "https://erp.example/sub.pdf", display_order: 3 },
  ]);
  assert.deepEqual(cards, EXPECTED);
});

test("draws cards from production's older shape too", async () => {
  const cards = await render([
    { url: "https://erp.example/spec.pdf", type: "Spec Sheet", title: "Rainier Spec Sheet", order: 0 },
    { url: "https://erp.example/ies.zip", type: "IES File", title: "Rainier IES Files", order: 0 },
  ]);
  assert.deepEqual(cards, EXPECTED);
});
