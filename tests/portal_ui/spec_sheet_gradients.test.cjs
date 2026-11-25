// Gradient lines on the spec sheet (owner, 2026-11-25). The page has a header and a footer line
// per LED family (#sw-, #tw-, #fs-, #dw-gradient-line and #swfooter-...). Its CSS shows only the
// sw line by default (.gradient-line.tw, .fs, ... are display:none), so the template's own line
// must be shown with display:block, not by clearing the inline style: ILL-RA01-TW and -FS
// printed with no line at all.
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
const KEYS = ["fs", "sw", "tw", "dw"];
const CSS = `.gradient-line{display:block}
${KEYS.map(
  (k) =>
    `.gradient-line.${k},.gradient-line.${k}-footer{display:${
      k === "sw" ? "block" : "none"
    }}`
).join("\n")}`;
const TEMPLATE = `<html><head><style>${CSS}</style></head><body>
${KEYS.map(
  (k) => `<div id="${k}-gradient-line" class="gradient-line ${k}"></div>`
).join("")}
${KEYS.map(
  (k) =>
    `<div id="${k}footer-gradient-line" class="gradient-line ${k}-footer"></div>`
).join("")}
</body></html>`;

function shown(packages) {
  const inputs = {
    "(ilL) Fetch Webflow Template": { data: TEMPLATE },
    "Get Product Info": {
      message: {
        products: [
          {
            product_name: "Rainier",
            product_slug: "ill-ra01",
            product_type: "Fixture Template",
            led_packages: packages,
          },
        ],
      },
    },
  };
  const $ = (name) => ({ first: () => ({ json: inputs[name] }) });
  const html = vm.runInNewContext(`(function() {${FORMAT}\n})()`, { $ }).json
    .injected_html;
  const { window } = new JSDOM(html, { runScripts: "dangerously" });
  return [...window.document.querySelectorAll(".gradient-line")]
    .filter((el) => window.getComputedStyle(el).display !== "none")
    .map((el) => el.id);
}

test("Tunable White shows the tw lines, though the page hides them by default", () => {
  assert.deepEqual(shown(["ilLumenate Tunable White"]), [
    "tw-gradient-line",
    "twfooter-gradient-line",
  ]);
});

test("RGB+TW shows the fs lines", () => {
  assert.deepEqual(shown(["ilLumenate RGB+TW"]), [
    "fs-gradient-line",
    "fsfooter-gradient-line",
  ]);
});

test("Static White shows the sw lines only", () => {
  assert.deepEqual(shown(["ilLumenate Static White"]), [
    "sw-gradient-line",
    "swfooter-gradient-line",
  ]);
});
