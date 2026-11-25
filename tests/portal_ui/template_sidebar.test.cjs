// Template form sidebar (illumenate_lighting/public/js/template_sidebar.js): brand pill, record
// name, Template Name, then "Go to ilL-Webflow-Product" when a Webflow Product is linked
// (owner, 2026-11-25).
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const jquery = require("jquery");
const { JSDOM } = require("jsdom");

const SCRIPT = fs.readFileSync(
  path.join(
    __dirname,
    "../../illumenate_lighting/public/js/template_sidebar.js"
  ),
  "utf8"
);

function render(t, doc) {
  const dom = new JSDOM(
    '<div class="page"><div class="layout-side-section"></div></div>'
  );
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const events = {};
  const context = {
    $,
    __: (s) => s,
    frappe: {
      ui: {
        form: {
          on(doctype, handlers) {
            events[doctype] = handlers;
          },
        },
      },
    },
  };
  vm.runInNewContext(SCRIPT, context);
  const frm = {
    doctype: "ilL-Fixture-Template",
    doc: {
      name: "ILL-RA01-SW",
      template_name: "Rainier [SF] Static White",
      target_brands: [],
      ...doc,
    },
    page: { wrapper: dom.window.document.querySelector(".page") },
    is_new: () => false,
    add_custom_button() {},
  };
  events["ilL-Fixture-Template"].refresh(frm);
  return { $, frm, events, header: () => $(".ill-template-header") };
}

test("links the linked Webflow Product under the Template Name", (t) => {
  const { header } = render(t, { webflow_product: "ill-ra01-sw" });
  const rows = header()
    .children()
    .map((_, el) => el.textContent)
    .get();
  assert.deepEqual(rows, [
    "ILL-RA01-SW",
    "Rainier [SF] Static White",
    "Go to ilL-Webflow-Product",
  ]);
  assert.equal(
    header().find("a").attr("href"),
    "/app/ill-webflow-product/ill-ra01-sw"
  );
});

test("no link without a linked Webflow Product", (t) => {
  const { header } = render(t, { webflow_product: "" });
  assert.equal(header().find("a").length, 0);
});

test("the link follows the field when it changes", (t) => {
  const { header, frm, events } = render(t, { webflow_product: "" });
  frm.doc.webflow_product = "ill-ra01-fs";
  events["ilL-Fixture-Template"].webflow_product(frm);
  assert.equal(header().length, 1);
  assert.equal(
    header().find("a").attr("href"),
    "/app/ill-webflow-product/ill-ra01-fs"
  );
});
