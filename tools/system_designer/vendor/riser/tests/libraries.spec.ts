import { expect, test } from '@playwright/test';
import Papa from 'papaparse';

test.beforeEach(async ({ page }) => {
  await page.goto('/#/libraries');
  await expect(page.getByRole('heading', { name: 'Product library' })).toBeVisible();
});

test('imports incomplete products, preserves known data after reload, and requires missing specifications', async ({
  page,
}) => {
  const item = {
    id: 'pending-sheet',
    sku: 'TEST-SHEET',
    brand: 'Test',
    model: 'Sheet',
    category: 'fixture',
    description: 'Test whole sheet',
    isExample: false,
    specs: {
      kind: 'incomplete',
      intendedKind: 'fixture',
      available: {
        voltageClass: 'low',
        inputType: 'DC',
        inputV: 24,
        watts: 10,
      },
      missingFields: ['dimming', 'integralDriver'],
      notes: ['One quantity is one whole sheet.'],
    },
    sourceData: {
      fields: { item: 'TEST-SHEET', watts: '10.0' },
      children: { options: [{ name: '3000K' }] },
    },
    localOverrides: [],
  };
  await page.getByLabel('Import products CSV').setInputFiles({
    name: 'products.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      Papa.unparse([
        {
          ...item,
          specs: JSON.stringify(item.specs),
          sourceData: JSON.stringify(item.sourceData),
          localOverrides: '[]',
        },
      ]),
    ),
  });
  await expect(page.locator('.import-summary')).toContainText(
    '1 rows · 1 new · 0 updated · 0 unchanged · 0 errors',
  );
  await expect(page.locator('.import-preview')).toContainText(
    'Needs specifications: dimming, integralDriver',
  );
  await page.getByRole('button', { name: 'Commit import' }).click();
  await expect(page.getByText('1 rows imported.', { exact: true })).toBeVisible();
  await expect(page.getByText('Library saved', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('note')).toContainText('1 products need specifications');
  await page.getByRole('textbox', { name: 'Search products' }).fill('TEST-SHEET');
  await page.locator('[role="row"][row-id="pending-sheet"] input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Item JSON' })).toHaveCount(0);
  await expect(
    page.getByRole('spinbutton', { name: 'Power per fixture / whole sheet (W)', exact: true }),
  ).toHaveValue('10');
  await page.getByRole('button', { name: 'Save as complete', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Integral driver');
  await page.getByRole('combobox', { name: 'Integral driver', exact: true }).selectOption('false');
  await page.getByRole('checkbox', { name: 'PWM', exact: true }).check();
  await page.getByRole('button', { name: 'Save incomplete product', exact: true }).click();
  await expect(page.getByText('Library item saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await page.getByRole('button', { name: 'Save as complete', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Review the imported source notes');
  await page.getByRole('checkbox', { name: /I have checked these notes/ }).check();
  await page.getByRole('button', { name: 'Save as complete', exact: true }).click();
  await expect(page.locator('.library-item-editor')).toHaveCount(0);
  await expect(page.getByRole('note')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await page.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const saved = JSON.parse(await page.getByRole('textbox', { name: 'Item JSON' }).inputValue());
  expect(saved.specs.kind).toBe('fixture');
  expect(saved.specs.dimming).toEqual(['PWM']);
  expect(saved.specs.integralDriver).toBe(false);
  expect(saved.sourceData).toEqual(item.sourceData);
});

test('searches and edits catalog specifications, wires, and library undo', async ({ page }) => {
  await page.getByRole('textbox', { name: 'Search products' }).fill('tunable');
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(1);
  await page.locator('[role="row"][row-id="tape-tw"] input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await expect(
    page.getByRole('spinbutton', { name: 'Maximum power (W/ft)', exact: true }),
  ).toHaveValue('4.4');
  await expect(page.getByRole('combobox', { name: 'Power rating basis', exact: true })).toHaveValue(
    'max-operating',
  );
  await page.getByRole('textbox', { name: 'Brand', exact: true }).fill('Local test brand');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByText('Local test brand', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Local test brand', { exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: 'Wires', exact: true }).click();
  await page.getByRole('textbox', { name: 'Search wires' }).fill('wireless');
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(1);
});

test('configures an AC phase-dimming decoder while preserving the DC option', async ({ page }) => {
  await page.getByRole('textbox', { name: 'Search products' }).fill('EX-DECODER-4CH');
  await page.locator('[role="row"][row-id="decoder-4ch"] input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  const editor = page.locator('.library-item-editor');
  const power = editor.getByRole('combobox', { name: 'Power input and output', exact: true });
  await expect(power).toHaveValue('DC');
  await power.selectOption('AC');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor.getByRole('alert')).toContainText('AC output dimming method');
  await editor
    .getByRole('combobox', { name: 'AC output dimming method', exact: true })
    .selectOption('phase-reverse');
  await editor.getByRole('spinbutton', { name: 'Minimum input voltage (V)' }).fill('110');
  await editor.getByRole('spinbutton', { name: 'Maximum input voltage (V)' }).fill('130');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await editor.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const json = JSON.parse(await editor.getByRole('textbox', { name: 'Item JSON' }).inputValue());
  expect(json.specs).toMatchObject({ powerType: 'AC', outputDimming: 'phase-reverse' });
  await editor.getByRole('tab', { name: 'Form fields', exact: true }).click();
  await power.selectOption('DC');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
});

test('validates, saves and reloads code-table edits and restores the shipped seed', async ({
  page,
}) => {
  await page.getByRole('tab', { name: 'Code tables' }).click();
  const editor = page.getByRole('textbox', { name: 'Table JSON' });
  await expect(editor).toBeEnabled();
  const original = JSON.parse(await editor.inputValue());
  const save = page.getByRole('button', { name: 'Validate & save table' });
  await editor.fill('{broken');
  await save.click();
  await expect(page.getByRole('alert')).toContainText('Invalid JSON');
  await editor.fill(JSON.stringify({ ...original, units: 'bad' }));
  await save.click();
  await expect(page.getByRole('alert')).toContainText('units');
  await editor.fill(
    JSON.stringify({ ...original, source: { ...original.source, edition: '2026' } }),
  );
  await save.click();
  await expect(page.getByRole('alert')).toContainText('code edition');
  const edited = structuredClone(original);
  edited.rows[0].stranded = 8.01;
  edited.comment = 'Reviewed local test override';
  await editor.fill(JSON.stringify(edited));
  await save.click();
  await expect(page.getByText('Code table saved locally.')).toBeVisible();
  await page.reload();
  await page.getByRole('tab', { name: 'Code tables' }).click();
  await expect(editor).toHaveValue(/Reviewed local test override/);
  expect(JSON.parse(await editor.inputValue()).rows[0].stranded).toBe(8.01);
  await page.getByRole('button', { name: 'Restore seed' }).click();
  await expect(page.getByText('Restored the shipped seed table.')).toBeVisible();
  expect(JSON.parse(await editor.inputValue())).toEqual(original);
  await page.getByLabel('Select code table').click();
  await page.getByRole('option', { name: /Table 9/ }).click();
  await expect(page.getByText(/Table 9 values were not supplied/)).toBeVisible();
});

test('creates products with fields, preserves edits across modes and categories, and fits narrow screens', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'New item', exact: true }).click();
  const editor = page.locator('.library-item-editor');
  await editor.getByRole('textbox', { name: 'SKU / item code', exact: true }).fill('FORM-PSU');
  await editor
    .getByRole('textbox', { name: 'Model / product name', exact: true })
    .fill('New power supply');
  await editor
    .getByRole('textbox', { name: 'Description', exact: true })
    .fill('Manufacturer ratings pending');
  await expect(
    editor.getByRole('spinbutton', { name: 'Rated output power (W)', exact: true }),
  ).toHaveValue('');
  await editor.getByRole('spinbutton', { name: 'Efficiency (%)', exact: true }).fill('92');
  await editor.getByRole('spinbutton', { name: 'Rated output power (W)', exact: true }).fill('96');
  await editor.getByRole('button', { name: 'Add output', exact: true }).click();
  const output = editor.getByRole('group', { name: 'Output 1', exact: true });
  await output.getByRole('textbox', { name: 'Output name', exact: true }).fill('OUT-A');
  await output.getByRole('spinbutton', { name: 'Maximum power (W)', exact: true }).fill('96');
  await expect(output.getByRole('combobox', { name: 'Class 2 listed', exact: true })).toHaveValue(
    '',
  );
  await editor
    .getByRole('combobox', { name: 'Product category', exact: true })
    .selectOption('tape');
  await expect(
    editor.getByRole('spinbutton', { name: 'Maximum power (W/ft)', exact: true }),
  ).toHaveValue('');
  await editor.getByRole('combobox', { name: 'Product category', exact: true }).selectOption('psu');
  await expect(
    editor.getByRole('spinbutton', { name: 'Rated output power (W)', exact: true }),
  ).toHaveValue('96');
  await editor.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const json = editor.getByRole('textbox', { name: 'Item JSON', exact: true });
  const value = JSON.parse(await json.inputValue());
  expect(value.specs.available.efficiency).toBe(0.92);
  expect(value.specs.available.outputs).toEqual([{ name: 'OUT-A', maxW: 96 }]);
  await json.fill('{broken');
  await editor.getByRole('tab', { name: 'Form fields', exact: true }).click();
  await expect(editor.getByRole('alert')).toContainText('advanced JSON is invalid');
  await editor.getByRole('button', { name: 'Discard JSON edits', exact: true }).click();
  await json.fill(JSON.stringify({ ...value, model: 'Edited in JSON' }));
  await editor.getByRole('tab', { name: 'Form fields', exact: true }).click();
  await expect(
    editor.getByRole('textbox', { name: 'Model / product name', exact: true }),
  ).toHaveValue('Edited in JSON');
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await editor.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `test-results/library-form-${width}.png`, fullPage: true });
    await editor
      .locator('.library-form-section')
      .first()
      .screenshot({ path: `test-results/library-form-details-${width}.png` });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await editor.getByRole('button', { name: 'Save incomplete product', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByText('Library saved', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('textbox', { name: 'Search products', exact: true }).fill('FORM-PSU');
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(1);
  await expect(page.getByRole('note')).toContainText('1 products need specifications');
});

test('edits wire conductor rows and references without JSON', async ({ page }) => {
  await page.getByRole('tab', { name: 'Wires', exact: true }).click();
  await page.getByRole('textbox', { name: 'Search wires', exact: true }).fill('THHN/THWN-2 #14');
  await page.locator('[role="row"][row-id="thhn-14"] input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  const editor = page.locator('.library-item-editor');
  const conductor = editor.getByRole('group', { name: 'Conductor group 1', exact: true });
  await conductor.getByRole('spinbutton', { name: 'Conductor count', exact: true }).fill('3');
  await editor.locator('summary').filter({ hasText: 'Manufacturer references' }).click();
  await editor.getByRole('button', { name: 'Add reference', exact: true }).click();
  await editor
    .getByRole('textbox', { name: 'Manufacturer / part number', exact: true })
    .fill('Test manufacturer 123');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await editor.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const saved = JSON.parse(await editor.getByRole('textbox', { name: 'Item JSON' }).inputValue());
  expect(saved.conductors[0].count).toBe(3);
  expect(saved.conductors[1].count).toBe(1);
  expect(saved.manufacturerRefs).toEqual(['Test manufacturer 123']);
  expect(saved.manufacturerRefChecks).toEqual([
    { reference: 'Test manufacturer 123', verify: true },
  ]);
});

test('edits free-cutting tape in the form and JSON, persists it, and restores fixed-interval validation', async ({
  page,
}) => {
  const openTape = async () => {
    await page.getByRole('textbox', { name: 'Search products', exact: true }).fill('EX-TAPE-WHITE');
    await page.locator('[role="row"][row-id="tape-white"] input[type="checkbox"]').first().check();
    await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  };
  await openTape();
  const editor = page.locator('.library-item-editor');
  const free = editor.getByRole('combobox', { name: 'Free-cutting tape', exact: true });
  const interval = editor.getByRole('spinbutton', { name: 'Cut interval (in)', exact: true });
  await expect(free).toHaveValue('false');
  await expect(interval).toHaveValue('4');
  await free.selectOption('true');
  await expect(interval).toHaveCount(0);
  await expect(editor.getByText('Not applicable — this tape is free-cutting.')).toBeVisible();
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByText('Library saved', { exact: true })).toBeVisible();
  await page.reload();
  await openTape();
  await expect(free).toHaveValue('true');
  await editor.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const json = editor.getByRole('textbox', { name: 'Item JSON', exact: true });
  const saved = JSON.parse(await json.inputValue());
  expect(saved.specs.freeCutting).toBe(true);
  expect(saved.specs).not.toHaveProperty('cutIntervalIn');
  await editor.getByRole('tab', { name: 'Form fields', exact: true }).click();
  await free.selectOption('false');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor.getByRole('alert')).toContainText('Enter a positive cut interval');
  await interval.fill('2.5');
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await editor.getByRole('tab', { name: 'Advanced JSON', exact: true }).click();
  const fixed = JSON.parse(await json.inputValue());
  fixed.specs.freeCutting = true;
  delete fixed.specs.cutIntervalIn;
  await json.fill(JSON.stringify(fixed));
  await editor.getByRole('button', { name: 'Validate & save JSON', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByText('Library saved', { exact: true })).toBeVisible();
  await page.reload();
  await openTape();
  await expect(free).toHaveValue('true');
  await expect(interval).toHaveCount(0);
});

test('exposes all sheet standards, preview-only QA layer and draft general notes', async ({
  page,
}) => {
  await page.getByRole('tab', { name: 'Drawing standards' }).click();
  await expect(page.locator('.library-detail')).toHaveCount(4);
  await expect(page.locator('tbody tr')).toHaveCount(16);
  await expect(page.getByText('Preview only · NEVER EXPORTED')).toBeVisible();
  await page.getByRole('tab', { name: 'General notes' }).click();
  await expect(page.locator('.note-list article')).toHaveCount(12);
});

test('library previews fit desktop and mobile in both themes', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const name of ['Products', 'Code tables', 'Drawing standards', 'General notes']) {
      await page.getByRole('tab', { name, exact: true }).click();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      if (name === 'Products' || name === 'Code tables')
        await page.screenshot({
          path: `test-results/phase1-${name.replaceAll(' ', '-')}-${width}.png`,
          fullPage: true,
          animations: 'disabled',
        });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'Use dark mode' }).click();
  await page.getByRole('tab', { name: 'Drawing standards' }).click();
  await page.screenshot({
    path: 'test-results/phase1-standards-dark.png',
    fullPage: true,
    animations: 'disabled',
  });
});
