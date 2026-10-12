// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import type { DesignApi, EligibleSupply } from '../design/api';
import type { DraftStore } from '../design/drafts';
import { createDesignStore, type DesignStore } from '../design/store';
import { addCabinet, addCircuit, distanceDefaults } from '@ill/engine/site';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { addSupply, catalogMap, type PowerContext } from '@ill/engine/power';
import { openFixture } from './fixture';
import { newDesign, type OpenDesign } from './open';
import { Shell } from './Shell';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
const withScheduleSupplies = openFixture({ catalog_hash: 'a'.repeat(64) });
// Most tests start from a schedule with no power supply lines of its own (H1 is A1's supply line).
const open = { ...withScheduleSupplies, lines: withScheduleSupplies.lines.filter((line) => line.key !== 'h1acc') };
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

async function render(value: OpenDesign = open) {
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
const ctx = (): PowerContext => ({
  catalog: catalogMap(catalogPayload.items.map((item) => CatalogItemSchema.parse(item))),
  lines: open.lines,
  builds: open.builds,
});
const run = (key: string) => design().runs.find((item) => item.key === key)!;

describe('Power step', () => {
  it('picks a supply by fit from the eligible list, with no prices', async () => {
    expect(el.querySelector('main h2')?.textContent).toBe('Power');
    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
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
    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
    const output = byTest('output-PS-1-OUT1')!;
    expect(output.textContent).toContain('PS-1/OUT1 would carry 26.4 W of its 24 W usable');
    await click(button('Assign here', output));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('PS-1/OUT1 would carry 26.4 W of its 24 W usable');
    expect(run('a1linear:1:1').assignment).toBeUndefined();

    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
    await click(field('Select TEST-TN-24-30K-WET.1'));
    await click(button('Assign here', byTest('output-PS-1-OUT2')!));
    expect(run('b1tape:1:1').assignment).toEqual({ equipmentId: 'PS-1', port: 'OUT2' });
    expect(byTest('assigned-count')?.textContent).toContain('1 of');
    expect(byTest('output-PS-1-OUT2')?.textContent).toContain('TEST-TN-24-30K-WET.1 · 21.6 W');
    await click(field('Unassign TEST-TN-24-30K-WET.1'));
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
    await click(field('Select TEST-TN-24-30K-WET.1'));
    await choose('Selected zone', 'zone-1');
    expect(run('b1tape:1:1').zoneId).toBe('zone-1');
    expect(byTest('review-hints')?.textContent).toContain('Phase-cut dimming');
    await click(button('Remove', byTest('zone-zone-1')!));
    expect(run('b1tape:1:1').zoneId).toBeUndefined();
  });

  it('feeds line-voltage fixtures from a panel circuit', async () => {
    store.getState().edit((draft) => {
      addCircuit(draft);
    });
    await flush();
    const circuit = byTest('circuit-CKT-1')!;
    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
    expect(circuit.textContent).toContain('TEST-FX-LINEAR-30K-12FT.1 is low voltage; put it on a supply output');
    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
    await click(field('Select DL-4.1–6 (6 runs)'));
    await click(button('Assign here', byTest('circuit-CKT-1')!));
    expect(run('e1other:1:1').assignment).toEqual({ equipmentId: design().project.sources[0]!.id, port: 'LINE' });
    expect(byTest('circuit-CKT-1')?.textContent).toContain('DL-4.1–6 (6 runs) · 72 W');
    await click(field('Unassign DL-4.1–6 (6 runs)'));
    expect(run('e1other:1:1').assignment).toBeUndefined();
  });

  it('starts from the supplies on the schedule, assigns runs to them and warns what is left', async () => {
    act(() => root.unmount());
    store = createDesignStore();
    store.getState().load('SCH-TEST', newDesign(withScheduleSupplies).design, null);
    store.getState().acceptTerms();
    await render(withScheduleSupplies);
    // H1 lists two 96 W supplies for A1: both come in, in A1's space, with A1's runs on them.
    expect(design().project.equipment.map((item) => [item.tag, item.scheduleLine])).toEqual([
      ['PS-1', 'h1acc'],
      ['PS-2', 'h1acc'],
    ]);
    expect(byTest('supply-PS-1')?.textContent).toContain('On the schedule · line H1');
    expect(button('Remove PS-1')).toBeUndefined();
    expect(button('Start from configurator supplies')).toBeUndefined();
    expect(run('a1linear:1:1').assignment).toEqual({ equipmentId: 'PS-1', port: 'OUT1' });
    expect(run('a1linear:2:1').assignment).toEqual({ equipmentId: 'PS-2', port: 'OUT1' });
    expect(byTest('schedule-supplies-drift')).toBeNull();
    expect(byTest('power-shortfall')?.textContent).toMatch(
      /runs need .* more power\. The 2 supplies on the fixture schedule cannot carry them\./,
    );
    // One undo takes the whole start back.
    await click(button('Undo'));
    expect(design().project.equipment).toEqual([]);
    await click(button('Redo'));
    expect(design().project.equipment).toHaveLength(2);

    // A supply added here is the design's own, so write-back adds it to the schedule.
    await click(field('Select TEST-SHEET-30K-6PC.1'));
    await click(button('Add supply', byTest('board-C-1')!));
    await flush();
    await click(button('Add Test 96 W supply'));
    expect(design().project.equipment[2]).toMatchObject({ tag: 'PS-3', catalogId: 'drv:TEST-PSU-96' });
    expect(design().project.equipment[2]?.scheduleLine).toBeUndefined();
    await click(button('Auto-assign runs'));
    expect(run('c1sheet:1:1').assignment?.equipmentId).toBe('PS-3');
  });

  it('offers the schedule’s supplies again when the schedule lists more', async () => {
    act(() => root.unmount());
    store = createDesignStore();
    store.getState().load('SCH-TEST', newDesign(withScheduleSupplies).design, null);
    store.getState().acceptTerms();
    await render(withScheduleSupplies);
    act(() => root.unmount());
    const more = {
      ...withScheduleSupplies,
      lines: withScheduleSupplies.lines.map((line) => (line.key === 'h1acc' ? { ...line, qty: 3 } : line)),
    };
    await render(more);
    expect(byTest('schedule-supplies-drift')?.textContent).toContain(
      'The fixture schedule lists 1 power supply not in this design yet.',
    );
    await click(button('Use the schedule’s supplies'));
    expect(design().project.equipment.filter((item) => item.scheduleLine === 'h1acc')).toHaveLength(3);
    expect(byTest('schedule-supplies-drift')).toBeNull();
  });

  it('brings the schedule’s controls in, powers them beside the supplies and lists what they carry', async () => {
    act(() => root.unmount());
    const h1 = withScheduleSupplies.lines.find((line) => line.key === 'h1acc')!;
    const withControls = {
      ...withScheduleSupplies,
      lines: [
        ...withScheduleSupplies.lines,
        { ...h1, key: 'k1dec', lineKey: 'k1dec', lineId: 'K1', idx: 11, qty: 1, accessoryItem: 'TEST-DEC-4', powerSupplyForLine: null },
        { ...h1, key: 'l1conv', lineKey: 'l1conv', lineId: 'L1', idx: 12, qty: 1, accessoryItem: 'TEST-CONV-4', powerSupplyForLine: null },
      ],
    };
    store = createDesignStore();
    store.getState().load('SCH-TEST', newDesign(withControls).design, null);
    store.getState().acceptTerms();
    await render(withControls);
    expect(design().project.equipment.map((item) => [item.tag, item.scheduleLine, item.fedFrom])).toEqual([
      ['PS-1', 'h1acc', { ref: 'unassigned' }],
      ['PS-2', 'h1acc', { ref: 'unassigned' }],
      ['DEC-1', 'k1dec', { ref: 'PS-1', port: 'OUT1' }],
      ['CTL-1', 'l1conv', { ref: 'PS-1', port: 'OUT1' }],
    ]);
    expect(byTest('control-DEC-1')?.textContent).toContain('On the schedule · line K1');
    expect(byTest('control-DEC-1')?.textContent).toContain('DMX decoder');
    expect(button('Remove DEC-1')).toBeUndefined();
    expect(byTest('powers-PS-1-OUT1')?.textContent).toBe('Powers DEC-1, CTL-1');
    expect(byTest('cabinet-load-C-1')?.textContent).toContain('2 supplies · 2 controls');

    // A DMX zone's run goes on a decoder channel.
    await choose('Add zone', 'DMX512');
    await click(field('Unassign TEST-TN-24-30K-WET.1'));
    await click(field('Select TEST-TN-24-30K-WET.1'));
    await choose('Selected zone', 'zone-1');
    await click(button('Assign here', byTest('channels-DEC-1')!));
    expect(run('b1tape:1:1').assignment).toEqual({ equipmentId: 'DEC-1', port: 'CH1' });
    expect(byTest('channels-DEC-1')?.textContent).toContain('free CH2, CH3, CH4');
    expect(byTest('channels-DEC-1')?.textContent).toContain('CH1 · TEST-TN-24-30K-WET.1 · 21.6 W');

    // A 0-10V zone is dimmed by the converter's output; the converter takes DMX in.
    await choose('Zone 1 method', '0-10V');
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('Zone 1 dims by 0-10V; DEC-1 dims by DMX');
    await choose('Add zone', '0-10V');
    await choose('Zone 2 control', 'CTL-1::Out 1');
    expect(design().zones[1]?.control).toEqual({ equipmentId: 'CTL-1', port: 'Out 1' });
    expect(byTest('dims-CTL-1')?.textContent).toBe('Dims Zone 2 (Out 1)');
    await choose('DEC-1 power', '');
    expect(design().project.equipment[2]?.fedFrom).toEqual({ ref: 'unassigned' });
  });

  it('adds a control from the catalog and edits its DMX address', async () => {
    store.getState().edit((draft) => {
      addSupply(draft, ctx(), 'cab-1', 'drv:TEST-PSU-96');
    });
    await flush();
    await choose('Add a control to C-1', 'ctl:TEST-DEC-4');
    expect(design().project.equipment[1]).toMatchObject({
      tag: 'DEC-1',
      fedFrom: { ref: 'PS-1', port: 'OUT1' },
      dmx: { universe: 1, startAddress: 'auto' },
    });
    const start = field<HTMLInputElement>('DEC-1 start address');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(start, '9');
      start.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => start.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    expect(design().project.equipment[1]?.dmx?.startAddress).toBe(9);
    await click(field('Select TEST-FX-LINEAR-30K-12FT.1'));
    await click(button('Remove DEC-1'));
    expect(design().project.equipment.map((item) => item.tag)).toEqual(['PS-1']);
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
