// The drawing request form is built from the request types configured on Desk
// (DESK-7). Needs tests/portal_ui/rendered/drawings.html from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const tick = () => new Promise(resolve => setImmediate(resolve));

function load() {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/drawings.html'), 'utf8');
  const calls = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/drawings',
    beforeParse(w) {
      w.frappe = { msgprint() {}, utils: { escape_html: value => String(value) } };
      w.PortalUploads = {
        uploadAll: async () => ['FILE-1'],
        call: async (method, args) => { calls.push([method.split('.').pop(), args]); return { success: true, request_name: 'DR-1' }; },
      };
      w.location.assign = () => {};
    },
  });
  return { w: dom.window, d: dom.window.document, calls };
}

const visible = (d, show) => !d.querySelector(`[data-show="${show}"]`).hidden;

test('every active type is offered with its Desk label, and the first one shapes the form', () => {
  const { d } = load();
  assert.deepEqual([...d.querySelectorAll('.drawing-type-option span')].map(s => s.textContent), ['Shop <Drawing>', 'Photometric Layout']);
  assert.equal(visible(d, 'show_project_field'), true);
  assert.equal(visible(d, 'show_due_date_field'), false);
  assert.equal(d.querySelectorAll('#requestTypeFields [data-field-key]').length, 0);
});

test('choosing a type shows its flags and custom fields', () => {
  const { d } = load();
  d.querySelectorAll('.drawing-type-option')[1].click();
  assert.equal(d.querySelector('input[name="request_type"]').value, 'Photometric Layout');
  assert.equal(visible(d, 'show_project_field'), false);
  assert.equal(visible(d, 'show_priority_field'), false);
  assert.equal(visible(d, 'show_due_date_field'), true);
  const height = d.querySelector('[data-field-key="ceiling_height"]');
  assert.equal(height.type, 'number');
  assert.equal(height.required, true);
  assert.match(d.querySelector('label[for="rtf-ceiling_height"]').textContent, /Ceiling height \*/);
  assert.deepEqual([...d.querySelectorAll('[data-field-key="target"] option')].map(o => o.value), ['', 'Office', 'Retail']);
  assert.equal(d.querySelector('[data-field-key="dimmed"]').required, false, 'a checkbox can be legitimately unticked');
});

test('the request is saved with its custom field values and then submitted with files', async () => {
  const { w, d, calls } = load();
  d.querySelectorAll('.drawing-type-option')[1].click();
  d.getElementById('requestDescription').value = 'Lobby layout';
  d.querySelector('[data-field-key="ceiling_height"]').value = '12.5';
  d.querySelector('[data-field-key="target"]').value = 'Retail';
  d.querySelector('[data-field-key="dimmed"]').checked = true;
  d.getElementById('requestDueDate').value = '2026-11-01';
  d.getElementById('drawingRequestForm').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await tick(); await tick();
  const [create, submit] = calls;
  assert.equal(create[0], 'create_request');
  assert.deepEqual(JSON.parse(create[1].request_data), {
    request_type: 'Photometric Layout',
    description: 'Lobby layout',
    custom_fields: { ceiling_height: '12.5', target: 'Retail', dimmed: 1 },
    requested_due_date: '2026-11-01',
  });
  assert.deepEqual([submit[0], submit[1].request_name, submit[1].file_ids], ['submit_request', 'DR-1', '["FILE-1"]']);
});

test('hidden fields are not sent for types that do not use them', async () => {
  const { w, d, calls } = load();
  d.getElementById('requestDescription').value = 'Detail';
  d.getElementById('requestProject').value = 'P-1';
  d.getElementById('fixtureReference').value = 'LS-48';
  d.getElementById('drawingRequestForm').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await tick(); await tick();
  assert.deepEqual(JSON.parse(calls[0][1].request_data), {
    request_type: 'Shop Drawing', description: 'Detail', custom_fields: {}, project: 'P-1',
    fixture_or_product_text: 'LS-48', priority: 'Normal',
  });
});
