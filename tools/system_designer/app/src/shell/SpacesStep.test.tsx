// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DesignApi } from '../design/api';
import type { DraftStore } from '../design/drafts';
import { createDesignStore, type DesignStore } from '../design/store';
import { openFixture } from './fixture';
import { newDesign } from './open';
import { Shell } from './Shell';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
const open = openFixture({ settings: { ...openFixture().settings, default_distance_other_level_ft: 45 } });
const drafts = { get: vi.fn(), put: vi.fn(), remove: vi.fn(), close: vi.fn() } as unknown as DraftStore;

beforeEach(async () => {
  el = document.createElement('div');
  document.body.append(el);
  store = createDesignStore();
  store.getState().load('SCH-TEST', newDesign(open).design, null);
  store.getState().acceptTerms();
  store.temporal.getState().clear();
  root = createRoot(el);
  await act(async () =>
    root.render(<Shell open={open} store={store} api={{} as DesignApi} drafts={drafts} checks={[]} />),
  );
  await click(step('Spaces'));
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

const button = (name: string) =>
  [...el.querySelectorAll('button')].find((node) => node.textContent?.trim() === name) as HTMLButtonElement | undefined;
const step = (name: string) =>
  [...el.querySelectorAll<HTMLButtonElement>('nav button')].find((node) => node.textContent?.endsWith(name));
const field = <T extends HTMLElement>(label: string) => el.querySelector<T>(`[aria-label="${label}"]`)!;
async function click(node: HTMLElement | undefined) {
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
async function type(label: string, value: string) {
  const input = field<HTMLInputElement>(label);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => input.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
}
const design = () => store.getState().design!;

describe('Spaces step', () => {
  it('renames a space and cascades its environment to a new cabinet and its runs', async () => {
    expect(el.querySelector('main h2')?.textContent).toBe('Spaces');
    await type('Space name', 'Main kitchen');
    expect(design().site.spaces[0]?.name).toBe('Main kitchen');
    await choose('Main kitchen environment', 'damp');
    await click(el.querySelectorAll<HTMLButtonElement>('[data-testid="space-space-kitchen"] button')[0]);
    expect(design().site.cabinets[0]).toMatchObject({ tag: 'C-1', envChoice: 'damp', locationRating: 'Damp' });
    expect(field<HTMLSelectElement>('C-1 location rating').value).toBe('Damp');
    expect(
      design()
        .runs.filter((run) => run.spaceId === 'space-kitchen')
        .some((run) => run.envChoice === 'damp'),
    ).toBe(true);
    expect(store.getState().dirty).toBe(true);
    await click(button('Undo'));
    expect(design().site.cabinets).toHaveLength(0);
  });

  it('sets home runs from quick picks and typed lengths with their provenance', async () => {
    const run = design().runs[0]!;
    const label = `${run.lineId}-${run.buildIndex}.${run.runIndex} home run`;
    await choose(`${label} quick pick`, 'other-level');
    expect(design().runs[0]).toMatchObject({ homeRunLengthFt: 45, homeRunProvenance: 'estimate' });
    expect(field<HTMLInputElement>(label).value).toBe('45');
    await type(label, '27.5');
    expect(design().runs[0]).toMatchObject({ homeRunLengthFt: 27.5, homeRunProvenance: 'entered' });
    expect(el.querySelector(`[data-testid="run-${run.key}"]`)?.textContent).toContain('(entered)');
    await type(label, '-3');
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('Enter a length in feet, 0 or more');
    expect(design().runs[0]?.homeRunLengthFt).toBe(27.5);
    await click(button('Same space (15 ft)'));
    expect(
      design()
        .runs.filter((item) => item.spaceId === run.spaceId)
        .every((item) => item.homeRunLengthFt === 15),
    ).toBe(true);
  });

  it('marks third-party runs as data by dealer (D8)', () => {
    const thirdParty = design().runs.filter((run) => run.source.kind === 'third-party');
    expect(thirdParty.length).toBeGreaterThan(0);
    for (const run of thirdParty)
      expect(el.querySelector(`[data-testid="run-${run.key}"]`)?.textContent).toContain('Data by dealer');
    const configured = design().runs.find((run) => run.source.kind === 'configured')!;
    expect(el.querySelector(`[data-testid="run-${configured.key}"]`)?.textContent).not.toContain('Data by dealer');
  });

  it('adds panel circuits and feeds a cabinet from one', async () => {
    await click(button('Add circuit'));
    await type('CKT-1 panel', 'LP-2');
    await choose('CKT-1 voltage', '277');
    expect(design().project.sources[0]).toMatchObject({ tag: 'CKT-1', panel: 'LP-2', voltage: 277 });
    await click(el.querySelectorAll<HTMLButtonElement>('[data-testid="space-space-kitchen"] button')[0]);
    await choose('C-1 circuit', 'src-1');
    expect(design().site.cabinets[0]?.sourceId).toBe('src-1');
    await choose('C-1 feed length quick pick', 'adjacent');
    expect(design().site.cabinets[0]).toMatchObject({ feedLengthFt: 25, feedLengthProvenance: 'estimate' });
  });

  it('merges spaces and disables editing when read-only', async () => {
    const [first, second] = design().site.spaces;
    await choose(`Merge ${second!.name} into`, first!.id);
    expect(design().site.spaces.map((space) => space.id)).not.toContain(second!.id);

    act(() => root.unmount());
    root = createRoot(el);
    const locked = { ...open, schedule: { ...open.schedule, is_locked: true } };
    await act(async () =>
      root.render(<Shell open={locked} store={store} api={{} as DesignApi} drafts={drafts} checks={[]} />),
    );
    await click(step('Spaces'));
    expect(el.querySelector<HTMLFieldSetElement>('.ill-sd__fieldset')?.disabled).toBe(true);
    expect(button('Undo')?.disabled).toBe(true);
  });
});
