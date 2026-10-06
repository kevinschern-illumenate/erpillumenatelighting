import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalogIssues, emptyCatalog, recordName, unresolvedLinks } from '../src/catalog-model.js';
import { cloneFamily, copyable, discoverFamily, ownerIndex, rootTypes, ruleRenamer } from '../src/clone-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const TABLES = new Set(['Table', 'Table MultiSelect']);
const root = { doctype: 'ilL-Fixture-Template', name: 'DEMO-FIXTURE' };

/** An ERPNext export holding the fixture example, plus a second family sharing its endcap Item. */
function exported({ live = false } = {}) {
  const records = structuredClone(examples.fixture.records);
  records['ilL-Fixture-Template'].push({ template_code: 'OTHER-FIXTURE', template_name: 'Other', is_active: 1 });
  records['ilL-Rel-Endcap-Map'].push({ fixture_template: 'OTHER-FIXTURE', endcap_style: 'Solid', endcap_color: 'White', endcap_item: 'EC-DEMO-WH-NO' });
  const doctypes = {};
  for (const [doctype, rows] of Object.entries(records)) {
    const tables = schema.doctypes[doctype].fields.filter(field => TABLES.has(field.type || field.fieldtype)).map(field => field.fieldname);
    doctypes[doctype] = { source: live ? 'live' : 'export', records: Object.fromEntries(rows.map(row => {
      const copy = structuredClone(row);
      if (live) tables.forEach(field => delete copy[field]);
      return [recordName(doctype, row, schema), copy];
    })) };
  }
  for (const [doctype, names] of Object.entries(examples.fixture.external_links)) {
    doctypes[doctype] ||= { source: 'export', records: {} };
    names.forEach(name => { doctypes[doctype].records[name] ||= {}; });
  }
  return { source: live ? 'live' : 'export', exported_on: '2026-10-06', doctypes, records };
}
const fromExport = reference => (doctype, name) => reference.doctypes[doctype]?.records?.[name];
const byMode = (discovery, mode) => discovery.nodes.filter(node => node.mode === mode).map(node => `${node.doctype} ${node.name}`).sort();

test('rename rules keep the case of what they match, and apply in order', () => {
  const rename = ruleRenamer([{ find: 'CA01', replace: 'CA03' }, { find: 'castle', replace: 'keep' }]);
  assert.equal(rename('ILL-CA01-SW'), 'ILL-CA03-SW');
  assert.equal(rename('ill-ca01-sw'), 'ill-ca03-sw');
  assert.equal(rename('Castle Series'), 'keep Series');
  assert.equal(ruleRenamer([{ find: 'ca01', replace: 'X' }], { matchCase: true })('CA01-ca01'), 'CA01-X');
  assert.equal(ruleRenamer([{ find: 'a.b', replace: 'z' }])('axb'), 'axb');
  assert.equal(ruleRenamer([])('SAME'), 'SAME');
});

test('roots are templates or Webflow products; attributes and masters are never copied', () => {
  assert.ok(rootTypes(schema).includes('ilL-Fixture-Template') && rootTypes(schema).includes('ilL-Webflow-Product'));
  assert.equal(copyable('ilL-Attribute-Finish', schema), false);
  assert.equal(copyable('UOM', schema), false);
  assert.equal(copyable('Item', schema), true);
});

test('owned records are found by their template, spec or Item, never by sharing an Item', () => {
  const index = ownerIndex(exported(), schema);
  const owned = name => (index.get(JSON.stringify(['ilL-Fixture-Template', name])) || []).map(item => item.doctype).sort();
  assert.deepEqual(owned('DEMO-FIXTURE'), ['ilL-Rel-Driver-Eligibility', 'ilL-Rel-Endcap-Map', 'ilL-Rel-Endcap-Map', 'ilL-Rel-Mounting-Accessory-Map', 'ilL-Webflow-Product']);
  assert.deepEqual(owned('OTHER-FIXTURE'), ['ilL-Rel-Endcap-Map']);
  assert.deepEqual(index.get(JSON.stringify(['Item', 'CH-DEMO-WH'])), [{ doctype: 'ilL-Spec-Profile', name: 'CH-DEMO-WH' }]);
});

