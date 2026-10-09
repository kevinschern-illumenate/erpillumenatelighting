import { test, expect } from '@playwright/test';

test('editing enclosure numbers regroups the equipment and persists the arrangement', async ({
  page,
}) => {
  await page.goto('/#/tables');
  await page.getByRole('button', { name: 'Load complete example', exact: true }).click();
  await page.getByRole('link', { name: /Drawing/ }).click();
  await expect(page.getByRole('status').filter({ hasText: /sheets ·/ })).toBeVisible();
  const controller = page.locator('.drawing-paper svg rect[data-entity="con-1"]').first();
  const initial = { x: await controller.getAttribute('x'), y: await controller.getAttribute('y') };
  await page.getByRole('link', { name: /Tables/ }).click();
  await page.getByRole('tab', { name: /Equipment/ }).click();
  for (const checkbox of await page.locator('[role="row"][row-id] input[type="checkbox"]').all())
    await checkbox.check();
  await page.getByRole('combobox', { name: 'Bulk field', exact: true }).selectOption('enclosure');
  await page.getByRole('textbox', { name: 'Bulk value', exact: true }).fill('Enclosure 1');
  await page.getByRole('button', { name: 'Apply to selected', exact: true }).click();
  await expect(page.locator('[role="row"][row-id] [col-id="enclosure"]')).toHaveText(
    Array(6).fill('Enclosure 1'),
  );
  await page.getByRole('link', { name: /Drawing/ }).click();
  await expect(page.getByRole('status').filter({ hasText: /sheets ·/ })).toBeVisible();
  const outlines = page.locator('.drawing-paper svg [data-layer="E-ANNO-ENCL"] > rect');
  await expect(outlines).toHaveCount(1);
  await expect(page.locator('.drawing-paper')).toContainText('Enclosure 1');
  const current = { x: await controller.getAttribute('x'), y: await controller.getAttribute('y') };
  expect(current).not.toEqual(initial);
  const box = await outlines.evaluate((r) => {
    const bounds = (r as SVGGraphicsElement).getBBox();
    return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  });
  for (const id of ['ps-1', 'ps-2', 'ps-3', 'dec-1', 'dec-2', 'con-1']) {
    const node = await page
      .locator(`.drawing-paper svg rect[data-entity="${id}"]`)
      .first()
      .evaluate((r) => {
        const b = (r as SVGGraphicsElement).getBBox();
        return { x: b.x, y: b.y, width: b.width, height: b.height };
      });
    expect(node.x).toBeGreaterThan(box.x);
    expect(node.y).toBeGreaterThan(box.y);
    expect(node.x + node.width).toBeLessThan(box.x + box.width);
    expect(node.y + node.height).toBeLessThan(box.y + box.height);
  }
  await page.screenshot({ path: 'test-results/enclosure-group.png', fullPage: true });
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await page.reload();
  await expect(outlines).toHaveCount(1);
  await expect(page.locator('.drawing-paper')).toContainText('Enclosure 1');
});

test('loads can join an enclosure and same-sheet wires stay directly connected', async ({
  page,
}) => {
  await page.goto('/#/tables');
  await page.getByRole('button', { name: 'Load complete example', exact: true }).click();
  await page.getByRole('tab', { name: /Loads/ }).click();
  await page.locator('[role="row"][row-id="load-1"] input[type="checkbox"]').check();
  await page.getByRole('combobox', { name: 'Bulk field', exact: true }).selectOption('enclosure');
  await page.getByRole('textbox', { name: 'Bulk value', exact: true }).fill('Cabinet A');
  await page.getByRole('button', { name: 'Apply to selected', exact: true }).click();
  await expect(page.locator('[role="row"][row-id="load-1"] [col-id="enclosure"]')).toHaveText(
    'Cabinet A',
  );
  await page.getByRole('link', { name: /Drawing/ }).click();
  await page.getByRole('checkbox', { name: 'Show schedules', exact: true }).uncheck();
  await expect(page.getByRole('status').filter({ hasText: /sheets ·/ })).toBeVisible();
  await expect(page.locator('.drawing-paper')).not.toContainText('CONT.');
  const geometry = await page.locator('.drawing-paper svg').evaluate((svg) => {
    const b = (selector: string) => {
      const r = svg.querySelector(selector) as SVGGraphicsElement;
      const v = r.getBBox();
      return { x: v.x, y: v.y, width: v.width, height: v.height };
    };
    return {
      supply: b('rect[data-entity="ps-1"]'),
      decoder: b('rect[data-entity="dec-1"]'),
      load: b('rect[data-entity="load-1"]'),
      outlines: [...svg.querySelectorAll('[data-layer="E-ANNO-ENCL"] > rect')].map((r) => {
        const v = (r as SVGGraphicsElement).getBBox();
        return { x: v.x, y: v.y, width: v.width, height: v.height };
      }),
    };
  });
  expect(geometry.supply.x + geometry.supply.width).toBeLessThan(geometry.decoder.x);
  expect(geometry.decoder.x + geometry.decoder.width).toBeLessThan(geometry.load.x);
  expect(
    geometry.outlines.some(
      (b) =>
        geometry.load.x > b.x &&
        geometry.load.y > b.y &&
        geometry.load.x + geometry.load.width < b.x + b.width &&
        geometry.load.y + geometry.load.height < b.y + b.height,
    ),
  ).toBe(true);
  await page.getByRole('link', { name: /Tables/ }).click();
  await page.getByRole('tab', { name: /Loads/ }).click();
  await page.locator('[role="row"][row-id="load-1"] input[type="checkbox"]').check();
  await page.getByRole('combobox', { name: 'Bulk field', exact: true }).selectOption('enclosure');
  await page.getByRole('textbox', { name: 'Bulk value', exact: true }).fill('');
  await page.getByRole('button', { name: 'Apply to selected', exact: true }).click();
  await expect(page.locator('[role="row"][row-id="load-1"] [col-id="enclosure"]')).toHaveText('');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('tab', { name: /Loads/ }).click();
  await expect(page.locator('[role="row"][row-id="load-1"] [col-id="enclosure"]')).toHaveText('');
});
