const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const jquery = require('jquery');

test('standard SKU dialog preserves fields and retry identity after failure', async () => {
    const dom = new JSDOM('<body><div id="configuratorSection"></div></body>', {runScripts:'outside-only', url:'https://portal.test/portal/products/clip?schedule=S1'});
    const w = dom.window, calls = [], messages = [];
    w.$ = jquery(w); w.__ = x => x;
    let dialog;
    w.frappe = {ready: () => {}, msgprint: message => messages.push(message), call: async options => {
        calls.push(options);
        if (options.method.endsWith('.prepare')) return {message: {choices:[{item_code:'CLIP', label:'Clip', stock_uom:'Nos'}], schedules:[{name:'S1', schedule_name:'Office', modified:'revision-1'}]}};
        throw new Error('offline');
    }, ui: {Dialog: class {
        constructor(options) {this.options=options; this.values={}; dialog=this; this.button=w.$('<button>'); this.$wrapper=w.$('<div>');}
        show() {} hide() {this.hidden=true;} set_value(key,value) {this.values[key]=value;} get_primary_btn() {return this.button;}
    }}};
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/product_detail.js'), 'utf8'));
    await w.openStandardProduct({product_slug:'clip'});
    assert.equal(dialog.values.schedule_name, 'S1');
    const values={item_code:'CLIP', schedule_name:'S1', quantity:2, line_id:'L1', location:'Office', notes:'Keep label'};
    await dialog.options.primary_action(values);
    await dialog.options.primary_action(values);
    const submits=calls.filter(row=>row.method.endsWith('.add'));
    assert.equal(submits[0].args.idempotency_key, submits[1].args.idempotency_key);
    assert.equal(submits[1].args.expected_modified, 'revision-1');
    assert.equal(submits[1].args.notes, 'Keep label');
    assert.equal(dialog.hidden, undefined);
    assert.equal(dialog.button.prop('disabled'), false);
    assert.match(messages.at(-1), /retained/);
    dom.window.close();
});
