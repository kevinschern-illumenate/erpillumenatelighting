const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

function setup() {
    const dom = new JSDOM(`<body><main data-ill-product-type="LED Sheet" data-ill-product-slug="snow" data-ill-erp-origin="https://erp.test">
        <select id="ill-sheet-spec"><option value="SW">Static White</option></select>
        <select data-ill-sheet-option="CCT"><option value="30">3000K</option></select>
        <input id="ill-sheet-width" value="36"><input id="ill-sheet-width-unit" value="in">
        <input id="ill-sheet-height" value="4"><input id="ill-sheet-height-unit" value="ft">
        <input id="ill-sheet-include-power" type="checkbox"><input id="ill-sheet-protocol" value="0-10V">
        <button id="ill-download-spec-sheet">Download</button></main>`, {runScripts:'outside-only', url:'https://brand.test/products/snow'});
    const w = dom.window, requests = [], alerts = [];
    w.alert = message => alerts.push(message);
    w.fetch = async (url, options) => { requests.push({url, options}); throw new Error('offline'); };
    w.console.error = () => {};
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/webflow_spec_sheet_download.js'), 'utf8'));
    return {dom, w, requests, alerts};
}

test('public Sheet download preserves units and false power without fixture-only requirements', async () => {
    const {dom, w, requests} = setup();
    await new Promise(resolve => w.document.addEventListener('DOMContentLoaded', resolve));
    w.document.querySelector('button').click();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests.length, 1);
    assert.match(requests[0].url, /^https:\/\/erp.test\/api\//);
    const args = new URLSearchParams(requests[0].options.body), selections = JSON.parse(args.get('selections'));
    assert.equal(selections.coverage_width_unit, 'in');
    assert.equal(selections.coverage_width_value, '36');
    assert.equal(selections.include_power_supply, false);
    assert.deepEqual(selections.options, {CCT:'30'});
    assert.equal(selections.spec, 'SW');
    assert.equal(selections.dimming_protocol_code, '0-10V');
    assert.equal(w.document.querySelector('button').disabled, false);
    assert.equal(w.document.querySelector('#ill-sheet-width').value, '36');
    dom.window.close();
});

test('incomplete Sheet dimensions retain entries and do not start a PDF request', async () => {
    const {dom, w, requests, alerts} = setup();
    await new Promise(resolve => w.document.addEventListener('DOMContentLoaded', resolve));
    w.document.querySelector('#ill-sheet-height').value = '';
    w.document.querySelector('button').click();
    assert.equal(requests.length, 0);
    assert.match(alerts[0], /Sheet coverage width and height/);
    assert.equal(w.document.querySelector('#ill-sheet-width').value, '36');
    dom.window.close();
});

test('public Sheet embed mounts only approved choices with accessible labels and full watts', async () => {
    const dom = new JSDOM('<main data-ill-product-type="LED Sheet" data-ill-product-slug="snow" data-ill-erp-origin="https://erp.test"><div data-ill-sheet-configurator></div><button id="ill-download-spec-sheet">Download</button></main>', {runScripts:'outside-only',url:'https://brand.test/snow'});
    const w=dom.window;
    w.fetch=async()=>({ok:true,json:async()=>({message:{success:true,specs:[{name:'TW',cct:'Tunable White',total_sheet_watts:40}],options:{Finish:[{attribute:'White',code:'WH',is_default:1}]},input_protocols:['0-10V']}})});
    w.eval(fs.readFileSync(path.join(__dirname,'../../illumenate_lighting/public/js/webflow_spec_sheet_download.js'),'utf8'));
    await new Promise(resolve=>w.document.addEventListener('DOMContentLoaded',resolve));
    await new Promise(resolve=>setImmediate(resolve));
    assert.match(w.document.querySelector('#ill-sheet-spec').textContent,/40 W per panel/);
    assert.equal(w.document.querySelector('[data-ill-sheet-option="Finish"]').value,'WH');
    assert.equal(w.document.querySelector('#ill-download-spec-sheet').disabled,false);
    for(const label of w.document.querySelectorAll('label')) assert.ok(w.document.getElementById(label.htmlFor));
    assert.equal(w.document.querySelector('#ill-sheet-include-power').checked,true);
    dom.window.close();
});
