// Extra dimension drawings on the spec sheet (Spec Gallery rows of section "Dimensions").
// The page's .dimensions-list-wrapper holds the main .dimension-item and one
// #dimension-item.dimension-item.other: a #dimension-title over one #spec-dims-img-other. The
// drawings of one title stack inside one .dimension-item.other (owner, 2026-11-25); a new title
// starts the next one. Before, every drawing got its own .dimension-item and they ran across.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "../..");
const FORMAT = fs.readFileSync(
  path.join(ROOT, "n8n_workflows/lib/ill_format_data_to_inject.js"),
  "utf8"
);

// As on illumenate.lighting/spec-sheet-templates/linear-fixtures.
const TEMPLATE = `<html><head></head><body>
<div id="dimensions" class="section-wrapper"><div class="dimensions-list-wrapper">
  <div class="dimension-item"><div class="spec-h2">Dimensions</div><img id="spec-dims-img" class="spec-dims-img" src="placeholder.svg"></div>
  <div id="dimension-item" class="dimension-item other"><div id="dimension-title" class="spec-h3 dims">#dimension-title</div>
    <img id="spec-dims-img-other" class="spec-dims-img other" src="placeholder.svg" loading="lazy"></div>
</div></div>
</body></html>`;

function render(gallery) {
  const product = {
    product_name: "Rainier [SF] Static White",
    product_slug: "ill-ra01-sw",
    product_type: "Fixture Template",
    spec_gallery: gallery,
  };
  const inputs = {
    "(ilL) Fetch Webflow Template": { data: TEMPLATE },
    "Get Product Info": { message: { products: [product] } },
  };
  const $ = (name) => ({ first: () => ({ json: inputs[name] }) });
  const html = vm.runInNewContext(`(function() {${FORMAT}\n})()`, { $ }).json.injected_html;
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      Object.defineProperty(window.HTMLElement.prototype, "innerText", {
        get() {
          return this.textContent;
        },
        set(value) {
          this.textContent = value;
        },
      });
    },
  });
  const doc = dom.window.document;
  const shown = (el) => el.style.display !== "none";
  return [...doc.querySelectorAll(".dimension-item.other")].filter(shown).map((item) => ({
    title: [...item.querySelectorAll(".spec-h3")].filter(shown).map((el) => el.textContent).join(""),
    images: [...item.querySelectorAll("img.spec-dims-img.other")].map((img) => img.getAttribute("src")),
  }));
}

const row = (image, title, section = "Dimensions") => ({ section, title, image });

test("the drawings of one title stack in one item", () => {
  assert.deepEqual(
    render([row("/files/a.svg", "Side View"), row("/files/b.svg", "Side View"), row("/files/c.svg", "Side View")]),
    [{ title: "Side View", images: ["/files/a.svg", "/files/b.svg", "/files/c.svg"] }]
  );
});

test("a new title starts the next item; untitled drawings join the one before", () => {
  assert.deepEqual(
    render([
      row("/files/a.svg", "Side View"),
      row("/files/b.svg", ""),
      row("/files/c.svg", "End View"),
      row("/files/x.svg", "Mounting", "Accessories Dimensions"),
    ]),
    [
      { title: "Side View", images: ["/files/a.svg", "/files/b.svg"] },
      { title: "End View", images: ["/files/c.svg"] },
    ]
  );
});

test("untitled drawings only: one item, its title hidden", () => {
  assert.deepEqual(render([row("/files/a.svg", ""), row("/files/b.svg", null)]), [
    { title: "", images: ["/files/a.svg", "/files/b.svg"] },
  ]);
});

test("no Dimensions rows: the pattern stays hidden", () => {
  assert.deepEqual(render([]), []);
});
