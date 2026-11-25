// Configured spec sheet highlights for Linear Fixtures (owner, 2026-11-24).
// The n8n Format node (n8n_workflows/lib/ill_format_data_to_inject.js) tags spec sheet
// elements with data-highlight="<step>:<code>"; a tag "<a>+<b>" needs both selections. The
// product page script (webflow_scripts/configured-spec-sheet.html) draws a box over each tag
// the visitor's selections satisfy. Data: ILL-SH01-SW on staging.
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
const PAGE_SCRIPT = fs
  .readFileSync(
    path.join(ROOT, "webflow_scripts/configured-spec-sheet.html"),
    "utf8"
  )
  .replace(/^\s*<script>/, "")
  .replace(/<\/script>\s*$/, "");

const values = (list) =>
  JSON.stringify(list.map(([code, label]) => ({ code, label, value: label })));
const PRODUCT = {
  product_name: "St. Helens [SF] Static White",
  product_slug: "ill-sh01-sw",
  product_type: "Fixture Template",
  fixture_template: "ILL-SH01-SW",
  specifications: [
    {
      spec_label: "Light Color (CCT)",
      spec_value: "2700K, 3000K, 3500K, 4000K",
      display_order: 40,
    },
    {
      spec_label: "Color Rendering (CRI)",
      spec_value: "95+",
      display_order: 50,
    },
    {
      spec_label: "Lens Options",
      spec_value: "Black, Clear, Frosted, White",
      display_order: 60,
    },
    {
      spec_label: "Mounting Options",
      spec_value: "Mounting Clip, Pivot Clip",
      display_order: 70,
    },
    {
      spec_label: "Finish Options",
      spec_value: "Anodized Silver, Black, White",
      display_order: 80,
    },
  ],
  configurator_options: [
    {
      option_step: 1,
      option_type: "Environment Rating",
      option_label: "Dry/Wet",
      allowed_values_json: values([
        ["20", "Dry"],
        ["54", "Damp"],
        ["67", "Wet"],
      ]),
    },
    {
      option_step: 2,
      option_type: "CCT",
      option_label: "CCT",
      allowed_values_json: values([
        ["27K", "2700K"],
        ["30K", "3000K"],
        ["35K", "3500K"],
        ["40K", "4000K"],
      ]),
    },
    {
      option_step: 3,
      option_type: "Lens Appearance",
      option_label: "Lens",
      allowed_values_json: values([
        ["WH", "White"],
        ["FR", "Frosted"],
        ["CL", "Clear"],
        ["BK", "Black"],
      ]),
    },
    {
      option_step: 4,
      option_type: "Output Level",
      option_label: "Output",
      allowed_values_json: JSON.stringify({
        lensMap: {
          BK: [
            { code: "50", label: "50 lm/ft" },
            { code: "250", label: "250 lm/ft" },
          ],
          WH: [
            { code: "50", label: "50 lm/ft" },
            { code: "100", label: "100 lm/ft" },
          ],
          FR: [{ code: "100", label: "100 lm/ft" }],
          CL: [{ code: "100", label: "100 lm/ft" }],
        },
      }),
    },
    {
      option_step: 5,
      option_type: "Mounting Method",
      option_label: "Mounting",
      allowed_values_json: values([
        ["MC", "Mounting Clip"],
        ["PV", "Pivot Clip"],
      ]),
    },
    {
      option_step: 6,
      option_type: "Finish",
      option_label: "Finish",
      allowed_values_json: values([
        ["SV", "Anodized Silver"],
        ["BK", "Black"],
        ["WH", "White"],
      ]),
    },
  ],
  certifications: [
    "24V DC|24vdc",
    "Dry Rated|DryRated",
    "Damp Rated|DampRated",
    "Wet Rated|WetRated",
  ].map((pair) => {
    const [certification, code] = pair.split("|");
    return {
      certification,
      certification_details: {
        certification_code: code,
        badge_image: `https://erp.test/${code}.svg`,
      },
    };
  }),
  spec_gallery: [
    {
      section: "Accessories Dimensions",
      title: "Mounting Clip",
      image: "https://erp.test/mc.jpg",
    },
    {
      section: "Accessories Dimensions",
      title: "Pivot Clip",
      image: "https://erp.test/pv.jpg",
    },
  ],
  output_options: {
    columns: ["50", "100", "250"],
    rows: [
      { label: "Fixture Wattage (White Lens)", values: ["0.8W", "1.7W", "—"] },
      {
        label: "Fixture Wattage (Black Lens)",
        values: ["1.7W", "2.5W", "6.4W"],
      },
      { label: "Fixture Wattage (Other Lenses)", values: ["—", "0.8W", "—"] },
    ],
  },
  delivered_lumens: {
    lenses: [
      { key: "white", label: "White" },
      { key: "frosted", label: "Frosted" },
      { key: "clear", label: "Clear" },
      { key: "black", label: "Black" },
    ],
    rows: [
      {
        output: "50 lm/ft",
        values: { white: "56", frosted: "—", clear: "—", black: "64" },
      },
      {
        output: "100 lm/ft",
        values: { white: "112", frosted: "98", clear: "99", black: "96" },
      },
    ],
  },
};

