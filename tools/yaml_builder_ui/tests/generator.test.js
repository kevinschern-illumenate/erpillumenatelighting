import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, stringify } from 'yaml';
import { catalogIssues, parseCatalog } from '../src/catalog-model.js';
import {
  allowedOptions, availableNames, cleanRecipe, expandPattern, generateRows, optionTypes, presetsFor, recipeErrors,
  savedRecipes, withRecipe, MAX_COMBINATIONS,
} from '../src/generator-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const reference = { source: 'export', doctypes: {
  'ilL-Attribute-Endcap Style': { source: 'export', records: { Solid: { code: 'NO' }, 'Feed Through': { code: 'HO' } } },
  'ilL-Attribute-Endcap Color': { source: 'export', records: { White: { code: 'WH' }, BK: { code: 'BK' } } },
  'ilL-Attribute-Finish': { source: 'export', records: { White: { code: 'WH' }, Black: { code: 'BK' } } },
  'ilL-Attribute-Mounting Method': { source: 'export', records: { 'Mounting Clip': { code: 'MC' } } },
  'ilL-Rel-Finish Endcap Color': { source: 'export', records: { 'Black-BK': { finish: 'Black', endcap_color: 'BK' } } },
  'ilL-Rel-Endcap-Map': { source: 'export', records: { 'LIVE-FIXTURE-Solid-White': {} } },
} };

/** The fixture example allowing a second finish and endcap style. */
function fixtureDraft() {
  const catalog = structuredClone(examples.fixture);
  const options = catalog.records['ilL-Fixture-Template'][0].allowed_options;
  options.push({ option_type: 'Finish', finish: 'Black', is_active: 1 }, { option_type: 'Endcap Style', endcap_style: 'Feed Through', is_active: 1 },
    { option_type: 'Finish', finish: 'Retired', is_active: 0 });
  catalog.external_links['ilL-Attribute-Finish'].push('Black', 'Retired');
  catalog.external_links['ilL-Attribute-Endcap Color'].push('BK');
  return catalog;
}
const context = catalog => ({ catalog, reference, schema });

test('patterns fill tokens, follow links in dotted fields, and report missing or unknown tokens', () => {
  const catalog = fixtureDraft();
  const binding = { template: { value: 'DEMO-FIXTURE', doctype: 'ilL-Fixture-Template' }, pair: { value: 'Black-BK', doctype: 'ilL-Rel-Finish Endcap Color' },
    size: { value: '24', doctype: null } };
  assert.deepEqual(expandPattern('EC-{template.default_profile_family}-{pair.endcap_color.code}-{size}', binding, context(catalog)),
    { text: 'EC-DEMO-BK-24', missing: [], unknown: [] });
  assert.deepEqual(expandPattern('{template.webflow_product}{size.code}{nope}', binding, context(catalog)),
    { text: '', missing: ['template.webflow_product', 'size.code'], unknown: ['nope'] });
});

test('every combination becomes a row, typed to its field, and existing names are marked', () => {
  const catalog = fixtureDraft();
  const recipe = { doctype: 'ilL-Rel-Endcap-Map', axes: [
    { token: 'template', doctype: 'ilL-Fixture-Template', values: ['DEMO-FIXTURE', 'LIVE-FIXTURE'] },
    { token: 'style', doctype: 'ilL-Attribute-Endcap Style', values: ['Solid', 'Feed Through'] },
    { token: 'color', values: ['White', 'White'] },
  ], fields: { fixture_template: '{template}', endcap_style: '{style}', endcap_color: '{color}', endcap_item: 'EC-{style.code}', is_default: 'yes', unknown_field: 'x' } };
  const rows = generateRows(recipe, context(catalog));
  assert.equal(rows.length, 8);
  assert.deepEqual(rows.map(row => row.status), ['draft', 'draft', 'draft', 'draft', 'erpnext', 'erpnext', 'new', 'repeat']);
  const fresh = rows.find(row => row.status === 'new');
  assert.equal(fresh.name, 'LIVE-FIXTURE-Feed Through-White');
  assert.deepEqual(fresh.row, { fixture_template: 'LIVE-FIXTURE', endcap_style: 'Feed Through', endcap_color: 'White', endcap_item: 'EC-HO', is_default: 1, is_active: 1 });
  assert.deepEqual(fresh.binding, { template: 'LIVE-FIXTURE', style: 'Feed Through', color: 'White' });
});

test('records that need a typed name are marked unnamed until a pattern names them', () => {
  const rows = generateRows({ doctype: 'Item', axes: [{ token: 'n', values: ['1', '2'] }], fields: { item_name: 'Part {n}' } }, context(fixtureDraft()));
  assert.deepEqual(rows.map(row => row.status), ['unnamed', 'unnamed']);
  const named = generateRows({ doctype: 'Item', axes: [{ token: 'n', values: ['1', '2'] }], fields: { item_code: 'P-{n}', stock_uom: 'Nos' } }, context(fixtureDraft()));
  assert.deepEqual(named.map(row => [row.name, row.status, row.row.stock_uom]), [['P-1', 'new', 'Nos'], ['P-2', 'new', 'Nos']]);
  // No axes makes one row from constants.
  assert.equal(generateRows({ doctype: 'Item', axes: [], fields: { item_code: 'ONE' } }, context(fixtureDraft())).length, 1);
});

