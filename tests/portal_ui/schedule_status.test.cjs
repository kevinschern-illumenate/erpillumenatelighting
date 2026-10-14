// Leaving QUOTED with an open offer warns before the quote is superseded (REL-4).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/templates/pages/schedule.html'), 'utf8');

function load(status, openOffer) {
  const start = SOURCE.indexOf('var statusLabels = ');
  const end = SOURCE.indexOf('function requestQuote()');
  assert.ok(start > 0 && end > start, 'status script block not found');
  const script = SOURCE.slice(start, end)
    .replace('{{ status_labels | tojson }}', JSON.stringify({ DRAFT: 'Draft', READY: 'Ready', QUOTED: 'Quoted' }))
    .replace('{{ open_offer | tojson }}', JSON.stringify(openOffer))
    .replace('{{ schedule.status | tojson }}', JSON.stringify(status));
  assert.doesNotMatch(script, /\{\{/);
  const confirms = [];
  const context = {
    schedule_name: 'S-1',
    document: { addEventListener() {} },
    __: (text, args) => (args ? text.replace(/\{(\d+)\}/g, (_, i) => args[i]) : text),
    frappe: {
      confirm: message => confirms.push(message),
      call() {},
      utils: { escape_html: value => String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;') },
    },
  };
  vm.runInNewContext(script, context);
  return { context, confirms };
}

test('leaving QUOTED with an open offer names the quote that will be superseded', () => {
  const { context, confirms } = load('QUOTED', { name: 'OFFER-<1>', valid_until: '10-30-2026' });
  context.changeStatus('DRAFT');
  assert.equal(confirms[0], 'Quote OFFER-&lt;1&gt; (valid until 10-30-2026) will no longer be acceptable. Continue?');
});

test('ordinary status changes keep the plain confirmation with friendly labels', () => {
  const { context, confirms } = load('DRAFT', null);
  context.changeStatus('READY');
  assert.equal(confirms[0], 'Change schedule status to Ready?');
  const quoted = load('QUOTED', null);
  quoted.context.changeStatus('READY');
  assert.equal(quoted.confirms[0], 'Change schedule status to Ready?');
});
