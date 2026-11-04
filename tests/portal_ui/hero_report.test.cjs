const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const FILE = path.join(__dirname, '../../illumenate_lighting/illumenate_lighting/report/templates_without_hero_image/templates_without_hero_image.js');

function load() {
  const calls = [];
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const frappe = {
    query_reports: {},
    utils: { escape_html: escape },
    confirm: (_message, yes) => yes(),
    call: (args) => { calls.push(args); return Promise.resolve({ message: {} }); },
    show_alert() {},
  };
  const context = { frappe, __: (text, args) => (args ? text.replace('{0}', args[0]) : text) };
  vm.runInNewContext(fs.readFileSync(FILE, 'utf8'), context, { filename: FILE });
  return { report: frappe.query_reports['Templates Without Hero Image'], calls };
}

const fallback = (value) => 'default:' + value;
const row = { template_type: 'ilL-Fixture-Template', template: 'F"<1>', suggested_image: '/files/a".jpg', suggestion_public: 1, can_use: 1 };

test('hero report escapes every value it puts in markup (5.4)', () => {
  const { report } = load();
  const button = report.formatter('', 0, { fieldname: 'action' }, row, fallback);
  assert.match(button, /class="btn btn-xs btn-default ill-use-hero"/);
  assert.ok(!button.includes('F"<1>') && button.includes('F&quot;&lt;1&gt;'));
  assert.ok(button.includes('data-image="/files/a&quot;.jpg"'));
  const image = report.formatter('', 0, { fieldname: 'suggested_image' }, row, fallback);
  assert.ok(image.includes('src="/files/a&quot;.jpg"'));
  assert.equal(report.formatter('x', 0, { fieldname: 'template_name' }, row, fallback), 'default:x');
});

test('hero report offers the action only for public images and editors', () => {
  const { report } = load();
  assert.equal(report.formatter('', 0, { fieldname: 'action' }, { ...row, can_use: 0 }, fallback), '');
  assert.equal(report.formatter('', 0, { fieldname: 'action' }, { ...row, suggestion_public: 0, can_use: 0 }, fallback), 'Image is not public');
  assert.equal(report.formatter('', 0, { fieldname: 'action' }, { ...row, suggested_image: null }, fallback), 'default:');
});

test('Use as hero image posts the row to the guarded server method and refreshes', async () => {
  const { report, calls } = load();
  let handler;
  let refreshed = 0;
  report.onload({ page: { wrapper: { on: (_event, selector, fn) => { assert.equal(selector, '.ill-use-hero'); handler = fn; } } }, refresh: () => { refreshed += 1; } });
  const attrs = { 'data-template-type': row.template_type, 'data-template': row.template, 'data-image': row.suggested_image };
  const button = { disabled: false, getAttribute: (name) => attrs[name] };
  handler.call(button);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.length, 1);
  assert.match(calls[0].method, /templates_without_hero_image\.use_as_hero_image$/);
  assert.equal(calls[0].type, 'POST');
  assert.deepEqual({ ...calls[0].args }, { template_type: row.template_type, template: row.template, image: row.suggested_image });
  assert.equal(button.disabled, true);
  assert.equal(refreshed, 1);
});
