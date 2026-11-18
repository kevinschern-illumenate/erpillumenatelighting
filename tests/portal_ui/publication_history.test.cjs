// Publication History section on the Webflow Product and the templates (plan 4.14, Phase 6).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const code = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/publication_history.js'), 'utf8');
const HOSTILE = '<img src=x onerror=alert(1)>';
const flush = async () => { for (let i = 0; i < 5; i += 1) await new Promise(resolve => setImmediate(resolve)); };

function setup(t, history, doctype = 'ilL-Webflow-Product', doc = { name: 'kit-ra02' }) {
  const dom = new JSDOM('<html><body><div class="layout"></div></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, calls = [];
  const frappe = {
    utils: { escape_html: value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]) },
    ui: { form: { on: (name, events) => { handlers[name] = events; } } },
    xcall: (method, args) => { calls.push([method, args]); return Promise.resolve(history); },
  };
  const context = { window: {}, frappe, $, __: (text, args) => String(text).replace(/\{(\d+)\}/g, (_, i) => args[i]) };
  context.window = context;
  vm.runInNewContext(code, context);
  const frm = { doctype, doc, is_new: () => false, layout: { wrapper: dom.window.document.querySelector('.layout') } };
  return { dom, handlers, calls, frm };
}

test('the product shows its brands and latest pushes, escaped', async t => {
  const history = {
    product: 'kit-ra02', limit: 25,
    brands: [{ brand: 'illumenate', published_on: '2026-11-06 10:00:00', staged_on: '2026-11-08 09:00:00', on_webflow: true }],
    rows: [
      { kind: 'push', when: '2026-11-08 09:00:00', status: 'Active + Live · Published', result: 'Done', ok: true, by: 'owner@example.com', completed_on: '2026-11-08 09:00:05' },
      { kind: 'status', when: '2026-11-08 08:59:00', status: 'Webflow Status: Webflow Draft → Published', result: 'Status changed', ok: null, by: 'owner@example.com' },
      { kind: 'push', when: '2026-11-07 09:00:00', status: '', result: 'Failed', ok: false, by: 'a', error: HOSTILE },
    ],
  };
  const { dom, handlers, calls, frm } = setup(t, history);
  handlers['ilL-Webflow-Product'].refresh(frm);
  await flush();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])), { product: 'kit-ra02' });
  const section = dom.window.document.querySelector('.ill-publication-history');
  assert.match(section.textContent, /published since 2026-11-06 10:00/);
  assert.equal(section.querySelectorAll('tbody tr').length, 3);
  assert.equal(section.querySelectorAll('tbody tr.ill-status-change').length, 1);
  assert.match(section.textContent, /Webflow Draft → Published/);
  assert.equal([...section.querySelectorAll('thead th')].map(th => th.textContent).join('|'), 'When|Status|Result|By|Finished|Error');
  assert.ok(section.classList.contains('form-section'));
  assert.equal(section.querySelector('img'), null);
  assert.match(section.textContent, /<img src=x/);
});

test('a template asks through its linked product; without one nothing shows', async t => {
  const { dom, handlers, calls, frm } = setup(t, { product: 'kit-ra02', brands: [], rows: [], limit: 25 },
    'ilL-Extrusion-Kit-Template', { name: 'KIT-RA02', webflow_product: 'kit-ra02' });
  handlers['ilL-Extrusion-Kit-Template'].refresh(frm);
  await flush();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])), { template_doctype: 'ilL-Extrusion-Kit-Template', template_name: 'KIT-RA02' });
  assert.match(dom.window.document.body.textContent, /Never synced to Webflow/);
  frm.doc = { name: 'KIT-X' };
  handlers['ilL-Extrusion-Kit-Template'].refresh(frm);
  await flush();
  assert.equal(dom.window.document.querySelector('.ill-publication-history'), null);
});
