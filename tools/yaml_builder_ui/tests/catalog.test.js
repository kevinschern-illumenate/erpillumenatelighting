import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, stringify } from 'yaml';
import { blankRecord, catalogIssues, parseCatalog, unresolvedLinks, makeItemRecords } from '../src/catalog-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));

for (const [product, catalog] of Object.entries(examples)) test(`${product}: example serializes and reopens without data loss`, () => {
  const yaml = stringify(catalog);
  const reopened = parseCatalog(yaml, parse, schema);
  assert.deepEqual(reopened, catalog);
  assert.deepEqual(catalogIssues(reopened, schema), []);
  assert.deepEqual(unresolvedLinks(reopened, schema), []);
});

test('unknown fields and changed selections are visible before download', () => {
  const catalog = structuredClone(examples.driver);
  catalog.records['ilL-Spec-Driver'][0].max_wattage = 'invalid';
  catalog.records['ilL-Spec-Driver'][0].typo = true;
  const issues = catalogIssues(catalog, schema);
  assert.ok(issues.some(issue => issue.includes('max_wattage')));
  assert.ok(issues.some(issue => issue.includes('typo')));
});

test('unresolved dynamic links and missing Item creation preserve authored values', () => {
  const catalog = structuredClone(examples['led-sheet']);
  catalog.records['ilL-LED-Sheet-Template'][0].leader_cable_item = 'NEW-LEADER';
  catalog.records['ilL-LED-Sheet-Template'][0].allowed_options[0].attribute_link = 'TYPO';
  const missing = unresolvedLinks(catalog, schema);
  assert.ok(missing.some(link => link.doctype === 'Item' && link.name === 'NEW-LEADER'));
  assert.ok(missing.some(link => link.doctype === 'ilL-Attribute-CCT' && link.name === 'TYPO'));
  const generated = makeItemRecords(catalog, schema);
  assert.equal(generated.records.Item.at(-1).item_code, 'NEW-LEADER');
  assert.equal(generated.records.Item.at(-1).item_group, undefined);
  assert.equal(catalog.records.Item.some(row => row.item_code === 'NEW-LEADER'), false);
});

test('false checkboxes, zero prices and quoted attribute names survive YAML', () => {
  const catalog = structuredClone(examples.driver);
  const template = catalog.records['ilL-Driver-Template'][0];
  template.base_price_msrp = 0;
  template.variants[0].is_default = 0;
  template.allowed_options[0].option_value = '00096';
  assert.deepEqual(parseCatalog(stringify(catalog), parse, schema), catalog);
  assert.equal(blankRecord('ilL-Driver-Template', schema).is_active, 1);
});

test('malformed imports cannot replace the current draft', () => {
  for (const value of [null, [], {}, { schema_version: 2, product_type: 'driver', records: { Item: 'wrong' } }]) {
    assert.throws(() => parseCatalog(JSON.stringify(value), JSON.parse, schema));
  }
});
