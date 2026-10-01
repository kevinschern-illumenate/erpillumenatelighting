const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const jquery = require('jquery');

function setup(url, call) {
    const dom = new JSDOM('<body><div id="productActionSection"></div></body>', {runScripts: 'outside-only', url});
    const w = dom.window, calls = [], messages = [], navigations = [];
    w.$ = jquery(w); w.__ = (text, args) => (args || []).reduce((out, value, i) => out.replace('{' + i + '}', value), text);
    w.frappe = {msgprint: message => messages.push(message), call: async options => { calls.push(options); return call(options); }};
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/product_detail.js'), 'utf8'));
    w.navigateTo = href => navigations.push(href);
    return {dom, w, calls, messages, navigations};
}

const schedules = {message: {choices: [], schedules: [{name: 'S1', schedule_name: 'Office', modified: 'revision-1'}]}};

function fill(w, values) {
    Object.entries(values).forEach(([id, value]) => w.$('#' + id).val(value));
}

test('accessory products add an accessory line with fixture type and location, retrying with one key', async () => {
    const {dom, w, calls, messages, navigations} = setup('https://portal.test/portal/products/clip?schedule=S1', options => {
        if (options.method.endsWith('.prepare')) return schedules;
        throw new Error('offline');
    });
    await w.renderProductAction({product_slug: 'clip', capability: 'quantity', family: 'Accessory',
        standard_choices: [{item_code: 'CLIP', label: 'Clip', stock_uom: 'Nos'}]});
    assert.equal(w.$('#scheduleSelect').val(), 'S1');
    assert.equal(w.$('#configureOnlyLink').length, 0);
    fill(w, {lineFixtureType: ' A1 ', lineLocation: 'Lobby', lineQty: '2', lineNotes: 'Keep label'});
    await w.submitProductAction({product_slug: 'clip'}, 'standard');
    await w.submitProductAction({product_slug: 'clip'}, 'standard');
    const submits = calls.filter(row => row.method.endsWith('.add'));
    assert.equal(submits.length, 2);
    assert.equal(submits[0].args.idempotency_key, submits[1].args.idempotency_key);
    assert.deepEqual(
        {item: submits[1].args.item_code, line: submits[1].args.line_id, location: submits[1].args.location, qty: submits[1].args.quantity, modified: submits[1].args.expected_modified, notes: submits[1].args.notes},
        {item: 'CLIP', line: 'A1', location: 'Lobby', qty: 2, modified: 'revision-1', notes: 'Keep label'});
    assert.equal(w.$('#lineFixtureType').val(), ' A1 ');
    assert.equal(w.$('#productActionSubmit').prop('disabled'), false);
    assert.equal(navigations.length, 0);
    assert.match(messages.at(-1), /retained/);
    dom.window.close();
});

test('configurable products hand the fixture type and location to their family configurator', async () => {
    const {dom, w, calls, messages, navigations} = setup('https://portal.test/portal/products/tape', () => schedules);
    const product = {product_slug: 'tape', capability: 'configure', family: 'LED Tape',
        configure_url: '/portal/configure?category=LED+Tape&template=T1&product_slug=tape'};
    await w.renderProductAction(product);
    assert.match(w.$('#productActionSection').text(), /LED tape configurator/);
    assert.equal(w.$('#configureOnlyLink').attr('href'), '/portal/configure?category=LED+Tape&template=T1&product_slug=tape');
    fill(w, {lineLocation: 'Cove'});
    w.submitProductAction(product, 'configure');
    assert.match(messages.at(-1), /schedule/);
    fill(w, {scheduleSelect: 'S1', lineFixtureType: 'T2', lineQty: '3'});
    w.submitProductAction(product, 'configure');
    const target = new URL(navigations.at(-1), 'https://portal.test');
    assert.equal(target.pathname, '/portal/configure');
    assert.equal(target.searchParams.get('category'), 'LED Tape');
    assert.equal(target.searchParams.get('schedule'), 'S1');
    const draft = JSON.parse(w.sessionStorage.getItem('ill-line-draft:' + target.searchParams.get('draft')));
    assert.equal(draft.schedule, 'S1');
    assert.deepEqual(draft.metadata, {line_id: 'T2', location: 'Cove', qty: 3, notes: ''});
    assert.equal(calls.filter(row => row.method.endsWith('.add')).length, 0);
    dom.window.close();
});

test('an existing schedule line reopens the configurator and unmapped products ask for assistance', async () => {
    const product = {product_slug: 'linear', capability: 'configure', family: 'Linear Fixture',
        configure_url: '/portal/configure?category=Linear+Fixture&template=F1&product_slug=linear'};
    let {dom, w, calls} = setup('https://portal.test/portal/products/linear?schedule=S1&line_idx=2', () => schedules);
    w.renderProductAction(product);
    const target = new URL(w.$('#productActionSubmit').attr('href'), 'https://portal.test');
    assert.equal(target.searchParams.get('line_idx'), '2');
    assert.equal(target.searchParams.get('schedule'), 'S1');
    assert.equal(w.$('#lineFixtureType').length, 0);
    assert.equal(calls.length, 0);
    dom.window.close();
    ({dom, w} = setup('https://portal.test/portal/products/kit', () => schedules));
    w.renderProductAction({product_slug: 'kit', capability: 'inquiry', family: 'Extrusion Kit'});
    assert.equal(w.$('#productActionSection a').attr('href'), '/portal/support');
    dom.window.close();
});

test('a catalog "#configure" link focuses the action panel once it renders', async () => {
    const {dom, w} = setup('https://portal.test/portal/products/clip#configure', () => schedules);
    let scrolled = false;
    w.HTMLElement.prototype.scrollIntoView = function () { scrolled = this.id === 'productActionSection'; };
    await w.renderProductAction({product_slug: 'clip', capability: 'quantity', family: 'Accessory',
        standard_choices: [{item_code: 'CLIP', label: 'Clip', stock_uom: 'Nos'}]});
    w.focusActionIfRequested();
    assert.equal(scrolled, true);
    assert.equal(w.document.activeElement.id, 'scheduleSearch');
    dom.window.close();
});

test('pilot-only products explain the account limit to dealers', async () => {
    const {dom, w} = setup('https://portal.test/portal/products/tape', () => schedules);
    await w.renderProductAction({product_slug: 'tape', capability: 'inquiry', capability_reason: 'pilot_only', family: 'LED Tape'});
    assert.match(w.$('#productActionSection').text(), /not yet available for your account/);
    assert.doesNotMatch(w.$('#productActionSection').text(), /capability reason/i);
    dom.window.close();
});
