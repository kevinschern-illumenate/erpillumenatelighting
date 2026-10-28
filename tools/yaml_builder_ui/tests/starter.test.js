import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalogIssues, unresolvedLinks, makeMissingRecords, recordName } from '../src/catalog-model.js';
import { applyStarter, builtinStarters, draftStarter, placeholders, starterPreview, starterRenamer, templateName } from '../src/starter-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const starters = builtinStarters(examples, schema);
const names = catalog => Object.entries(catalog.records).flatMap(([doctype, rows]) => rows.map(row => recordName(doctype, row, schema)));

test('every product type has a built-in starter', () => {
  assert.deepEqual(starters.map(item => item.productType), Object.keys(schema.products));
});

for (const starter of starters) test(`${starter.productType}: a starter makes a complete, consistently named draft`, () => {
  const { catalog, count } = applyStarter(starter, { code: 'LX20', series: 'Lumen Series', name: '' }, { schema });
  assert.equal(catalog.product_type, starter.productType);
  assert.equal(catalog.series_name, 'Lumen Series');
  assert.equal(count, names(starter.catalog).length);
  assert.ok(!JSON.stringify(catalog.records).includes('DEMO'), 'every DEMO name is rewritten');
  assert.ok(!JSON.stringify(catalog.records).includes('Example'), 'every Example label is rewritten');
  assert.deepEqual(unresolvedLinks(catalog, schema), [], 'links follow the renamed records');
  assert.deepEqual(catalogIssues(catalog, schema), []);
  assert.deepEqual(starter.catalog, examples[starter.productType], 'the starter is not mutated');
});

test('product name defaults from the series and is used for the template', () => {
  const fixture = starters.find(item => item.productType === 'fixture');
  const { catalog } = applyStarter(fixture, { code: 'LX20', series: 'Lumen', name: '' }, { schema });
  assert.equal(catalog.records['ilL-Fixture-Template'][0].template_name, 'Lumen Linear fixtures');
  assert.equal(catalog.records['ilL-Fixture-Template'][0].template_code, 'LX20-FIXTURE');
  assert.ok(catalog.records.Item.some(row => row.item_code === 'CH-LX20-WH' && row.item_name === 'Lumen CH-LX20-WH'));
  const named = applyStarter(fixture, { code: 'LX20', series: 'Lumen', name: 'Lumen 20 Recessed' }, { schema }).catalog;
  assert.equal(named.records['ilL-Fixture-Template'][0].template_name, 'Lumen 20 Recessed');
});

test('codes match whole codes only, in upper and lower case', () => {
  const starter = { code: 'LX2', series: 'Old', name: 'Old product' };
  const run = starterRenamer(starter, { code: 'QB7', series: 'New', name: 'New product' });
  assert.equal(run('CH-LX2-WH'), 'CH-QB7-WH');
  assert.equal(run('lx2-slug'), 'qb7-slug');
  assert.equal(run('LX2WH'), 'QB7WH');
  assert.equal(run('LX20'), 'LX20');
  assert.equal(run('FLX2'), 'FLX2');
  assert.equal(run('Old product by Old'), 'New product by New');
});

test('existing attribute records are linked instead of re-created', () => {
  const fixture = starters.find(item => item.productType === 'fixture');
  const reference = { doctypes: { 'ilL-Attribute-Series': { source: 'live', records: { Lumen: {} } } } };
  const { catalog, reused } = applyStarter(fixture, { code: 'LX20', series: 'Lumen', name: '' }, { schema, reference });
  assert.deepEqual(reused, [{ doctype: 'ilL-Attribute-Series', name: 'Lumen' }]);
  assert.equal(catalog.records['ilL-Attribute-Series'], undefined);
  assert.ok(catalog.external_links['ilL-Attribute-Series'].includes('Lumen'));
  assert.deepEqual(unresolvedLinks(catalog, schema, reference), []);
});

