// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import { parseCatalog } from '../design/catalog';
import { createDesignStore, type DesignStore } from '../design/store';
import { openFixture } from '../shell/fixture';
import { newDesign } from '../shell/open';
import EngineeringTab from './EngineeringTab';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
const catalog = { state: 'ready', catalog: parseCatalog('d'.repeat(64), catalogPayload) } as const;

beforeEach(() => {
  el = document.createElement('div');
  document.body.append(el);
  store = createDesignStore();
  store.getState().load('SCH-TEST', newDesign(openFixture()).design, null);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

async function render(staff = false, readOnly = false) {
  root = createRoot(el);
  await act(async () =>
    root.render(
      <EngineeringTab
        store={store}
        engine={{ state: 'waiting' }}
        catalog={catalog}
        readOnly={readOnly}
        staff={staff}
      />,
    ),
  );
}
const button = (name: string) =>
  [...el.querySelectorAll('button')].find((node) => node.textContent?.trim() === name) as HTMLButtonElement;
const setting = (name: string) =>
  [...el.querySelectorAll('label')]
    .find((node) => node.querySelector('span')?.textContent === name)!
    .querySelector<HTMLInputElement & HTMLSelectElement>('input, select')!;
async function click(node: HTMLElement) {
  await act(async () => node.click());
}

describe('Engineering tab', () => {
  it('adds equipment and circuits to the design through the store', async () => {
    await render();
    await click(button('Add circuit'));
    expect(store.getState().design!.project.sources.map((item) => item.tag)).toEqual(['CKT-1']);
    await click(button('Equipment'));
    await click(button('Add equipment'));
    expect(store.getState().design!.project.equipment.map((item) => item.tag)).toEqual(['PS-1']);
    expect(store.getState().dirty).toBe(true);
    store.temporal.getState().undo();
    expect(store.getState().design!.project.equipment).toEqual([]);
    await click(button('Loads'));
    expect(button('Add equipment')).toBeUndefined();
    expect(el.querySelector('[data-testid="grid-loads"]')).not.toBeNull();
  });

  it('edits settings, with the safety margins left to ilLumenate staff', async () => {
    await render();
    await click(button('Settings'));
    expect(setting('Supply operating target (%)').disabled).toBe(true);
    const edition = setting('NEC edition');
    await act(async () => {
      edition.value = '2026';
      edition.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(store.getState().design!.project.settings.necEdition).toBe('2026');
    act(() => root.unmount());
    await render(true);
    await click(button('Settings'));
    const derate = setting('Supply operating target (%)');
    expect(derate.disabled).toBe(false);
    await act(async () => {
      derate.focus();
      derate.value = '85';
      derate.blur();
    });
    expect(store.getState().design!.project.settings.psuDeratePct).toBe(85);
  });

  it('shows the tables without edit controls on a read-only design', async () => {
    await render(true, true);
    expect(button('Add circuit')).toBeUndefined();
    await click(button('Settings'));
    expect(setting('NEC edition').disabled).toBe(true);
  });
});
