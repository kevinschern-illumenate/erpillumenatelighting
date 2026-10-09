import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalogIssues, unresolvedLinks, recordName } from '../src/catalog-model.js';
import {
  namingField, renameRecords, renameConflicts, textReplacer, findReplace, applyReplace,
} from '../src/rename-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const names = (catalog, doctype) => catalog.records[doctype].map(row => recordName(doctype, row, schema));

test('naming fields follow the DocType naming rule', () => {
  assert.equal(namingField('Item', schema), 'item_code');
  assert.equal(namingField('ilL-Fixture-Template', schema), 'template_code');
  assert.equal(namingField('ilL-Rel-Endcap-Map', schema), null);
});

test('renaming a template updates links, dynamic links and format names', () => {
  const catalog = structuredClone(examples.fixture);
  const before = structuredClone(catalog);
  const result = renameRecords(catalog, schema, [{ doctype: 'ilL-Fixture-Template', from: 'DEMO-FIXTURE', to: 'DEMO2-FIXTURE' }]);
  const next = result.catalog;
  assert.deepEqual(catalog, before, 'the original draft is unchanged');
  assert.deepEqual(names(next, 'ilL-Fixture-Template'), ['DEMO2-FIXTURE']);
  assert.ok(next.records['ilL-Rel-Endcap-Map'].every(row => row.fixture_template === 'DEMO2-FIXTURE'));
  assert.equal(next.records['ilL-Rel-Driver-Eligibility'][0].fixture_template, 'DEMO2-FIXTURE');
  assert.equal(next.records['ilL-Webflow-Product'][0].fixture_template, 'DEMO2-FIXTURE');
  assert.match(names(next, 'ilL-Rel-Endcap-Map')[0], /^DEMO2-FIXTURE-/);
  assert.deepEqual(unresolvedLinks(next, schema), []);
  assert.deepEqual(catalogIssues(next, schema), []);
  assert.equal(result.changes.filter(change => change.rename).length, 1);
});

test('renaming an Item cascades through records named from it', () => {
  const result = renameRecords(examples.fixture, schema, [{ doctype: 'Item', from: 'DEMO-TAPE', to: 'NEW-TAPE' }]);
  const next = result.catalog;
  // The LED Tape spec is named by its Item, the offering by its spec, and the template links the offering.
  assert.deepEqual(names(next, 'ilL-Spec-LED Tape'), ['NEW-TAPE']);
  assert.equal(next.records['ilL-Rel-Tape Offering'][0].tape_spec, 'NEW-TAPE');
  assert.equal(next.records['ilL-Rel-Leader-Cable-Map'][0].tape_spec, 'NEW-TAPE');
  assert.equal(next.records['ilL-Fixture-Template'][0].allowed_tape_offerings[0].tape_offering, 'NEW-TAPE-3000K-Standard');
  assert.deepEqual(unresolvedLinks(next, schema), []);
  assert.deepEqual(catalogIssues(next, schema), []);
  assert.deepEqual(result.renamed.map(item => item.doctype).sort(),
    ['Item', 'ilL-Rel-Leader-Cable-Map', 'ilL-Rel-Tape Offering', 'ilL-Spec-LED Tape']);
});

test('renaming a linked-only name retargets links and leaves declarations alone', () => {
  const result = renameRecords(examples.fixture, schema, [{ doctype: 'ilL-Spec-Driver', from: 'EXISTING-96W-DRIVER', to: 'OTHER-DRIVER' }]);
  assert.equal(result.catalog.records['ilL-Rel-Driver-Eligibility'][0].driver_spec, 'OTHER-DRIVER');
  assert.deepEqual(result.catalog.external_links['ilL-Spec-Driver'], ['EXISTING-96W-DRIVER']);
});

