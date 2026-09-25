const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup() {
    const dom = new JSDOM('<body><button id="opener">Request</button></body>', {runScripts: 'outside-only', url: 'https://portal.test/portal/orders/SO1'});
    const w = dom.window, calls = [];
    w.__ = value => value;
    w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
    w.PortalUploads = {uploadAll: async () => ['FILE1'], call: async (method, args) => { calls.push({method, args}); throw new Error('Connection interrupted'); }};
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_commercial.js'), 'utf8'));
    return {dom, w, calls};
}

test('failed quote intake preserves fields, files and retry identity', async () => {
    const {dom, w, calls} = setup();
    const modal = w.PortalCommercial.quote('S1', 'rev1');
    modal.querySelector('[name="notes"]').value = 'Keep these notes';
    modal.querySelector('form').dispatchEvent(new w.Event('submit', {cancelable: true})); await tick();
    assert.equal(modal.querySelector('[name="notes"]').value, 'Keep these notes');
    assert.match(modal.querySelector('[role="status"]').textContent, /interrupted/);
    modal.querySelector('form').dispatchEvent(new w.Event('submit', {cancelable: true})); await tick();
    assert.equal(calls.length, 2);
    assert.equal(calls[0].args.idempotency_key, calls[1].args.idempotency_key);
    assert.deepEqual([...calls[1].args.file_ids], ['FILE1']);
    assert.equal(calls[1].args.expected_modified, 'rev1');
    dom.window.close();
});

test('withdrawal sends only the current order revision and returns keyboard focus', async () => {
    const {dom, w, calls} = setup();
    const opener = w.document.getElementById('opener'); opener.focus();
    const modal = w.PortalCommercial.withdraw('SO1', 'revision');
    assert.equal(modal.querySelector('input[type="file"]'), null);
    modal.querySelector('textarea').value = 'Please withdraw';
    modal.querySelector('form').dispatchEvent(new w.Event('submit', {cancelable: true})); await tick();
    assert.equal(calls[0].args.revision_hash, 'revision');
    assert.equal(calls[0].args.order_name, 'SO1');
    modal.close(); assert.equal(w.document.activeElement, opener);
    dom.window.close();
});