test('placeholder links can be pointed at existing ERPNext records', () => {
  const fixture = starters.find(item => item.productType === 'fixture');
  const reference = { doctypes: { 'ilL-Spec-Driver': { source: 'live', records: { 'DRV-96W': {}, 'DRV-60W': {} } } } };
  const found = placeholders(fixture.catalog, reference);
  assert.deepEqual(found, [{ doctype: 'ilL-Spec-Driver', name: 'EXISTING-96W-DRIVER', choices: ['DRV-60W', 'DRV-96W'] }]);
  const picks = new Map([['ilL-Spec-Driver\nEXISTING-96W-DRIVER', 'DRV-96W']]);
  const { catalog } = applyStarter(fixture, { code: 'LX20', series: 'Lumen', name: '' }, { schema, reference, picks });
  assert.ok(!JSON.stringify(catalog).includes('EXISTING-96W-DRIVER'));
  assert.deepEqual(catalog.external_links['ilL-Spec-Driver'], ['DRV-96W']);
  assert.equal(catalog.records['ilL-Rel-Driver-Eligibility'][0].driver_spec, 'DRV-96W');
});

test('a draft saved as a starter makes the next product under new names', () => {
  const first = applyStarter(starters.find(item => item.productType === 'tape'), { code: 'TP1', series: 'Ribbon', name: 'Ribbon Tape' }, { schema }).catalog;
  first.add_to_reference = true;
  assert.equal(templateName(first, schema), 'Ribbon Tape');
  const saved = draftStarter(first, { label: 'My tape', code: 'TP1', series: 'Ribbon', name: 'Ribbon Tape' }, '2026-10-28');
  assert.equal(saved.catalog.add_to_reference, undefined);
  const { catalog } = applyStarter(saved, { code: 'TP2', series: 'Ribbon Pro', name: 'Ribbon Pro Tape' }, { schema });
  assert.ok(!JSON.stringify(catalog.records).includes('TP1'));
  assert.equal(templateName(catalog, schema), 'Ribbon Pro Tape');
  assert.deepEqual(catalogIssues(catalog, schema), []);
});

test('preview flags records that already exist in ERPNext', () => {
  const driver = starters.find(item => item.productType === 'driver');
  const { catalog } = applyStarter(driver, { code: 'D1', series: 'Power', name: '' }, { schema });
  const reference = { doctypes: { Item: { source: 'live', records: { 'D1-DRIVER': {} } } } };
  assert.ok(starterPreview(catalog, schema, reference).some(row => row.doctype === 'Item' && row.name === 'D1-DRIVER' && row.exists));
});

test('missing records are created for every linked DocType a typed name can satisfy', () => {
  const catalog = { schema_version: 2, product_type: 'fixture', series_name: 'S', external_links: {}, records: {
    'ilL-Fixture-Template': [{ template_code: 'T1', template_name: 'T', default_profile_spec: 'CH-T1', series: 'S' }],
  } };
  const { catalog: next, added } = makeMissingRecords(catalog, schema);
  assert.deepEqual(added.map(row => row.doctype).sort(), ['Item', 'ilL-Attribute-Series', 'ilL-Spec-Profile']);
  assert.equal(next.records['ilL-Spec-Profile'][0].item, 'CH-T1');
  assert.equal(next.records.Item[0].item_code, 'CH-T1');
  assert.deepEqual(unresolvedLinks(next, schema).map(link => link.doctype), ['UOM'], 'masters are left to ERPNext');
  assert.deepEqual(catalog.records['ilL-Spec-Profile'], undefined, 'the input is not mutated');
});

test('a saved starter keeps its product name pattern under the new series', () => {
  const saved = { code: 'TP1', series: 'Ribbon', name: 'Ribbon Tape', catalog: { records: {} } };
  const rename = starterRenamer(saved, { code: 'TP2', series: 'Ribbon Pro', name: '' });
  assert.equal(rename('Ribbon Tape'), 'Ribbon Pro Tape');
});

test('a typed product name wins over the series inside the old name', () => {
  const saved = { code: 'TP1', series: 'Ribbon', name: 'Ribbon Tape', catalog: { records: {} } };
  const rename = starterRenamer(saved, { code: 'TP2', series: 'Ribbon Pro', name: 'Totally New' });
  assert.equal(rename('Ribbon Tape · Ribbon TP1'), 'Totally New · Ribbon Pro TP2');
});