test('rename conflicts report empty, duplicate, draft and ERPNext names', () => {
  const reference = { doctypes: { Item: { source: 'export', records: { 'LIVE-ITEM': {} } } } };
  const conflicts = renameConflicts(examples.fixture, schema, reference, [
    { doctype: 'Item', from: 'DEMO-TAPE', to: '' },
    { doctype: 'Item', from: 'DEMO-LEADER', to: 'CH-DEMO-WH' },
    { doctype: 'Item', from: 'ACC-DEMO-MC', to: 'LIVE-ITEM' },
    { doctype: 'Item', from: 'EC-DEMO-WH-NO', to: 'FREE' },
    { doctype: 'Item', from: 'EC-DEMO-WH-HO', to: 'FREE' },
  ]);
  assert.deepEqual([...conflicts.keys()], [0, 1, 2, 4]);
  assert.match(conflicts.get(2), /ERPNext/);
  // Swapping names with a record that is itself renamed away is allowed.
  assert.equal(renameConflicts(examples.fixture, schema, null, [
    { doctype: 'Item', from: 'DEMO-LEADER', to: 'CH-DEMO-WH' }, { doctype: 'Item', from: 'CH-DEMO-WH', to: 'CH-NEW' },
  ]).size, 0);
});

test('text replacer escapes plain text, supports regex groups, and rejects empty matches', () => {
  assert.equal(textReplacer({ find: 'a.b', replace: '$1' })('xa.bx'), 'x$1x');
  assert.equal(textReplacer({ find: 'a.b', replace: 'z' })('axb'), null);
  assert.equal(textReplacer({ find: 'CH-(\\w+)', replace: 'PR-$1', regex: true })('CH-DEMO'), 'PR-DEMO');
  assert.equal(textReplacer({ find: 'demo', replace: 'X' })('DEMO-demo'), 'X-X');
  assert.equal(textReplacer({ find: 'demo', replace: 'X', matchCase: true })('DEMO-demo'), 'DEMO-X');
  assert.equal(textReplacer({ find: 'DEMO', replace: 'X', wholeValue: true })('DEMO-TAPE'), null);
  assert.throws(() => textReplacer({ find: 'x*', regex: true }), /empty text/);
  assert.throws(() => textReplacer({ find: '(', regex: true }));
});

test('find and replace on names renames a whole series with links following', () => {
  const changes = findReplace(examples.fixture, schema, { find: 'DEMO', replace: 'CAST', scope: 'names', matchCase: true });
  assert.ok(changes.every(change => change.kind === 'name'));
  assert.ok(changes.some(change => change.doctype === 'Item' && change.to === 'CH-CAST-WH'));
  const next = applyReplace(examples.fixture, schema, changes).catalog;
  assert.deepEqual(names(next, 'ilL-Fixture-Template'), ['CAST-FIXTURE']);
  assert.ok(names(next, 'Item').every(name => !name.includes('DEMO')));
  assert.equal(next.records['ilL-Spec-Profile'][0].item, 'CH-CAST-WH');
  assert.deepEqual(unresolvedLinks(next, schema), []);
  assert.deepEqual(catalogIssues(next, schema), []);
});

test('find and replace on all text also edits values and child rows, within chosen DocTypes', () => {
  const changes = findReplace(examples.fixture, schema, { find: 'Example', replace: 'Castle', scope: 'text', matchCase: true });
  const fields = changes.map(change => `${change.doctype}.${change.path}`);
  assert.ok(fields.includes('Item.item_name'));
  assert.ok(fields.includes('ilL-Fixture-Template.template_name'));
  // The series is renamed, so links to it follow the rename instead of being listed again.
  assert.ok(changes.some(change => change.kind === 'name' && change.doctype === 'ilL-Attribute-Series'));
  assert.ok(!fields.includes('ilL-Spec-Profile.series'));
  const next = applyReplace(examples.fixture, schema, changes).catalog;
  assert.equal(next.records['ilL-Spec-Profile'][0].series, 'Castle Series');
  assert.equal(next.records.Item[0].item_name, 'Castle DEMO-TAPE');
  assert.deepEqual(catalogIssues(next, schema), []);

  const child = findReplace(examples.fixture, schema, { find: 'Frosted', replace: 'Clear', scope: 'text', doctypes: ['ilL-Fixture-Template'] });
  assert.deepEqual(child.map(change => change.path), ['allowed_options[1].lens_appearance']);
  assert.equal(applyReplace(examples.fixture, schema, child).catalog.records['ilL-Fixture-Template'][0].allowed_options[1].lens_appearance, 'Clear');
  assert.equal(examples.fixture.records['ilL-Fixture-Template'][0].allowed_options[1].lens_appearance, 'Frosted');
});
