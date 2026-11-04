// Plan 3.9: "Catalog updated — review" badges on schedule lines the catalog has moved past.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const ROWS = `<table><tbody>
  <tr data-line-key="K1"><td class="col-fixture-details"><strong>Fixture A</strong></td>
    <td class="col-actions"><a href="/portal/configure?category=Linear%20Fixture&schedule=S-1&line_key=K1">Edit</a></td></tr>
  <tr data-line-key="K&quot;2"><td class="col-fixture-details"><strong>Fixture B</strong></td></tr>
  <tr data-line-key="K3"><td class="col-fixture-details"><strong>Fixture C</strong></td></tr>
</tbody></table>`;

function page(context) {
  const json = JSON.stringify({ schedule_name: 'S-1', stale_badge: true, lines: [], i18n: {}, ...context }).replace(/</g, '\\u003c');
  const dom = new JSDOM(`<body>${ROWS}<script type="application/json" id="schedule-context">${json}</script></body>`, {
    runScripts: 'outside-only',
    url: 'https://portal.test/portal/schedules/S-1',
  });
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\n' + read('stale'));
  return { dom, w, $: w.$, requests };
}

const settle = () => new Promise(resolve => setTimeout(resolve, 20));

test('the template wires the kill switch, strings and script', () => {
  assert.match(TEMPLATE, /"stale_badge": \(stale_badge_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"recent", "stale"[\],]/);
  assert.match(TEMPLATE, /"Catalog updated — review": _\("Catalog updated — review"\)/);
});

test('flags each stale line with text-only reasons and the row\'s own review link', async () => {
  const { dom, $, requests } = page();
  await settle();
  assert.equal(requests.length, 1);
  const call = requests[0];
  assert.match(call.method, /portal\.catalog_drift\.check$/);
  assert.equal(call.type, 'GET');
  assert.deepEqual({ ...call.args }, { schedule_name: 'S-1' });
  call.callback({ message: { enabled: true, lines: {
    K1: ['FT-1 is no longer offered', 'Power supply <b>X</b> specification changed'],
    'K"2': ['Finish GONE is no longer offered; choose it again'],
    K9: ['A line that is not on the page'],
    K3: [],
  } } });
  const first = $('tr[data-line-key="K1"] .ill-stale-line');
  assert.equal(first.length, 1);
  assert.equal(first.attr('role'), 'status');
  assert.equal(first.find('.badge').text(), 'Catalog updated — review');
  assert.deepEqual(first.find('li').toArray().map(li => li.textContent), ['FT-1 is no longer offered', 'Power supply <b>X</b> specification changed']);
  assert.equal(first.find('b').length, 0, 'reasons are text, not markup');
  assert.equal(first.find('a.ill-stale-review').attr('href'), '/portal/configure?category=Linear%20Fixture&schedule=S-1&line_key=K1');
  const second = $('tr').eq(1).find('.ill-stale-line');
  assert.equal(second.length, 1, 'keys are matched exactly, not as selectors');
  assert.equal(second.find('a').length, 0, 'viewers without an edit link only see the badge');
  assert.equal($('tr[data-line-key="K3"] .ill-stale-line').length, 0, 'a line with no reasons is not flagged');
  assert.equal($('.ill-stale-line').length, 2);
  dom.window.close();
});

test('a repeated check replaces the badges and the line itself is untouched', async () => {
  const { dom, $, w, requests } = page();
  await settle();
  const before = $('tbody').html();
  requests[0].callback({ message: { enabled: true, lines: { K1: ['FT-1 is no longer offered'] } } });
  w.ScheduleStale.apply({ K3: ['Power supply X specification changed'] });
  assert.equal($('tr[data-line-key="K1"] .ill-stale-line').length, 0);
  assert.equal($('tr[data-line-key="K3"] .ill-stale-line').length, 1);
  assert.deepEqual(Object.keys(w.ScheduleStale.lines()), ['K3']);
  w.ScheduleStale.apply({});
  assert.equal($('tbody').html(), before, 'only the badge is added and removed');
  dom.window.close();
});

test('a switched-off page, a disabled reply or a failed check shows nothing', async () => {
  const off = page({ stale_badge: false });
  await settle();
  assert.equal(off.requests.length, 0);
  off.dom.window.close();
  const disabled = page();
  await settle();
  disabled.requests[0].callback({ message: { enabled: false, lines: { K1: ['x'] } } });
  assert.equal(disabled.$('.ill-stale-line').length, 0);
  disabled.dom.window.close();
  const failed = page();
  await settle();
  failed.requests[0].error();
  assert.equal(failed.$('.ill-stale-line').length, 0);
  failed.dom.window.close();
});
