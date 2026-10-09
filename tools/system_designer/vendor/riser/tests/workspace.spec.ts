import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/#/project');
  await expect(page.getByRole('status')).toHaveText('Saved locally');
});

test('edits, undo, redo, keyboard shortcuts, and reload persistence', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const name = page.getByLabel('Project name', { exact: true });
  await name.fill('Gallery riser');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(name).toHaveValue('Untitled project');
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(name).toHaveValue('Gallery riser');
  await name.press('Control+z');
  await expect(name).toHaveValue('Untitled project');
  await name.press('Control+Shift+z');
  await expect(name).toHaveValue('Gallery riser');
  await page.getByLabel('Client', { exact: true }).fill('Studio 206');
  await page.getByLabel('PSU loading limit').fill('75');
  await page.getByLabel('Brand', { exact: true }).click();
  await page.getByRole('option', { name: '206 Lighting' }).click();
  await page.getByRole('button', { name: 'Save now' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved locally');
  await page.reload();
  await expect(name).toHaveValue('Gallery riser');
  await expect(page.getByLabel('Client', { exact: true })).toHaveValue('Studio 206');
  await expect(page.getByLabel('PSU loading limit')).toHaveValue('75');
  await expect(page.getByLabel('Brand', { exact: true })).toContainText('206 Lighting');
  await expect(page.getByRole('button', { name: 'Undo', exact: true })).toBeDisabled();
  expect(errors).toEqual([]);
});

test('project switches save pending changes and isolate undo history', async ({ page }) => {
  await page.getByLabel('Project name', { exact: true }).fill('Project Alpha');
  await page.getByLabel('Project scratchpad').fill('Keep this note');
  await page.getByRole('button', { name: 'New project' }).click();
  await expect(page.getByLabel('Project name', { exact: true })).toHaveValue('Untitled project');
  await page.getByLabel('Project name', { exact: true }).fill('Project Beta');
  await page.getByRole('button', { name: 'Project Alpha', exact: true }).click();
  await expect(page.getByLabel('Project scratchpad')).toHaveValue('Keep this note');
  await expect(page.getByRole('button', { name: 'Undo', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Project Beta', exact: true }).click();
  await expect(page.getByLabel('Project name', { exact: true })).toHaveValue('Project Beta');
  await expect(page.getByLabel('Project scratchpad')).toHaveValue('');
});

test('all implemented routes load and theme persists', async ({ page }) => {
  for (const route of ['Tables', 'Review', 'Drawing', 'Export']) {
    await page.getByRole('link', { name: new RegExp(route) }).click();
    await expect(page.getByRole('heading', { name: route, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByText('PLANNED · PHASE', { exact: false })).toHaveCount(0);
  }
  await page.getByRole('link', { name: /Libraries/ }).click();
  await expect(page.getByRole('heading', { name: 'Product library' })).toBeVisible();
  await page.getByRole('tab', { name: 'ERPNext Sync' }).click();
  await expect(page.getByRole('button', { name: 'Preview pull' })).toBeVisible();
  await page.getByRole('button', { name: 'Use dark mode' }).click();
  await expect(page.locator('html')).toHaveClass('dark');
  await page.reload();
  await expect(page.locator('html')).toHaveClass('dark');
  await page.getByRole('button', { name: 'Use light mode' }).click();
  await expect(page.locator('html')).not.toHaveClass('dark');
});

test('desktop and narrow layouts do not overflow', async ({ page }) => {
  for (const width of [1440, 900, 390]) {
    await page.setViewportSize({ width, height: 950 });
    await expect(page.getByLabel('Project name', { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/phase0-${width}.png`,
      fullPage: true,
      animations: 'disabled',
    });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'Use dark mode' }).click();
  await page.screenshot({
    path: 'test-results/phase0-dark.png',
    fullPage: true,
    animations: 'disabled',
  });
});
