// Plan 6.7: comparing two schedule lines renders server text without interpreting it as HTML.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const { read, TEMPLATE } = require('./schedule_source.cjs');

function page(reply) {
  const context = JSON.stringify({ schedule_name: 'S-1', i18n: { Differs: 'Différent' } });
  const dom = new JSDOM(`<body><script type="application/json" id="schedule-context">${context}</script>
    <form id="compareLinesForm"><select id="compareLineA"><option value="k-1" selected>A1</option><option value="k-2">A2</option></select>
    <select id="compareLineB"><option value="k-1">A1</option><option value="k-2" selected>A2</option></select>
    <button type="submit">Compare</button></form><div id="compareResult"></div></body>`, { runScripts: 'outside-only' });
  const w = dom.window;
  const calls = [];
  w.PortalAPI = { call: (method, args, options) => { calls.push({ method, args, options }); return reply(); } };
  w.PortalUI = { failed: (container, message) => { container.textContent = 'failed: ' + message; } };
  w.eval(read('context'));
  w.eval(read('compare'));
  return { dom, w, calls, result: w.document.getElementById('compareResult') };
}

const submit = w => w.document.getElementById('compareLinesForm').dispatchEvent(new w.Event('submit', { cancelable: true }));
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

test('the schedule page offers the compare form only behind its flag and with two lines', () => {
  assert.match(TEMPLATE, /\{% if compare_enabled and \(lines_json or \[\]\) \| length >= 2 %\}/);
  assert.match(TEMPLATE, /<label for="compareLineA"/);
  assert.match(TEMPLATE, /<option value="\{\{ line\.line_key \| e \}\}"/);
});

test('compare sends both line keys and renders rows as text with differences marked', async () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const { dom, w, calls, result } = page(() => Promise.resolve({
    success: true, enabled: true, priced: false,
    lines: [
      { schedule: 'S-1', designation: 'A1', location: hostile },
      { schedule: 'S-2', schedule_name: 'Other <b>', designation: 'A2', location: '' },
    ],
    rows: [
      { key: 'part_number', label: 'Part number', a: hostile, b: 'ILL-2', same: false },
      { key: 'run_plan', label: 'Run plan', a: ['Run 1', 'Run 2'], b: ['Run 1'], same: false },
      { key: 'quantity', label: 'Quantity', a: '2', b: '2', same: true },
    ],
  }));
  submit(w);
  await settle();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'illumenate_lighting.illumenate_lighting.portal.compare.compare_lines');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0].args)), { schedule: 'S-1', line_a: 'k-1', line_b: 'k-2' });
  assert.equal(calls[0].options.type, 'GET');
  assert.equal(result.querySelector('img'), null);
  assert.equal(result.querySelector('b'), null);
  const rows = result.querySelectorAll('tbody tr');
  assert.equal(rows.length, 3);
  assert.equal(rows[0].cells[1].textContent, hostile);
  assert.equal(rows[1].cells[1].querySelectorAll('br').length, 1);
  assert.equal(result.querySelectorAll('tr.ill-compare-differs').length, 2);
  assert.match(rows[0].textContent, /Différent/);
  assert.match(result.querySelector('thead').textContent, /Other <b>/);
  assert.equal(result.getAttribute('aria-busy'), 'false');
  dom.window.close();
});

test('the same line twice is refused locally and a switched-off site says so', async () => {
  const { dom, w, calls, result } = page(() => Promise.resolve({ success: true, enabled: false }));
  w.document.getElementById('compareLineB').value = 'k-1';
  submit(w);
  assert.equal(calls.length, 0);
  assert.match(result.textContent, /two different lines/);
  w.document.getElementById('compareLineB').value = 'k-2';
  submit(w);
  await settle();
  assert.match(result.textContent, /turned off/);
  dom.window.close();
});

test('a refused comparison shows the server message', async () => {
  const { dom, w, result } = page(() => Promise.reject(new Error('Schedule is unavailable')));
  submit(w);
  await settle();
  assert.equal(result.textContent, 'failed: Schedule is unavailable');
  dom.window.close();
});