test('renaming only the template copies the template and its maps, linking everything else', () => {
  const reference = exported();
  const rename = ruleRenamer([{ find: 'DEMO-FIXTURE', replace: 'NEW-FIXTURE' }]);
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), rename });
  assert.deepEqual(byMode(discovery, 'copy'), [
    'ilL-Fixture-Template DEMO-FIXTURE',
    'ilL-Rel-Driver-Eligibility ilL-Fixture-Template-DEMO-FIXTURE-EXISTING-96W-DRIVER',
    'ilL-Rel-Endcap-Map DEMO-FIXTURE-Feed Through-White',
    'ilL-Rel-Endcap-Map DEMO-FIXTURE-Solid-White',
    'ilL-Rel-Mounting-Accessory-Map ilL-Fixture-Template-DEMO-FIXTURE-Mounting Clip-ACC-DEMO-MC',
  ]);
  // The other family's endcap map shares an Item, but it belongs to OTHER-FIXTURE.
  assert.ok(!discovery.nodes.some(node => node.name.startsWith('OTHER-FIXTURE')));
  const product = discovery.nodes.find(node => node.doctype === 'ilL-Webflow-Product');
  assert.equal(product.mode, 'link');
  assert.match(product.reason, /unchanged/);
  // An export already holds child tables, so nothing needs fetching.
  assert.deepEqual(discovery.needed, []);

  const result = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference));
  assert.equal(result.added, 5);
  const next = result.catalog;
  assert.deepEqual(next.records['ilL-Fixture-Template'].map(row => row.template_code), ['NEW-FIXTURE']);
  assert.ok(next.records['ilL-Rel-Endcap-Map'].every(row => row.fixture_template === 'NEW-FIXTURE'));
  assert.equal(next.records['ilL-Rel-Endcap-Map'][0].endcap_item, 'EC-DEMO-WH-NO');
  // Predicted names match the names the copies end up with.
  const predicted = discovery.nodes.filter(node => node.mode === 'copy').map(node => node.newName).sort();
  const actual = Object.entries(next.records).flatMap(([doctype, rows]) => rows.map(row => recordName(doctype, row, schema))).sort();
  assert.deepEqual(actual, predicted);
  assert.deepEqual(unresolvedLinks(next, schema, reference), []);
  assert.deepEqual(catalogIssues(next, schema, reference), []);
});

test('a series rename copies the whole family, cascading through specs, offerings and child rows', () => {
  const reference = exported();
  const rename = ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]);
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), rename });
  const copies = byMode(discovery, 'copy');
  for (const expected of ['Item DEMO-TAPE', 'ilL-Spec-LED Tape DEMO-TAPE', 'ilL-Rel-Tape Offering DEMO-TAPE-3000K-Standard',
    'ilL-Rel-Leader-Cable-Map DEMO-TAPE-Single End Feed-DEMO-LEADER', 'ilL-Spec-Profile CH-DEMO-WH', 'ilL-Rel-Profile Lens CH-DEMO-WH',
    'ilL-Spec-Lens LNS-DEMO-WH-FR', 'ilL-Spec-Accessory EC-DEMO-WH-NO', 'Item ACC-DEMO-MC']) assert.ok(copies.includes(expected), expected);
  assert.ok(byMode(discovery, 'link').includes('ilL-Attribute-Finish White'));
  assert.ok(byMode(discovery, 'link').includes('ilL-Spec-Driver EXISTING-96W-DRIVER'));
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference)).catalog;
  assert.equal(next.records['ilL-Fixture-Template'][0].allowed_tape_offerings[0].tape_offering, 'CAST-TAPE-3000K-Standard');
  assert.equal(next.records['ilL-Rel-Profile Lens'][0].compatible_lenses[0].lens_spec, 'LNS-CAST-WH-FR');
  assert.deepEqual(unresolvedLinks(next, schema, reference), []);
  assert.deepEqual(catalogIssues(next, schema, reference), []);
});

