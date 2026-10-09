import { test, expect } from '@playwright/test';

test('adds and edits a separate 0-10 V downlight cable with the control link form', async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.goto('/#/tables');
  await page.getByRole('button', { name: 'Load complete example', exact: true }).click();
  await page.getByRole('tab', { name: /Equipment/ }).click();
  await page.getByRole('button', { name: 'Add row', exact: true }).click();
  const equipment = page.locator('[role="row"][row-id]').last();
  await equipment.locator('[col-id="catalogId"]').dblclick();
  await page.getByRole('textbox', { name: 'Search choices' }).fill('EX-DMX-010-CONVERTER');
  await page.getByRole('option', { name: /EX-DMX-010-CONVERTER/ }).click();
  await equipment.locator('[col-id="fedFrom"]').dblclick();
  await page.getByRole('textbox', { name: 'Search choices' }).fill('PS-3 / OUT1');
  await page.getByRole('option', { name: /PS-3 \/ OUT1/ }).click();
  await page.getByRole('tab', { name: /Control Links/ }).click();
  await page.getByRole('button', { name: 'Add 0–10 V link', exact: true }).click();
  const form = page.getByRole('region', { name: 'Control link form' });
  await expect(form.getByRole('combobox', { name: 'Signal protocol' })).toHaveValue('0-10V');
  await expect(form.getByRole('button', { name: 'Add control cable' })).toBeDisabled();
  await form.getByRole('combobox', { name: 'Source device / output' }).selectOption('PS-4::DIM1');
  await expect(form.getByRole('combobox', { name: 'Receiving device / input' })).toContainText(
    'D1 / DIM IN · 0-10V · Gallery',
  );
  await form.getByRole('combobox', { name: 'Receiving device / input' }).selectOption('load-5');
  await form.getByRole('spinbutton', { name: 'Cable length (ft)' }).fill('37');
  await form.getByRole('combobox', { name: 'Cable environment' }).selectOption('plenum');
  await form.getByRole('button', { name: 'Add control cable' }).click();
  await expect(form).toHaveCount(0);
  const row = page.locator('[role="row"][row-id]').first();
  await expect(row.locator('[col-id="protocol"]')).toHaveText('0-10V');
  await expect(row.locator('[col-id="to"]')).toHaveText('D1 · Gallery');
  await expect(row.locator('[col-id="lengthFt"]')).toHaveText('37');
  await row.locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: 'Edit control link', exact: true }).click();
  await expect(form.getByRole('combobox', { name: 'Source device / output' })).toHaveValue(
    'PS-4::DIM1',
  );
  await form.getByRole('spinbutton', { name: 'Cable length (ft)' }).fill('42');
  await form.getByRole('button', { name: 'Save control link', exact: true }).click();
  await expect(row.locator('[col-id="lengthFt"]')).toHaveText('42');
  await page.getByRole('link', { name: /Drawing/ }).click();
  await expect(page.getByRole('status').filter({ hasText: /sheets ·/ })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator('.drawing-paper')).toContainText('0-10V');
});