// The parts of the linear-fixtures spec sheet page the highlights touch (ids and classes as on
// illumenate.lighting/spec-sheet-templates/linear-fixtures).
const TEMPLATE = `<html><head></head><body>
<div class="cert-wrapper"><img class="cert-icon" src="placeholder.svg"></div>
<div id="specifications"><div id="output-options">
  <div class="table-title-wrapper"><div class="table-title">Output Options (lm/ft)</div><div id="output" class="table-title">#output</div></div>
  <div class="table-data-wrapper"><div class="table-item-wrapper"><div class="table-title">#t</div><div id="output-data" class="table-item">#d</div></div></div>
</div>
<div id="spec-data-item" class="spec-data-item"><div id="spec-data-title">#t</div><div id="spec-data-value">#v</div></div></div>
<div id="delivered-lumens"><div class="table-title-wrapper"><div class="table-title">Output</div>
  <div id="lumen-table-lens" class="table-title">#l</div><div id="lumen-table-lens" class="table-title">#l</div>
  <div id="lumen-table-lens" class="table-title">#l</div><div id="lumen-table-lens" class="table-title">#l</div></div>
  <div class="table-data-wrapper"><div class="table-item-wrapper"><div id="output-item">#o</div>
  <div id="output-c1">#</div><div id="output-c2">#</div><div id="output-c3">#</div><div id="output-c4">#</div></div></div></div>
<div id="acc-dimensions"><div id="accdimension-item"><div id="accdimension-title">#t</div><img id="accdim-img"></div></div>
</body></html>`;

function render(product = PRODUCT) {
  // n8n hands the node fresh data on every run; the node adds fields to the product it reads.
  const inputs = {
    "(ilL) Fetch Webflow Template": { data: TEMPLATE },
    "Get Product Info": { message: { products: [structuredClone(product)] } },
  };
  const $ = (name) => ({ first: () => ({ json: inputs[name] }) });
  const html = vm.runInNewContext(`(function() {${FORMAT}\n})()`, { $ }).json
    .injected_html;
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    // jsdom has no innerText; the page script sets text with it, as browsers allow.
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
  return dom.window.document;
}

// A cell's tag sits on the cell or on the span around its text.
const tagOf = (el) =>
  (el &&
    (el.getAttribute("data-highlight") ||
      el.querySelector("[data-highlight]")?.getAttribute("data-highlight"))) ||
  "";
const byText = (doc, selector, text) =>
  Array.from(doc.querySelectorAll(selector)).find(
    (el) => el.textContent.trim() === text
  );
const specValue = (doc, label, part) => {
  const row = Array.from(doc.querySelectorAll(".spec-data-item")).find((el) =>
    el.textContent.includes(label)
  );
  return byText(row, "[data-highlight], span", part);
};