test('recipes with bad or repeated axis names, or too many combinations, do not generate', () => {
  const big = Array.from({ length: 50 }, (_, i) => String(i));
  assert.match(recipeErrors({ axes: [{ token: '1x', values: [] }] })[0], /letters/);
  assert.match(recipeErrors({ axes: [{ token: 'a', values: ['x'] }, { token: 'a', values: ['y'] }] })[0], /Two axes/);
  assert.match(recipeErrors({ axes: [{ token: 'a', values: big }, { token: 'b', values: big }] })[0], new RegExp(String(MAX_COMBINATIONS)));
  assert.deepEqual(generateRows({ doctype: 'Item', axes: [{ token: 'a', values: big }, { token: 'b', values: big }], fields: {} }, context(fixtureDraft())), []);
});

test("allowed options come from the draft's templates, skipping inactive ones", () => {
  const catalog = fixtureDraft();
  assert.deepEqual(allowedOptions(catalog, schema, 'Finish'), ['White', 'Black']);
  assert.deepEqual(allowedOptions(catalog, schema, 'Endcap Style'), ['Solid', 'Feed Through']);
  assert.ok(optionTypes(schema).includes('Mounting Method'));
  assert.deepEqual(availableNames('ilL-Rel-Finish Endcap Color', catalog, reference, schema), ['White-White', 'Black-BK']);
});

test('the endcap map preset fills the missing endcap rows for the allowed options', () => {
  const catalog = fixtureDraft();
  const preset = presetsFor('ilL-Rel-Endcap-Map', catalog, reference, schema).find(item => item.id === 'endcap-map');
  assert.deepEqual(preset.recipe.axes.map(axis => [axis.token, axis.values]),
    [['template', ['DEMO-FIXTURE']], ['style', ['Solid', 'Feed Through']], ['pair', ['White-White', 'Black-BK']]]);
  const rows = generateRows(preset.recipe, context(catalog));
  assert.deepEqual(rows.map(row => [row.name, row.status]), [
    ['DEMO-FIXTURE-Solid-White', 'draft'], ['DEMO-FIXTURE-Solid-BK', 'new'],
    ['DEMO-FIXTURE-Feed Through-White', 'draft'], ['DEMO-FIXTURE-Feed Through-BK', 'new']]);
  const black = rows.find(row => row.name === 'DEMO-FIXTURE-Solid-BK');
  assert.equal(black.row.endcap_item, 'EC-DEMO-BK-NO');
  // The generated Item code matches the Item the example already uses for that combination.
  assert.equal(rows[0].row.endcap_item, 'EC-DEMO-WH-NO');
  assert.deepEqual(rows[0].missing, []);
  const next = { ...catalog, records: { ...catalog.records, 'ilL-Rel-Endcap-Map': [...catalog.records['ilL-Rel-Endcap-Map'], ...rows.filter(row => row.status === 'new').map(row => row.row)] } };
  // Only the new endcap Items remain to create.
  assert.deepEqual(catalogIssues(next, schema, reference), [
    'ilL-Rel-Endcap-Map[2].endcap_item: unresolved Item / EC-DEMO-BK-NO', 'ilL-Rel-Endcap-Map[3].endcap_item: unresolved Item / EC-DEMO-BK-HO']);
});

test('presets exist for the common maps and Items, and only for the chosen DocType', () => {
  const catalog = fixtureDraft();
  assert.deepEqual(presetsFor('Item', catalog, reference, schema).map(item => item.id), ['profile-items', 'lens-items', 'endcap-items']);
  assert.deepEqual(presetsFor('ilL-Spec-Profile', catalog, reference, schema), []);
  const mounting = presetsFor('ilL-Rel-Mounting-Accessory-Map', catalog, reference, schema)[0];
  assert.deepEqual(generateRows(mounting.recipe, context(catalog)).map(row => row.status), ['draft']);
  const leader = presetsFor('ilL-Rel-Leader-Cable-Map', catalog, reference, schema)[0];
  assert.deepEqual(generateRows(leader.recipe, context(catalog)).map(row => [row.row.leader_item, row.status]), [['DEMO-LEADER', 'draft']]);
  const profiles = presetsFor('Item', catalog, reference, schema)[0];
  assert.deepEqual(generateRows(profiles.recipe, context(catalog)).map(row => [row.name, row.status]), [['CH-DEMO-WH', 'draft'], ['CH-DEMO-BK', 'new']]);
});

test('recipes save in the draft, survive YAML, and never reach validation', () => {
  const catalog = fixtureDraft();
  const recipe = cleanRecipe({ doctype: 'Item', axes: [{ token: 'n', doctype: '', values: ['1'] }], fields: { item_code: 'P-{n}', item_name: ' ' } }, 'Parts');
  assert.deepEqual(recipe, { name: 'Parts', doctype: 'Item', axes: [{ token: 'n', values: ['1'] }], fields: { item_code: 'P-{n}' } });
  const saved = withRecipe(catalog, 'Item', 'Parts', recipe);
  assert.deepEqual(savedRecipes(saved, 'Item'), [recipe]);
  assert.deepEqual(savedRecipes(saved, 'UOM'), []);
  const replaced = withRecipe(saved, 'Item', 'Parts', { ...recipe, fields: { item_code: 'Q-{n}' } });
  assert.equal(savedRecipes(replaced).length, 1);
  const reopened = parseCatalog(stringify(replaced), parse, schema);
  assert.deepEqual(savedRecipes(reopened), savedRecipes(replaced));
  assert.deepEqual(catalogIssues(reopened, schema, reference), catalogIssues(catalog, schema, reference));
  assert.equal(withRecipe(replaced, 'Item', 'Parts', null).builder, undefined);
  assert.deepEqual(savedRecipes({ records: {}, builder: { recipes: 'broken' } }), []);
  assert.throws(() => parseCatalog(stringify({ ...catalog, builder: ['x'] }), parse, schema), /builder/);
});