test('links to copies whose stored names predate their format rule follow the copy', () => {
  const reference = exported();
  const offerings = reference.doctypes['ilL-Rel-Tape Offering'].records;
  offerings['LEGACY-OFFERING'] = offerings['DEMO-TAPE-3000K-Standard'];
  delete offerings['DEMO-TAPE-3000K-Standard'];
  reference.doctypes['ilL-Fixture-Template'].records['DEMO-FIXTURE'].allowed_tape_offerings[0].tape_offering = 'LEGACY-OFFERING';
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), rename: ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]) });
  const offering = discovery.nodes.find(node => node.doctype === 'ilL-Rel-Tape Offering');
  assert.deepEqual([offering.name, offering.newName, offering.mode], ['LEGACY-OFFERING', 'CAST-TAPE-3000K-Standard', 'copy']);
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference)).catalog;
  assert.equal(next.records['ilL-Fixture-Template'][0].allowed_tape_offerings[0].tape_offering, 'CAST-TAPE-3000K-Standard');
  assert.deepEqual(catalogIssues(next, schema, reference), []);

  // A spec whose stored name differs from its Item (the Item was renamed later) is unchanged too.
  reference.doctypes['ilL-Spec-Driver'].records['EXISTING-96W-DRIVER'] = { item: 'ZZZ_EXISTING-96W-DRIVER' };
  const driver = discoverFamily({ root, reference, schema, full: fromExport(reference), rename: ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]) })
    .nodes.find(node => node.doctype === 'ilL-Spec-Driver');
  assert.equal(driver.mode, 'link');

  // Unchanged, the legacy name is kept as a link even though it differs from the format.
  const kept = discoverFamily({ root, reference, schema, full: fromExport(reference), rename: ruleRenamer([{ find: 'DEMO-FIXTURE', replace: 'NEW-FIXTURE' }]) });
  assert.equal(kept.nodes.find(node => node.doctype === 'ilL-Rel-Tape Offering').mode, 'link');
});

test('new names already in ERPNext link to the existing record instead of copying', () => {
  const reference = exported();
  reference.doctypes.Item.records['CH-CAST-WH'] = { item_name: 'Existing profile' };
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), rename: ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]) });
  const item = discovery.nodes.find(node => node.doctype === 'Item' && node.name === 'CH-DEMO-WH');
  assert.equal(item.mode, 'existing');
  assert.deepEqual(item.modes, ['existing', 'link']);
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference)).catalog;
  assert.ok(!next.records.Item.some(row => row.item_code === 'CH-CAST-WH'));
  assert.equal(next.records['ilL-Spec-Profile'][0].item, 'CH-CAST-WH');
  assert.deepEqual(catalogIssues(next, schema, reference), []);
});

test('keeping a record keeps the records named from it, and the copies link the original', () => {
  const reference = exported();
  const modes = new Map([[JSON.stringify(['Item', 'DEMO-TAPE']), 'link']]);
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), modes, rename: ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]) });
  // The spec is named by its Item and the offering by its spec, so both stay as they are.
  assert.deepEqual(discovery.nodes.filter(node => node.name.startsWith('DEMO-TAPE')).map(node => [node.doctype, node.mode]),
    [['ilL-Rel-Tape Offering', 'link'], ['Item', 'link']]);
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference)).catalog;
  assert.equal(next.records['ilL-Spec-LED Tape'], undefined);
  assert.equal(next.records['ilL-Fixture-Template'][0].allowed_tape_offerings[0].tape_offering, 'DEMO-TAPE-3000K-Standard');
  assert.deepEqual(catalogIssues(next, schema, reference), []);
});

