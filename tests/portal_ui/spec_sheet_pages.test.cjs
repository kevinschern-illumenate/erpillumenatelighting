// Spec sheet page breaks (owner, 2026-11-25): the Part Number Builder starts its own page,
// except on Extrusion Kits, where it may follow Dimensions; a kit's Components start their own
// page. JSDOM has no layout (every height is 0), so only these own-page rules add pages.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { JSDOM } = require("jsdom");

const FORMAT = fs.readFileSync(
  path.join(__dirname, "../../n8n_workflows/lib/ill_format_data_to_inject.js"),
  "utf8"
);

const TEMPLATE = `<html><head></head><body>
<div class="pdf-spec-container"><div class="page-wrapper"><div class="spec-main-wrapper">
  <div id="dimensions" class="section-wrapper"><div class="spec-h2">Dimensions</div></div>
  <div id="part-no-builder" class="section-wrapper"><div class="spec-h2">Part Number Builder</div></div>
  <div id="components" class="section-wrapper"><div class="spec-h2">Components</div></div>
</div></div></div>
</body></html>`;

async function pages(productType) {
  // A section with no data is hidden, so each gets one row.
  const product = {
    product_name: "Rainier",
    product_slug: "kit-ra01",
    product_type: productType,
    configurator_options: [
      { option_step: 1, option_type: "Lens", option_label: "Lens", is_required: 1, allowed_values_json: "[]" },
    ],
    kit_components: [{ component_type: "Profile", component_item: "P1", component_description: "Profile" }],
  };
  const inputs = {
    "(ilL) Fetch Webflow Template": { data: TEMPLATE },
    "Get Product Info": { message: { products: [product] } },
  };
  const $ = (name) => ({ first: () => ({ json: inputs[name] }) });
  const html = vm.runInNewContext(`(function() {${FORMAT}\n})()`, { $ }).json.injected_html;
  const dom = new JSDOM(html, { runScripts: "dangerously" });
  await new Promise((resolve) => dom.window.addEventListener("load", resolve));
  await new Promise((resolve) => setTimeout(resolve, 0));
  return [...dom.window.document.querySelectorAll(".page-wrapper")].map((page) =>
    [...page.querySelectorAll(".spec-main-wrapper > .section-wrapper")]
      .filter((el) => el.style.display !== "none")
      .map((el) => el.id)
  );
}

test("an Extrusion Kit's part number follows Dimensions; Components start a page", async () => {
  assert.deepEqual(await pages("Extrusion Kit"), [
    ["dimensions", "part-no-builder"],
    ["components"],
  ]);
});

test("other products start the Part Number Builder on its own page", async () => {
  assert.deepEqual(await pages("Fixture Template"), [
    ["dimensions"],
    ["part-no-builder", "components"],
  ]);
});
