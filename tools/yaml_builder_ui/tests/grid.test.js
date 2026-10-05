import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalogIssues, unresolvedLinks } from '../src/catalog-model.js';
import {
  gridColumns, visibleColumns, parseTSV, toTSV, coerceCell, copyMatrix, pasteCells, rowsFromMatrix,
  fillDown, clearCells, duplicateRows, moveRows, removeRows, issueIndex, parseNumber,
} from '../src/grid-model.js';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const column = (fieldtype, extra = {}) => ({ key: 'f', label: 'F', fieldtype, kind: fieldtype === 'Table' ? 'table' : 'field', ...extra });

test('columns put the record name first and keep child tables', () => {
  const item = gridColumns('Item', schema);
  assert.equal(item[0].key, 'item_code');
  assert.ok(item[0].pinned);
  assert.ok(item.some(col => col.key === 'attributes' && col.kind === 'table'));
  assert.equal(gridColumns('ilL-Rel-Endcap-Map', schema)[0].kind, 'computed');
  assert.equal(gridColumns('ilL-Attribute-LED Package', schema)[0].key, 'name');
  assert.ok(!gridColumns('Item Variant Attribute', schema, [], false).some(col => col.pinned));
});

test('hiding empty fields keeps required, pinned and filled columns', () => {
  const rows = examples.driver.records['ilL-Driver-Template'];
  const all = gridColumns('ilL-Driver-Template', schema, rows);
  const shown = visibleColumns(all, rows, { dataOnly: true });
  assert.ok(shown.length < all.length);
  assert.ok(shown.every(col => col.pinned || col.reqd || rows.some(row => row[col.key] !== undefined)));
  assert.deepEqual(visibleColumns(all, rows, { hidden: ['template_name'] }).find(col => col.key === 'template_name'), undefined);
  assert.deepEqual(visibleColumns(all, rows, { filter: 'zzz' }).map(col => col.key), [all[0].key]);
});

test('TSV round-trips tabs, newlines and quotes like a spreadsheet', () => {
  const matrix = [['plain', 'tab\there', 'line\nbreak'], ['"quoted"', '', 'end']];
  assert.deepEqual(parseTSV(toTSV(matrix)), matrix);
  assert.deepEqual(parseTSV('a\tb\r\nc\td\r\n'), [['a', 'b'], ['c', 'd']]);
  assert.deepEqual(parseTSV('"Big" lamp\tx'), [['"Big" lamp', 'x']]);
  assert.deepEqual(parseTSV('one'), [['one']]);
});

test('pasted text becomes the field type, keeping bad values for validation', () => {
  assert.deepEqual(coerceCell(column('Int'), ' 1,200 '), { ok: true, value: 1200 });
  assert.deepEqual(coerceCell(column('Currency'), '$12.50'), { ok: true, value: 12.5 });
  assert.deepEqual(coerceCell(column('Float'), 'abc'), { ok: true, value: 'abc' });
  assert.deepEqual(coerceCell(column('Check'), 'Yes'), { ok: true, value: 1 });
  assert.deepEqual(coerceCell(column('Check'), 'FALSE'), { ok: true, value: 0 });
  assert.deepEqual(coerceCell(column('Select', { options: 'Constant Voltage\nConstant Current' }), 'constant voltage'), { ok: true, value: 'Constant Voltage' });
  assert.deepEqual(coerceCell(column('Data'), '  SKU-1 '), { ok: true, value: 'SKU-1' });
  assert.deepEqual(coerceCell(column('Data'), ''), { ok: true, value: '' });
  assert.deepEqual(coerceCell(column('Table'), '[{"a":1}]'), { ok: true, value: [{ a: 1 }] });
  assert.equal(coerceCell(column('Table'), 'nope').ok, false);
  assert.equal(parseNumber('2.'), 2);
  assert.equal(parseNumber('-.5'), -0.5);
});

test('copy then paste moves a block of cells between rows, including child tables', () => {
  const catalog = structuredClone(examples.driver);
  const rows = catalog.records['ilL-Driver-Template'];
  rows.push({ template_code: 'NEW' });
  const cols = gridColumns('ilL-Driver-Template', schema, rows);
  const order = rows.map((_, i) => i);
  const variants = cols.findIndex(col => col.key === 'variants');
  const copied = copyMatrix(rows, order, cols, { top: 0, bottom: 0, left: 1, right: variants }, 'ilL-Driver-Template', schema);
  const pasted = pasteCells(rows, order, cols, { top: 1, bottom: 1, left: 1, right: 1 }, parseTSV(toTSV(copied)));
  assert.equal(pasted.skipped, 0);
  const { template_code: _a, ...source } = rows[0];
  const { template_code: _b, ...target } = pasted.rows[1];
  for (const col of cols.slice(1, variants + 1)) assert.deepEqual(target[col.key], source[col.key], col.key);
  assert.equal(pasted.rows[1].template_code, 'NEW');
  assert.notEqual(pasted.rows[0], undefined);
  assert.equal(rows[1].variants, undefined, 'rows are not mutated');
});

