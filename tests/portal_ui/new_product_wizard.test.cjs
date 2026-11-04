const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/illumenate_lighting/page/new_product_wizard/new_product_wizard.js'), 'utf8');
const HOSTILE = '<img src=x onerror="window.pwned=1">';
const tick = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };

function setup(handlers = {}) {
  const dom = new JSDOM('<!doctype html><body><div id="main"></div></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  const calls = [], routes = [];
  w.__ = (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, i) => String((args || [])[i]));
  w.frappe = {
    pages: { 'new-product-wizard': {} },
    router: { slug: name => name.toLowerCase().replace(/ /g, '-') },
    async call(options) {
      calls.push(JSON.parse(JSON.stringify(options)));
      const key = Object.keys(handlers).find(name => options.method.endsWith(name));
      if (!key) return { message: undefined };
      return { message: await handlers[key](options.args) };
    },
    set_route(...args) { routes.push(args); },
  };
  w.eval(script);
  const root = w.document.getElementById('main');
  const wizard = w.NewProductWizard.mount(root);
  const buttons = () => [...root.querySelectorAll('button')];
  const next = async () => { buttons().find(b => ['Next', 'Create draft', 'Open product'].includes(b.textContent)).click(); await tick(); };
  const status = () => root.querySelector('[role="status"]').textContent;
  return { w, root, wizard, calls, routes, next, status, buttons };
}

function fill(control, value) {
  control.value = value;
  control.dispatchEvent(new control.ownerDocument.defaultView.Event('input'));
}

test('slugify matches product slug rules', () => {
  const { w } = setup();
  assert.equal(w.NewProductWizard.slugify('  Slim 12 — Wet/Dry  '), 'slim-12-wet-dry');
  assert.equal(w.NewProductWizard.slugify(''), '');
});

test('blank flow refuses a claimed template, then creates an inactive draft', async () => {
  let claimed = 'other-product';
  const { root, calls, next, status, wizard } = setup({
    'frappe.client.get_list': () => [],
    'frappe.client.get_value': () => ({ webflow_product: claimed }),
    'frappe.client.insert': args => ({ name: args.doc.product_slug }),
    'product_readiness.preview': () => ({ ready: false, issues: [{ record: 'slim-12', field: 'hero_image', message: HOSTILE }], warnings: [] }),
  });
  await next();
  assert.equal(status(), 'Choose a family.');
  root.querySelector('select').value = 'Fixture Template';
  await next();
  await next(); // blank start
  const [name, slug, description] = root.querySelectorAll('input');
  fill(name, 'Slim 12');
  assert.equal(slug.value, 'slim-12');
  fill(description, HOSTILE);
  await next();
  fill(root.querySelector('input'), 'SLIM-12');
  await next();
  assert.ok(status().includes('already belongs to other-product'));
  assert.equal(calls.filter(c => c.method === 'frappe.client.insert').length, 0);
  claimed = null;
  await next();
  const insert = calls.find(c => c.method === 'frappe.client.insert');
  assert.deepEqual(insert.args.doc, {
    doctype: 'ilL-Webflow-Product', product_name: 'Slim 12', product_slug: 'slim-12', product_type: 'Fixture Template',
    short_description: HOSTILE, sublabel: '', is_active: 0, fixture_template: 'SLIM-12',
  });
  assert.equal(wizard.state.product, 'slim-12');
  assert.equal(wizard.state.step, 4);
  assert.equal([...root.querySelectorAll('button')].find(b => b.textContent === 'Back').disabled, true);
  await next(); // media
  await next(); // documents -> readiness
  assert.ok(root.textContent.includes(HOSTILE));
  assert.equal(root.querySelectorAll('img').length, 0);
});

test('clone flow duplicates through product_clone with a new template code', async () => {
  const { root, calls, next, wizard } = setup({
    'frappe.client.get_list': () => [{ name: 'slim-12', product_name: 'Slim 12' }],
    'product_clone.duplicate': () => ({ doctype: 'ilL-Webflow-Product', name: 'slim-24', template: { name: 'SLIM-24' } }),
  });
  root.querySelector('select').value = 'Fixture Template';
  await next();
  root.querySelector('select').value = 'clone';
  await next();
  assert.ok(root.textContent.includes('Choose the product to copy.'));
  root.querySelector('input[type="text"]').value = 'slim-12';
  root.querySelector('input[type="checkbox"]').checked = false;
  await next();
  const [name] = root.querySelectorAll('input');
  fill(name, 'Slim 24');
  await next();
  root.querySelector('input').value = 'SLIM-24';
  await next();
  const call = calls.find(c => c.method.endsWith('product_clone.duplicate'));
  assert.deepEqual(call.args, {
    doctype: 'ilL-Webflow-Product', name: 'slim-12', new_name: 'Slim 24', new_slug: 'slim-24', include_media: 0, template_code: 'SLIM-24',
  });
  assert.equal(call.type, 'POST');
  assert.equal(wizard.state.product, 'slim-24');
  assert.equal(wizard.state.template, 'SLIM-24');
});

test('finish inspects publication and only offers staging when ready', async () => {
  const { root, calls, routes, next, wizard, buttons, status } = setup({
    'publication.inspect': () => ({ brand: 'ill', state: 'NEEDS_REVIEW', current_hash: 'abc123', readiness: { ready: true, issues: [], warnings: [] } }),
    'publication.request': () => ({ job: 'PUB-0001' }),
  });
  Object.assign(wizard.state, { family: 'Component', product: 'widget', step: 7 });
  wizard.show();
  const stage = buttons().find(b => b.textContent === 'Request staging');
  assert.equal(stage.hidden, true);
  root.querySelector('input').value = 'ill';
  buttons().find(b => b.textContent === 'Inspect publication').click();
  await tick();
  assert.equal(stage.hidden, false);
  stage.click();
  await tick();
  assert.deepEqual(calls.find(c => c.method.endsWith('publication.request')).args, { product: 'widget', brand: 'ill', operation: 'STAGE', expected_hash: 'abc123' });
  assert.equal(status(), 'Staging requested: PUB-0001');
  await next();
  assert.deepEqual(JSON.parse(JSON.stringify(routes)), [['Form', 'ilL-Webflow-Product', 'widget']]);
});