test('in ERPNext, copies are fetched so links in their child tables are followed', () => {
  const live = exported({ live: true });
  const rename = ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]);
  const fetched = new Map();
  const full = (doctype, name) => fetched.get(JSON.stringify([doctype, name]));
  let discovery = discoverFamily({ root, reference: live, schema, full, rename });
  // Top-level links come from the list; child-table links wait for the fetched record.
  assert.deepEqual(discovery.needed[0], root);
  assert.ok(discovery.nodes.some(node => node.doctype === 'ilL-Spec-Profile' && node.mode === 'copy'));
  assert.ok(!discovery.nodes.some(node => node.doctype === 'ilL-Rel-Tape Offering'));
  for (let round = 0; discovery.needed.length && round < 10; round += 1) {
    for (const { doctype, name } of discovery.needed) {
      fetched.set(JSON.stringify([doctype, name]), structuredClone(live.records[doctype].find(row => recordName(doctype, row, schema) === name)));
    }
    discovery = discoverFamily({ root, reference: live, schema, full, rename });
  }
  assert.deepEqual(discovery.needed, []);
  assert.ok(discovery.nodes.some(node => node.doctype === 'ilL-Rel-Tape Offering' && node.mode === 'copy'));
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, full).catalog;
  assert.equal(next.records['ilL-Fixture-Template'][0].allowed_options.length, 6);
  assert.deepEqual(catalogIssues(next, schema, live), []);
});

test('a copied template and product do not link each other, and records already in the draft are skipped', () => {
  const reference = exported();
  reference.doctypes['ilL-Fixture-Template'].records['DEMO-FIXTURE'].webflow_product = 'example-fixture';
  const rename = ruleRenamer([{ find: 'DEMO', replace: 'CAST' }, { find: 'example', replace: 'castle' }]);
  const discovery = discoverFamily({ root, reference, schema, full: fromExport(reference), rename });
  const draft = emptyCatalog('fixture');
  draft.records.Item = [{ item_code: 'CAST-TAPE', item_name: 'Already drafted' }];
  const result = cloneFamily(draft, schema, discovery, fromExport(reference));
  assert.deepEqual(result.cleared, [{ doctype: 'ilL-Fixture-Template', name: 'CAST-FIXTURE', product: 'castle-fixture' }]);
  assert.equal(result.catalog.records['ilL-Fixture-Template'][0].webflow_product, undefined);
  assert.equal(result.catalog.records['ilL-Webflow-Product'][0].fixture_template, 'CAST-FIXTURE');
  assert.deepEqual(result.skipped, [{ doctype: 'Item', name: 'CAST-TAPE' }]);
  assert.equal(result.catalog.records.Item.filter(row => row.item_code === 'CAST-TAPE').length, 1);
  assert.equal(result.catalog.records.Item[0].item_name, 'Already drafted');
});

test('rules can also rewrite text in the copies, and names built from text follow', () => {
  const reference = exported();
  const rename = ruleRenamer([{ find: 'DEMO', replace: 'CAST' }, { find: 'Example', replace: 'Castle' }]);
  const options = { root, reference, schema, full: fromExport(reference), rename };
  const plain = cloneFamily(emptyCatalog('fixture'), schema, discoverFamily(options), fromExport(reference)).catalog;
  assert.equal(plain.records['ilL-Fixture-Template'][0].default_profile_family, 'DEMO');
  const discovery = discoverFamily({ ...options, renameText: rename });
  const next = cloneFamily(emptyCatalog('fixture'), schema, discovery, fromExport(reference), { renameText: rename }).catalog;
  const template = next.records['ilL-Fixture-Template'][0];
  assert.deepEqual([template.default_profile_family, template.template_name], ['CAST', 'Castle Linear fixtures']);
  assert.equal(next.records['ilL-Spec-Profile'][0].family, 'CAST');
  // Links are renamed only through record renames; Select values are never rewritten.
  assert.equal(next.records['ilL-Rel-Mounting-Accessory-Map'][0].template_type, 'ilL-Fixture-Template');
  assert.equal(next.records['ilL-Spec-LED Tape'][0].leader_cable_item, 'CAST-LEADER');
  assert.deepEqual(catalogIssues(next, schema, reference), []);
});

test('the copy limit stops discovery and says so', () => {
  const reference = exported();
  const discovery = discoverFamily({ root, reference, schema, full: () => undefined, rename: ruleRenamer([{ find: 'DEMO', replace: 'CAST' }]), limit: 3 });
  assert.equal(discovery.truncated, true);
  assert.equal(discovery.needed.length, 3);
});