test('one pasted value fills the selection; extra rows are appended only when allowed', () => {
  const cols = [column('Data', { key: 'a' }), column('Int', { key: 'b' })];
  const rows = [{}, {}, {}];
  const filled = pasteCells(rows, [0, 1, 2], cols, { top: 0, bottom: 2, left: 0, right: 1 }, [['7']]);
  assert.deepEqual(filled.rows, [{ a: '7', b: 7 }, { a: '7', b: 7 }, { a: '7', b: 7 }]);
  const block = [['x', '1'], ['y', '2'], ['z', '3']];
  const grown = pasteCells([{}], [0], cols, { top: 0, bottom: 0, left: 0, right: 0 }, block, () => ({ fresh: 1 }));
  assert.equal(grown.added, 2);
  assert.deepEqual(grown.rows, [{ a: 'x', b: 1 }, { fresh: 1, a: 'y', b: 2 }, { fresh: 1, a: 'z', b: 3 }]);
  const filtered = pasteCells([{}, {}, {}], [0, 2], cols, { top: 0, bottom: 0, left: 0, right: 0 }, block);
  assert.deepEqual(filtered.rows, [{ a: 'x', b: 1 }, {}, { a: 'y', b: 2 }]);
  const cleared = pasteCells([{ a: 'old' }], [0], cols, { top: 0, bottom: 0, left: 0, right: 0 }, [['']]);
  assert.deepEqual(cleared.rows, [{}]);
});

test('spreadsheet rows paste by header names or by visible column order', () => {
  const cols = gridColumns('ilL-Attribute-CCT', schema);
  const byHeader = rowsFromMatrix([['Kelvin Value', 'CCT Name *', 'Unknown'], ['2700', '27K', 'x'], ['', '', '']], cols, cols, () => ({}));
  assert.ok(byHeader.header);
  assert.equal(byHeader.rows.length, 1);
  assert.equal(byHeader.rows[0].cct_name, '27K');
  assert.equal(byHeader.rows[0].kelvin, 2700);
  const byOrder = rowsFromMatrix([['30K', 'extra']], cols, cols.slice(0, 1), () => ({ is_active: 1 }));
  assert.equal(byOrder.header, false);
  assert.deepEqual(byOrder.rows, [{ is_active: 1, cct_name: '30K' }]);
});

test('fill down, clear and row operations return new rows', () => {
  const cols = [column('Data', { key: 'a' }), column('Table', { key: 't' })];
  const rows = [{ a: '1', t: [{ x: 1 }] }, { a: '2' }, { a: '3' }];
  const filled = fillDown(rows, [0, 1, 2], cols, { top: 0, bottom: 2, left: 0, right: 1 });
  assert.deepEqual(filled.rows.map(row => row.a), ['1', '1', '1']);
  assert.notEqual(filled.rows[1].t, rows[0].t, 'child rows are copied, not shared');
  assert.deepEqual(fillDown(rows, [0, 1, 2], cols, { top: 1, bottom: 1, left: 0, right: 0 }).rows[1].a, '1');
  assert.equal(fillDown(rows, [0, 1, 2], cols, { top: 0, bottom: 0, left: 0, right: 0 }).written, 0);
  assert.deepEqual(clearCells(rows, [0, 1, 2], cols, { top: 0, bottom: 0, left: 0, right: 1 }).rows[0], {});
  const duplicated = duplicateRows(rows, [0, 1], row => ({ ...row, copy: true }));
  assert.deepEqual(duplicated.rows.map(row => row.a), ['1', '2', '1', '2', '3']);
  assert.deepEqual(duplicated.inserted, [2, 3]);
  assert.deepEqual(moveRows(['a', 'b', 'c', 'd'], [1, 2], -1), { rows: ['b', 'c', 'a', 'd'], indexes: [0, 1] });
  assert.deepEqual(moveRows(['a', 'b', 'c', 'd'], [0, 2], -1), { rows: ['a', 'c', 'b', 'd'], indexes: [0, 1] });
  assert.deepEqual(moveRows(['a', 'b', 'c'], [1, 2], 1), { rows: ['a', 'b', 'c'], indexes: [1, 2] });
  assert.deepEqual(removeRows(['a', 'b', 'c'], [0, 2]), ['b']);
});

test('validation findings mark cells, child-table cells and rows', () => {
  const catalog = structuredClone(examples.driver);
  const template = catalog.records['ilL-Driver-Template'][0];
  template.variants[0].driver_spec = 'MISSING-SPEC';
    template.base_price_msrp = 'abc';
  catalog.records['ilL-Driver-Template'].push(structuredClone(template));
  const issues = catalogIssues(catalog, schema);
  const index = issueIndex(issues, unresolvedLinks(catalog, schema), catalog, schema);
  assert.ok(index.cells.get('ilL-Driver-Template[0].variants[0].driver_spec').some(text => text.includes('MISSING-SPEC')));
  assert.ok(index.cells.get('ilL-Driver-Template[1].variants[0].driver_spec'), 'every source of an unresolved link is marked');
  assert.ok(index.under.has('ilL-Driver-Template[0].variants'));
  assert.ok(index.rows.get('ilL-Driver-Template[0]').some(text => text.startsWith('variants[0].driver_spec:')));
  assert.ok(index.rows.get('ilL-Driver-Template[0].variants[0]').some(text => text.startsWith('driver_spec:')));
  assert.ok(index.rows.get('ilL-Driver-Template[1]').some(text => text.includes('duplicate record')));
  assert.ok(index.cells.get('ilL-Driver-Template[0].base_price_msrp').some(text => text.includes('finite number')));
});
