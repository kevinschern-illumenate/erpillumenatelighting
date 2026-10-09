// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import type { DesignApi } from '../design/api';
import type { DraftStore } from '../design/drafts';
import { createDesignStore, type DesignStore } from '../design/store';
import { addCabinet, distanceDefaults } from '@ill/engine/site';
import { openFixture } from './fixture';
import { newDesign, type OpenDesign } from './open';
import { Shell } from './Shell';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
const open = openFixture({ catalog_hash: 'd'.repeat(64), user: 'dealer@example.com' });
const drafts = { get: vi.fn(), put: vi.fn(), remove: vi.fn(), close: vi.fn() } as unknown as DraftStore;
let api: DesignApi;

// The checks run after a short pause on each edit.
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 200));
  });
}

async function render(value: OpenDesign = open) {
  root = createRoot(el);
  await act(async () => root.render(<Shell open={value} store={store} api={api} drafts={drafts} checks={[]} />));
  await click(step('Check'));
  await settle();
}

beforeEach(() => {
  el = document.createElement('div');
  document.body.append(el);
  api = { getCatalog: vi.fn().mockResolvedValue(catalogPayload) } as unknown as DesignApi;
  store = createDesignStore();
  const design = newDesign(open).design;
  addCabinet(design, 'space-kitchen', distanceDefaults({}));
  design.project.equipment.push({
    id: 'PS-1',
    tag: 'PS-1',
    catalogId: 'drv:TEST-PSU-96',
    category: 'psu',
    qty: 1,
    location: 'Kitchen cabinet',
    enclosure: 'cab-1',
    fedFrom: { ref: 'unassigned' },
    feedLengthFt: 10,
    env: 'dry-concealed',
  });
  design.runs.find((run) => run.key === 'a1linear:1:1')!.assignment = { equipmentId: 'PS-1', port: 'OUT1' };
  store.getState().load('SCH-TEST', design, null);
  store.getState().acceptTerms();
  store.temporal.getState().clear();
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
async function type(label: string, value: string, commit = true) {
  const input = field<HTMLInputElement>(label);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  if (commit) await act(async () => input.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
}
const design = () => store.getState().design!;

describe('Check step', () => {
  it('sizes the assigned run and lists the checks with their fixes', async () => {
    await render();
    expect(el.querySelector('main h2')?.textContent).toBe('Check');
    const row = byTest('result-a1linear:1:1')!;
    expect(row.textContent).toContain('A1-1.1');
    expect(row.textContent).toContain('18/2 CL3R');
    expect(row.textContent).toContain('15 ft');
    expect(row.textContent).toContain('1.09% of 3%');
    const circuit = byTest('check-UNRESOLVED_REF-PS-1')!;
    expect(circuit.textContent).toContain('PS-1 is not on a panel circuit yet.');
    await click(button('Open Power', circuit));
    expect(el.querySelector('main h2')?.textContent).toBe('Power');
  });

  it('lets a dealer accept a warning with a reason and withdraw it', async () => {
    await render();
    const access = () => byTest('check-SUPPLY_NO_ACCESS-cab-1')!;
    expect(button('Override', access())).toBeUndefined();
    await click(button('Accept', access()));
    await click(button('Save reason', access()));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('Give a reason');
    await type('Reason for Cabinet C-1', 'Access through the attic', false);
    await click(button('Save reason', access()));
    expect(design().overrides).toMatchObject([
      { code: 'SUPPLY_NO_ACCESS', entityRef: 'cab-1', kind: 'acknowledge', by: 'dealer@example.com' },
    ]);
    await settle();
    expect(access().textContent).toContain('Accepted: Access through the attic');
    await click(button('Withdraw', access()));
    expect(design().overrides).toEqual([]);
  });

  it('tightens the voltage-drop target and refuses a looser one for dealers', async () => {
    await render();
    await type('Class 2 low voltage target', '2');
    expect(design().project.settings.vdTargetLowVoltagePct).toBe(2);
    await settle();
    expect(byTest('result-a1linear:1:1')?.textContent).toContain('of 2%');
    await type('Class 2 low voltage target', '4');
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('The target can be 3% or tighter');
    expect(design().project.settings.vdTargetLowVoltagePct).toBe(2);
    expect(field('Reason for a looser target')).toBeNull();
  });

  it('lets an Applications Engineer loosen a target with a reason', async () => {
    await render({ ...open, permissions: { ...open.permissions, can_review: true }, user: 'ae@illumenate.com' });
    await type('Reason for a looser target', 'Long landscape feed, owner accepts', false);
    await type('Class 2 low voltage target', '4');
    expect(design().overrides).toMatchObject([{ code: 'VD_TARGET_LOOSENED', kind: 'staff-override' }]);
    await settle();
    expect(byTest('check-VD_TARGET_LOOSENED-project')?.textContent).toContain('Long landscape feed');
  });

  it('returns a pinned wire to automatic selection', async () => {
    store.getState().edit((draft) => {
      draft.project.wireOverrides['power:load:a1linear:1:1'] = {
        wireTypeId: 'wire:TEST-WIRE-18-2',
        parallelSets: 1,
        parallelCommonConductors: 1,
      };
    });
    await render();
    expect(byTest('result-a1linear:1:1')?.textContent).toContain('(pinned)');
    expect(byTest('pinned-wires')?.textContent).toContain('A1-1.1: 18/2 CL3R');
    await click(button('Back to automatic'));
    expect(design().project.wireOverrides).toEqual({});
    expect(byTest('pinned-wires')).toBeNull();
  });

  it('says when the catalog cannot be loaded', async () => {
    api = { getCatalog: vi.fn().mockRejectedValue(new Error('offline')) } as unknown as DesignApi;
    await render(openFixture({ catalog_hash: 'e'.repeat(64) }));
    expect(el.querySelector('[role="status"]:not([data-testid])')?.textContent).toBe(
      'The ilLumenate catalog could not be loaded.',
    );
  });
});
