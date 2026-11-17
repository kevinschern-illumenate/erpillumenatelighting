const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/illumenate_lighting/page/product_readiness/product_readiness.js'), 'utf8');
const HOSTILE = '<img src=x onerror="window.pwned=1">';
const tick = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); };

const cell = (status, extra = {}) => ({ status, message: '', field: null, doctype: 'ilL-Webflow-Product', name: null, ...extra });
const ROW = {
  product: 'slim-12', product_name: HOSTILE, product_type: 'Fixture Template', is_active: true, ready: false,
  cells: {
    identity: cell('ok'), source: cell('ok'), specs: cell('warn', { message: 'No specification rows', field: 'specifications', name: 'slim-12' }),
    images: cell('fail', { message: HOSTILE, field: 'hero_image', doctype: 'ilL-Fixture-Template', name: 'SLIM-12' }),
    alt_text: cell('ok'), docs: cell('ok'), spec_sheet: cell('na'), publication: cell('ok'), webflow_sync: cell('ok'),
  },
};

function setup(pages) {
  const dom = new JSDOM('<!doctype html><body><div id="main"></div></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  const calls = [], routes = [], messages = [], values = { family: '', brand: '', only_incomplete: 0 }, fields = {};
  w.__ = (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, i) => String((args || [])[i]));
  w.frappe = {
    pages: { 'product-readiness': {} },
    async call(options) {
      calls.push(JSON.parse(JSON.stringify(options)));
      if (options.method.endsWith('.preview')) return { message: { ready: false, issues: [{ record: 'slim-12', field: 'x', message: HOSTILE }], warnings: [] } };
      return { message: pages.shift() };
    },
    async set_route(...args) { routes.push(args); },
    msgprint(message) { messages.push(message); },
  };
  const page = {
    add_field(df) { fields[df.fieldname] = df; return { get_value: () => values[df.fieldname] }; },
    set_primary_action(_label, fn) { page.refresh = fn; },
  };
  w.eval(script);
  const root = w.document.getElementById('main');
  const board = w.ProductReadinessBoard.mount(page, root);
  return { w, root, calls, routes, messages, values, fields, board };
}

test('rows render as text with traffic lights and paginate with the cursor', async () => {
  const { w, root, calls, values, fields } = setup([
    { rows: [ROW], next_cursor: 'slim-12' },
    { rows: [{ ...ROW, product: 'slim-24', product_name: 'Slim 24', ready: true }], next_cursor: null },
    { rows: [], next_cursor: null },
  ]);
  await tick();
  assert.deepEqual(calls[0].args, { family: '', brand: '', only_incomplete: 0, after: '' });
  assert.equal(calls[0].type, 'GET');
  assert.equal(root.querySelectorAll('img').length, 0);
  assert.equal(w.pwned, undefined);
  assert.ok(root.textContent.includes(HOSTILE));
  const headers = [...root.querySelectorAll('th')].map(th => th.textContent);
  assert.deepEqual(headers.slice(1, 10), ['Identity', 'Source', 'Specs', 'Images', 'Alt text', 'Docs', 'Spec sheet', 'Publication', 'Webflow sync']);
  assert.deepEqual([...root.querySelectorAll('tbody tr:first-child .indicator-pill')].map(pill => pill.className.split(' ').pop()),
    ['green', 'green', 'orange', 'red', 'green', 'green', 'gray', 'green', 'green']);
  const more = [...root.querySelectorAll('button')].find(button => button.textContent === 'Load more');
  assert.equal(more.hidden, false);
  more.click();
  await tick();
  assert.equal(calls[1].args.after, 'slim-12');
  assert.equal(root.querySelectorAll('tbody tr').length, 2);
  assert.equal(more.hidden, true);
  assert.match(root.querySelector('[role="status"]').textContent, /2 products shown, 1 ready/);
  values.family = 'LED Tape';
  values.only_incomplete = 1;
  fields.family.change();
  await tick();
  assert.deepEqual(calls[2].args, { family: 'LED Tape', brand: '', only_incomplete: 1, after: '' });
  assert.match(root.querySelector('[role="status"]').textContent, /Nothing to show/);
});

test('a failing cell opens the record that needs the fix and preflight output is escaped', async () => {
  const { root, routes, messages, calls } = setup([{ rows: [ROW], next_cursor: null }]);
  await tick();
  const images = root.querySelectorAll('tbody tr:first-child td')[4].querySelector('a');
  images.click();
  await tick();
  assert.deepEqual(routes, [['Form', 'ilL-Fixture-Template', 'SLIM-12']]);
  assert.equal(root.querySelectorAll('tbody tr:first-child td')[1].querySelector('a'), null);
  [...root.querySelectorAll('button')].find(button => button.textContent === 'Preflight').click();
  await tick();
  assert.deepEqual(calls[1].args, { product: 'slim-12', channel: 'cms' });
  assert.ok(!messages[0].message.includes('<img'));
  assert.ok(messages[0].message.includes('&lt;img'));
});

test('a server error leaves an explanation instead of a stale table', async () => {
  const { root } = setup([]);
  await tick();
  assert.match(root.querySelector('[role="status"]').textContent, /Nothing to show|unavailable/);
});
