// Compatible Products embed (webflow_scripts/compatible-products-json.html).
// The sync sends [{related_product, relationship_type}]; production's CMS still holds the old
// shape [{product, type}] until each product is synced again (illumenate.lighting, 2026-11-24).
// The embed must draw the cards from either shape, so it can go live before the first sync.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "../..");
const HTML = fs.readFileSync(path.join(ROOT, "webflow_scripts/compatible-products-json.html"), "utf8");
const SCRIPT = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");

function render(json) {
  const dom = new JSDOM(
    `<div class="lookup-item"><span class="lookup-sku">ill-ra01-tw</span><span class="lookup-name">Rainier TW</span>
       <a class="lookup-link" href="/products/ill-ra01-tw"></a></div>
     <div class="lookup-item"><span class="lookup-sku">ps-univ</span><span class="lookup-name">Universal PSU</span></div>
     <div id="product-json-data"></div>
     <div class="swiper-empty-comp" style="display:none"></div>
     <div id="dynamic-sliders-container"></div>
     <div class="swiper-section-blueprint" style="display:none">
       <div class="swiper-section-title"></div>
       <div class="swiper-comp"><div class="swiper-wrapper-comp"><a class="swiper-slide-comp"><span class="comp-prod-name"></span></a></div></div>
     </div>`,
    { runScripts: "outside-only" }
  );
  const { window } = dom;
  window.document.getElementById("product-json-data").textContent = JSON.stringify(json);
  window.Swiper = function Swiper() {};
  window.eval(SCRIPT);
  for (const [, callback] of window.fsAttributes) callback([]);
  const sections = [...window.document.querySelectorAll("#dynamic-sliders-container > *")];
  return {
    sections: sections.map((s) => ({
      title: s.querySelector(".swiper-section-title").textContent,
      cards: [...s.querySelectorAll(".comp-prod-name")].map((n) => n.textContent),
    })),
    empty: window.document.querySelector(".swiper-empty-comp").style.display,
  };
}

const EXPECTED = [
  { title: "Recommended With", cards: ["Universal PSU"] },
  { title: "Alternative To", cards: ["Rainier TW"] },
];

test("draws cards from the shape the sync sends", () => {
  const result = render([
    { related_product: "ill-ra01-tw", relationship_type: "Alternative To" },
    { related_product: "ps-univ", relationship_type: "Recommended With" },
    { related_product: "not-published", relationship_type: "Works With" },
  ]);
  assert.deepEqual(result.sections, EXPECTED);
  assert.equal(result.empty, "none");
});

test("draws cards from production's older shape too", () => {
  const result = render([
    { product: "ill-ra01-tw", type: "Alternative To", notes: null },
    { product: "ps-univ", type: "Recommended With", notes: null },
    { product: "dmxd", type: "Recommended With", notes: null },
  ]);
  assert.deepEqual(result.sections, EXPECTED);
  assert.equal(result.empty, "none");
});

test("shows the empty state when nothing listed is published", () => {
  const result = render([{ product: "dmxd", type: "Recommended With" }]);
  assert.deepEqual(result.sections, []);
  assert.equal(result.empty, "block");
});