test("specification rows tag CCT, Lens, Mounting and Finish values with their step", () => {
  const doc = render();
  assert.equal(tagOf(specValue(doc, "Light Color (CCT)", "3000K")), "2:30K");
  assert.equal(tagOf(specValue(doc, "Lens Options", "Black")), "3:BK");
  assert.equal(tagOf(specValue(doc, "Mounting Options", "Pivot Clip")), "5:PV");
  assert.equal(tagOf(specValue(doc, "Finish Options", "Black")), "6:BK");
  // Rows without a rule stay untagged.
  const cri = Array.from(doc.querySelectorAll(".spec-data-item")).find((el) =>
    el.textContent.includes("Color Rendering")
  );
  assert.equal(cri.querySelector("[data-highlight]"), null);
});

test("only the Dry/Wet certification icon of each rating is tagged", () => {
  const doc = render();
  const icons = Array.from(doc.querySelectorAll("img.cert-icon")).filter(
    (el) => el.style.display !== "none"
  );
  const tags = Object.fromEntries(
    icons.map((el) => [el.getAttribute("src").split("/").pop(), tagOf(el)])
  );
  assert.deepEqual(tags, {
    "24vdc.svg": "",
    "DryRated.svg": "1:20",
    "DampRated.svg": "1:54",
    "WetRated.svg": "1:67",
  });
});

test("Output Options: the output header, and the cells of the chosen lens rows need both", () => {
  const doc = render();
  const head = Array.from(
    doc.querySelectorAll("#output-options .table-title-wrapper .table-title")
  ).slice(1);
  assert.deepEqual(head.map(tagOf), ["4:50", "4:100", "4:250"]);
  const rows = Array.from(
    doc.querySelectorAll(
      "#output-options .table-data-wrapper .table-item-wrapper"
    )
  );
  const cells = rows.map((row) => Array.from(row.children).slice(1).map(tagOf));
  assert.deepEqual(cells[0], ["4:50+3:WH", "4:100+3:WH", "4:250+3:WH"]);
  assert.deepEqual(cells[1], ["4:50+3:BK", "4:100+3:BK", "4:250+3:BK"]);
  // Other Lenses: Frosted or Clear.
  assert.deepEqual(cells[2], [
    "4:50+3:FR 4:50+3:CL",
    "4:100+3:FR 4:100+3:CL",
    "4:250+3:FR 4:250+3:CL",
  ]);
  // Row labels are not tagged.
  assert.ok(rows.every((row) => tagOf(row.children[0]) === ""));
});

test("Delivered Lumens: output row label, lens header, and the value where they cross", () => {
  const doc = render();
  const head = Array.from(
    doc.querySelectorAll("#delivered-lumens .table-title-wrapper .table-title")
  );
  assert.deepEqual(head.map(tagOf), ["", "3:WH", "3:FR", "3:CL", "3:BK"]);
  const first = doc.querySelector(
    "#delivered-lumens .table-data-wrapper .table-item-wrapper"
  );
  const cells = Array.from(first.children);
  assert.equal(cells[0].textContent.trim(), "50 lm/ft");
  assert.equal(tagOf(cells[0]), "4:50");
  assert.equal(cells[4].textContent.trim(), "64");
  assert.equal(tagOf(cells[4]), "4:50+3:BK");
});

test("table and title tags sit on a span around the text, so the box fits the text", () => {
  const doc = render();
  const tagged = Array.from(
    doc.querySelectorAll(
      "#output-options [data-highlight], #delivered-lumens [data-highlight], #acc-dimensions [data-highlight]"
    )
  );
  assert.ok(tagged.length > 0);
  for (const el of tagged) {
    assert.equal(el.tagName, "SPAN", el.textContent);
    assert.equal(el.style.display, "inline-block", el.textContent);
  }
  const sixtyFour = byText(doc, "#delivered-lumens span", "64");
  assert.equal(sixtyFour.getAttribute("data-highlight"), "4:50+3:BK");
});

