// Extra dimension drawings on the spec sheet (Spec Gallery rows of section "Dimensions").
// The page's .dimensions-list-wrapper holds the main .dimension-item and one
// #dimension-item.dimension-item.other: a #dimension-title over one #spec-dims-img-other. All the
// extra drawings go in that one .dimension-item.other, each title over its drawings, so its
// vertical flex stacks them (owner, 2026-11-25). Before, every drawing (then every title) got its
// own .dimension-item, and the list wrapper's wrapping row put them side by side.
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
  const html = vm.runInNewContext(`(function() {${FORMAT}\n})()`, { $ }).json
    .injected_html;
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
  // Each shown .dimension-item.other as its children in order: "title:<text>" or "img:<src>".
  return [...doc.querySelectorAll(".dimension-item.other")]
    .filter(shown)
    .map((item) =>
      [...item.children]
        .filter(shown)
        .map((el) =>
          el.tagName === "IMG"
            ? `img:${el.getAttribute("src")}`
            : `title:${el.textContent}`
        )
    );
}

const row = (image, title, section = "Dimensions") => ({
  section,
  title,
  image,
});

test("every extra drawing stacks in the one item, each title over its drawings", () => {
  // ILL-RA01-SW on production: three drawings, three titles.
  assert.deepEqual(
    render([
      row("/files/side.jpg", "Side View"),
      row("/files/linear.jpg", "Top View with Linear Louver"),
      row("/files/hex.jpg", "Top View with Hex Louver"),
      row("/files/x.svg", "Mounting", "Accessories Dimensions"),
    ]),
    [
      [
        "title:Side View",
        "img:/files/side.jpg",
        "title:Top View with Linear Louver",
        "img:/files/linear.jpg",
        "title:Top View with Hex Louver",
        "img:/files/hex.jpg",
      ],
    ]
  );
});

test("drawings sharing a title, or untitled, sit under the title before them", () => {
  assert.deepEqual(
    render([
      row("/files/a.svg", "Side View"),
      row("/files/b.svg", "Side View"),
      row("/files/c.svg", ""),
    ]),
    [
      [
        "title:Side View",
        "img:/files/a.svg",
        "img:/files/b.svg",
        "img:/files/c.svg",
      ],
    ]
  );
});

test("untitled drawings only: no title shown", () => {
  assert.deepEqual(
    render([row("/files/a.svg", ""), row("/files/b.svg", null)]),
    [["img:/files/a.svg", "img:/files/b.svg"]]
  );
});

test("no Dimensions rows: the pattern stays hidden", () => {
  assert.deepEqual(render([]), []);
});
