import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { emptyCatalog, familyTypes } from '../src/catalog-model.js';
import { addAsIs, editable, notifyParent, openList, openParam, parentMessage, productFor } from '../src/embed-bridge.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const ORIGIN = 'https://erp.example.test';

function frame() {
  const sent = [];
  const parent = { postMessage: (message, target) => sent.push({ message, target }) };
  return { win: { parent, location: { origin: ORIGIN } }, parent, sent };
}

test('messages go to the framing page on our own origin, never when not framed', () => {
  const { win, sent } = frame();
  assert.equal(notifyParent(win, { type: 'dirty', dirty: true }), true);
  assert.deepEqual(sent, [{ message: { source: 'ill-catalog-builder', type: 'dirty', dirty: true }, target: ORIGIN }]);
  const top = { location: { origin: ORIGIN } };
  top.parent = top;
  assert.equal(notifyParent(top, { type: 'ready' }), false);
  assert.equal(notifyParent(null, { type: 'ready' }), false);
});

test('only same-origin messages from the parent frame tagged by the Command Center are accepted', () => {
  const { win, parent } = frame();
  const good = { origin: ORIGIN, source: parent, data: { source: 'ill-command-center', type: 'open', records: [] } };
  assert.deepEqual(parentMessage(good, win), good.data);
  assert.equal(parentMessage({ ...good, origin: 'https://evil.test' }, win), null);
  assert.equal(parentMessage({ ...good, source: {} }, win), null);
  assert.equal(parentMessage({ ...good, data: { ...good.data, source: 'ill-catalog-builder' } }, win), null);
  assert.equal(parentMessage({ ...good, data: 'open' }, win), null);
  const top = { location: { origin: ORIGIN } };
  top.parent = top;
  assert.equal(parentMessage({ ...good, source: top }, top), null);
});

test('open lists are cleaned, deduplicated and read from ?open=', () => {
  assert.deepEqual(openList([{ doctype: 'Item', name: ' A ' }, { doctype: 'Item', name: 'A' }, { doctype: '', name: 'B' }, null, { doctype: 'Item' }]),
    [{ doctype: 'Item', name: 'A' }]);
  assert.deepEqual(openList('nope'), []);
  assert.deepEqual(openParam('?open=ilL-Fixture-Template:ILL-A:01&open=Item:X,Item:Y&embed=1'), [
    { doctype: 'ilL-Fixture-Template', name: 'ILL-A:01' }, { doctype: 'Item', name: 'X' }, { doctype: 'Item', name: 'Y' }]);
  assert.deepEqual(openParam('?open=nocolon&open=:x'), []);
  assert.deepEqual(openParam(''), []);
});

test('records go to the product they belong to, staying on the active product when it fits', () => {
  for (const [key, product] of Object.entries(schema.products)) {
    const chosen = productFor(product.template, schema, 'nothing-active', familyTypes);
    assert.equal(schema.products[chosen].template, product.template, `${key} template`);
  }
  assert.equal(productFor('ilL-Extrusion-Kit-Template', schema, 'fixture', familyTypes), 'extrusion-kit');
  assert.equal(productFor('ilL-Driver-Template', schema, 'fixture', familyTypes), 'driver');
  // tape and neon share a template: the active one wins.
  assert.equal(productFor('ilL-Tape-Neon-Template', schema, 'neon', familyTypes), 'neon');
  assert.equal(productFor('ilL-Spec-Profile', schema, 'extrusion-kit', familyTypes), 'extrusion-kit');
  assert.equal(productFor('ilL-Spec-Profile', schema, 'driver', familyTypes), 'fixture');
  // Item belongs to no single family: it stays where the author is.
  assert.equal(productFor('Item', schema, 'controller', familyTypes), 'controller');
});

test('only catalog parent DocTypes can be opened or created', () => {
  assert.equal(editable('ilL-Fixture-Template', schema), true);
  assert.equal(editable('Sales Order', schema), false);
  const child = Object.keys(schema.doctypes).find(name => schema.doctypes[name].istable);
  assert.equal(editable(child, schema), false);
});

test('opened records keep their names and are never added twice', () => {
  const draft = emptyCatalog('fixture');
  const rows = [{ doctype: 'ilL-Fixture-Template', name: 'ILL-A', record: { template_code: 'ILL-A', template_name: 'A' } }];
  const first = addAsIs(draft, rows, schema);
  assert.deepEqual(first.added, [{ doctype: 'ilL-Fixture-Template', name: 'ILL-A' }]);
  assert.equal(first.catalog.records['ilL-Fixture-Template'][0].template_code, 'ILL-A');
  assert.notEqual(first.catalog.records['ilL-Fixture-Template'][0], rows[0].record);
  assert.deepEqual(draft.records, {});
  const again = addAsIs(first.catalog, rows, schema);
  assert.deepEqual(again.added, []);
  assert.deepEqual(again.skipped, [{ doctype: 'ilL-Fixture-Template', name: 'ILL-A' }]);
  assert.equal(again.catalog, first.catalog);
});