test("Accessories Dimensions titles take the Mounting step", () => {
  const doc = render();
  assert.equal(
    tagOf(byText(doc, "#acc-dimensions div > div", "Mounting Clip")),
    "5:MC"
  );
  assert.equal(
    tagOf(byText(doc, "#acc-dimensions div > div", "Pivot Clip")),
    "5:PV"
  );
});

test("other product types get none of the fixture tags", () => {
  const doc = render({ ...PRODUCT, product_type: "LED Neon" });
  assert.equal(
    doc.querySelectorAll(
      "#output-options [data-highlight], #delivered-lumens [data-highlight], img.cert-icon[data-highlight], #acc-dimensions [data-highlight]"
    ).length,
    0
  );
});

test("the product page highlights a tag when any of its alternatives has every part selected", () => {
  const dom = new JSDOM("<html><body></body></html>", {
    runScripts: "outside-only",
  });
  dom.window.eval(PAGE_SCRIPT);
  const match = dom.window.__illHighlightMatch;
  assert.equal(typeof match, "function");
  const picked = new Set(["3:bk", "4:50", "5:mc"]);
  assert.equal(match("4:50+3:BK", picked), true);
  assert.equal(match("4:50+3:WH", picked), false);
  assert.equal(match("4:100+3:FR 4:50+3:BK", picked), true);
  assert.equal(match("5:MC", picked), true);
  assert.equal(match("1:20", picked), false);
  assert.equal(match("", picked), false);
});

// Louvered lenses (owner, 2026-11-25): "White Lens / Linear Louver" and "White Lens / Hex Louver"
// are the White lens with a louver, so the Output Options "(White Lens)" row and the Delivered
// Lumens "White" column (the louvers have no row or column of their own) answer to all three.
test("louvered lenses count as their lens in Output Options and Delivered Lumens", () => {
  const product = structuredClone(PRODUCT);
  product.configurator_options.find((o) => o.option_type === "Lens Appearance").allowed_values_json =
    values([
      ["WH", "White"],
      ["WX", "White Lens / Hex Louver"],
      ["WL", "White Lens / Linear Louver"],
    ]);
  product.configurator_options.find((o) => o.option_type === "Output Level").allowed_values_json =
    JSON.stringify({
      lensMap: Object.fromEntries(
        ["WH", "WX", "WL"].map((lens) => [lens, [{ code: "50", label: "50 lm/ft" }, { code: "200", label: "200 lm/ft" }]])
      ),
    });
  product.specifications.find((s) => s.spec_label === "Lens Options").spec_value =
    "White, White Lens / Hex Louver, White Lens / Linear Louver";
  product.output_options = {
    columns: ["50", "200"],
    rows: [{ label: "Fixture Wattage (White Lens)", values: ["0.8W", "3.6W"] }],
  };
  product.delivered_lumens = {
    lenses: [{ key: "white", label: "White" }],
    rows: [{ output: "200 lm/ft", values: { white: "224" } }],
  };
  const doc = render(product);
  const white = "3:WH 3:WX 3:WL";
  const cells = Array.from(
    doc.querySelectorAll("#output-options .table-data-wrapper .table-item-wrapper")
  ).map((row) => Array.from(row.children).slice(1).map(tagOf));
  assert.deepEqual(cells[0], [
    "4:50+3:WH 4:50+3:WX 4:50+3:WL",
    "4:200+3:WH 4:200+3:WX 4:200+3:WL",
  ]);
  const lensHead = Array.from(
    doc.querySelectorAll("#delivered-lumens .table-title-wrapper .table-title")
  ).slice(1);
  assert.deepEqual(lensHead.map(tagOf), [white]);
  const value = doc.querySelector("#delivered-lumens .table-data-wrapper .table-item-wrapper");
  assert.equal(tagOf(value.children[1]), "4:200+3:WH 4:200+3:WX 4:200+3:WL");
  // The Lens Options row keeps one tag per option.
  assert.equal(tagOf(specValue(doc, "Lens Options", "White Lens / Linear Louver")), "3:WL");
});
