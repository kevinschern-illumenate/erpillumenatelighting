// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import type { DesignApi, EligibleSupply } from '../design/api';
import type { DraftStore } from '../design/drafts';
import { createDesignStore, type DesignStore } from '../design/store';
import { addCabinet, distanceDefaults } from '@ill/engine/site';
import { openFixture } from './fixture';
import { newDesign } from './open';
import { Shell } from './Shell';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
const open = openFixture({ catalog_hash: 'a'.repeat(64) });
const drafts = { get: vi.fn(), put: vi.fn(), remove: vi.fn(), close: vi.fn() } as unknown as DraftStore;
const eligible: EligibleSupply[] = [
  { catalog_id: 'drv:TEST-PSU-96', item_code: 'TEST-PSU-96', rank: 2, location_rating: 'Dry' },
  { catalog_id: 'drv:TEST-PSU-60', item_code: 'TEST-PSU-60', rank: 1, location_rating: 'Dry' },
];
let api: DesignApi;

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function render(value = open) {
  root = createRoot(el);
  await act(async () => root.render(<Shell open={value} store={store} api={api} drafts={drafts} checks={[]} />));
  await click(step('Power'));
  await flush();
}

beforeEach(async () => {
  el = document.createElement('div');
  document.body.append(el);
  api = {
    getCatalog: vi.fn().mockResolvedValue(catalogPayload),
    eligibleSupplies: vi.fn().mockResolvedValue(eligible),
  } as unknown as DesignApi;
  store = createDesignStore();
  const design = newDesign(open).design;
  addCabinet(design, 'space-kitchen', distanceDefaults({}));
  store.getState().load('SCH-TEST', design, null);
  store.getState().acceptTerms();
  store.temporal.getState().clear();
  await render();
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

const button = (name: string, scope: ParentNode = el) =>
  [...scope.querySelectorAll('button')].find((node) => node.textContent?.trim() === name) as
    HTMLButtonElement | undefined;
const step = (name: string) =>
  [...el.querySelectorAll<HTMLButtonElement>('nav button')].find((node) => node.textContent?.endsWith(name));
const field = <T extends HTMLElement>(label: string) => el.querySelector<T>(`[aria-label="${label}"]`)!;
const byTest = (id: string) => el.querySelector<HTMLElement>(`[data-testid="${id}"]`);
async function click(node: HTMLElement | undefined | null) {
  if (!node) throw new Error('missing control');
  await act(async () => node.click());
}
async function choose(label: string, value: string) {
  const select = field<HTMLSelectElement>(label);
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
const design = () => store.getState().design!;
const run = (key: string) => design().runs.find((item) => item.key === key)!;

describe('Power step', () => {
  it('picks a supply by fit from the eligible list, with no prices', async () => {
    expect(el.querySelector('main h2')?.textContent).toBe('Power');
    await click(field('Select A1-1.1'));
    await click(button('Add supply', byTest('board-C-1')!));
    await flush();
    expect(api.eligibleSupplies).toHaveBeenCalledWith({
      schedule: 'SCH-TEST',
      runKeys: ['a1linear:1:1'],
      locationRating: 'Dry',
    });
    const choices = [...el.querySelectorAll('[data-testid^="choice-"]')].map((node) =>
      node.getAttribute('data-testid'),
    );
    // 26.4 W fits one 96 W supply (76.8 W usable) but not a 24 W output of the 60 W supply.
    expect(choices).toEqual(['choice-drv:TEST-PSU-96', 'choice-drv:TEST-PSU-60']);
    expect(byTest('choice-drv:TEST-PSU-60')?.textContent).toContain('A run is larger than its outputs');
    expect(el.querySelector('[aria-label="Add a supply to C-1"]')?.textContent).not.toMatch(/\$|price|cost/i);
    await click(button('Add Test 96 W supply'));
    expect(design().project.equipment).toMatchObject([
      { tag: 'PS-1', catalogId: 'drv:TEST-PSU-96', enclosure: 'cab-1' },
    ]);
  });

  it('assigns selected runs from the keyboard and shows the refusal reason', async () => {
    store.getState().edit((draft) => {
      draft.project.equipment.push({
        id: 'PS-1',
        tag: 'PS-1',
        catalogId: 'drv:TEST-PSU-60',
        category: 'psu',
        qty: 1,
        location: 'Kitchen cabinet',
        enclosure: 'cab-1',
        fedFrom: { ref: 'unassigned' },
        feedLengthFt: 10,
        env: 'dry-concealed',
      });
    });
    await flush();
    await click(field('Select A1-1.1'));
    const output = byTest('output-PS-1-OUT1')!;
    expect(output.textContent).toContain('PS-1/OUT1 would carry 26.4 W of its 24 W usable');
    await click(button('Assign here', output));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('PS-1/OUT1 would carry 26.4 W of its 24 W usable');
    expect(run('a1linear:1:1').assignment).toBeUndefined();

    await click(field('Select A1-1.1'));
    await click(field('Select B1-1.1'));
    await click(button('Assign here', byTest('output-PS-1-OUT2')!));
    expect(run('b1tape:1:1').assignment).toEqual({ equipmentId: 'PS-1', port: 'OUT2' });
    expect(byTest('assigned-count')?.textContent).toContain('1 of');
    expect(byTest('output-PS-1-OUT2')?.textContent).toContain('B1-1.1 · 21.6 W');
    await click(field('Unassign B1-1.1'));
    expect(run('b1tape:1:1').assignment).toBeUndefined();
    await click(button('Undo'));
    expect(run('b1tape:1:1').assignment).toEqual({ equipmentId: 'PS-1', port: 'OUT2' });
  });

  it('starts from the configurator supplies', async () => {
    await click(button('Start from configurator supplies'));
    expect(design().project.equipment).toHaveLength(4);
    expect(byTest('supply-PS-1')?.textContent).toContain('From configurator');
    expect(run('d1group:1:2').assignment?.port).toBe('OUT2');
    expect(button('Start from configurator supplies')).toBeUndefined();
  });

  it('adds zones, puts runs in them and shows the review hint for phase-cut', async () => {
    await choose('Add zone', 'phase-forward');
    expect(design().zones).toMatchObject([{ id: 'zone-1', name: 'Zone 1', method: 'phase-forward' }]);
    await click(field('Select B1-1.1'));
    await choose('Selected zone', 'zone-1');
    expect(run('b1tape:1:1').zoneId).toBe('zone-1');
    expect(byTest('review-hints')?.textContent).toContain('Phase-cut dimming');
    await click(button('Remove', byTest('zone-zone-1')!));
    expect(run('b1tape:1:1').zoneId).toBeUndefined();
  });

  it('says when the catalog cannot be loaded', async () => {
    act(() => root.unmount());
    api = {
      getCatalog: vi.fn().mockRejectedValue(new Error('offline')),
      eligibleSupplies: vi.fn(),
    } as unknown as DesignApi;
    await render(openFixture({ catalog_hash: 'b'.repeat(64) }));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('The ilLumenate catalog could not be loaded.');
  });
});
