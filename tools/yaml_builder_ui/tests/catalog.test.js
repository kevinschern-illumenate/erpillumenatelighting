import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, stringify } from 'yaml';
import {
  blankRecord, catalogIssues, parseCatalog, unresolvedLinks, makeItemRecords,
  inReference, referenceSummary, withReferenceLinks, unconfirmedLinks,
  catalogAddition, mergeAdditions, excludeCatalog, referenceOrigin,
} from '../src/catalog-model.js';

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

test('links to exported ERPNext records resolve and are declared in the YAML', () => {
  const reference = { exported_on: '2026-10-01', doctypes: {
    'ilL-Attribute-Dimming Protocol': { source: 'export', records: { PWM: { label: 'PWM' } } },
    'ilL-Attribute-CCT': { source: 'export', records: { '3000K': {} } },
  } };
  const catalog = structuredClone(examples.tape);
  delete catalog.external_links['ilL-Attribute-Dimming Protocol'];
  assert.ok(unresolvedLinks(catalog, schema).some(link => link.name === 'PWM'));
  assert.ok(!unresolvedLinks(catalog, schema, reference).some(link => link.name === 'PWM'));
  assert.deepEqual(catalogIssues(catalog, schema, reference), []);
  const resolved = withReferenceLinks(catalog, schema, reference);
  assert.deepEqual(resolved.external_links['ilL-Attribute-Dimming Protocol'], ['PWM']);
  assert.equal(catalog.external_links['ilL-Attribute-Dimming Protocol'], undefined);
  assert.equal(inReference(reference, 'ilL-Attribute-CCT', '3000K'), true);
  assert.equal(referenceSummary('ilL-Attribute-Dimming Protocol', { label: 'PWM' }, schema), '');
});

test('existing ERPNext records are not re-imported and unknown declarations are flagged', () => {
  const catalog = structuredClone(examples.tape);
  const tape = catalog.records['ilL-Spec-LED Tape'][0].item;
  const reference = { doctypes: {
    'ilL-Spec-LED Tape': { source: 'export', records: { [tape]: {} } },
    'ilL-Attribute-CCT': { source: 'export', records: { '2700K': {} } },
    Item: { source: 'links', records: {} },
  } };
  assert.ok(catalogIssues(catalog, schema, reference).some(issue => issue.includes(`${tape} already exists in ERPNext`)));
  assert.deepEqual(unconfirmedLinks(catalog, reference), [{ doctype: 'ilL-Attribute-CCT', name: '3000K' }]);
});

test('catalogs added to the reference count as existing for other catalogs only', () => {
  const tape = structuredClone(examples.tape);
  tape.series_name = 'Flex';
  tape.add_to_reference = true;
  assert.deepEqual(parseCatalog(stringify(tape), parse, schema), tape);
  const addition = catalogAddition(tape, schema, '2026-10-02');
  const spec = tape.records['ilL-Spec-LED Tape'][0].item;
  assert.equal(addition.catalog, 'tape/Flex');
  const reference = { exported_on: '2026-10-01', doctypes: {} };
  const merged = mergeAdditions(reference, [addition], schema);
  assert.equal(inReference(merged, 'ilL-Spec-LED Tape', spec), true);
  assert.equal(referenceOrigin(merged, 'ilL-Spec-LED Tape', spec).pending, true);
  assert.equal(inReference(excludeCatalog(merged, tape), 'ilL-Spec-LED Tape', spec), false);
  assert.ok(!catalogIssues(tape, schema, excludeCatalog(merged, tape)).some(issue => issue.includes('already exists')));
  const fixture = structuredClone(examples.fixture);
  assert.equal(inReference(excludeCatalog(merged, fixture), 'ilL-Spec-LED Tape', spec), true);
  const logged = { ...reference, catalog_additions: [{ catalog: 'tape/Flex', added_on: '2026-10-02', records: {} }] };
  assert.equal(mergeAdditions(logged, [addition], schema), logged);
  assert.ok(catalogIssues({ ...tape, series_name: '' }, schema).includes('Name the catalog to add it to the ERPNext reference'));
  assert.throws(() => parseCatalog(stringify({ ...tape, add_to_reference: 'yes' }), parse, schema));
});
