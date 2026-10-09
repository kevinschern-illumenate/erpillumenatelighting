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
const open = openFixture({ settings: { ...openFixture().settings, group_threshold_qty: 6 } });
const drafts = { get: vi.fn(), put: vi.fn(), remove: vi.fn(), close: vi.fn() } as unknown as DraftStore;

async function render(value = open) {
  root = createRoot(el);
  await act(async () =>
    root.render(<Shell open={value} store={store} api={{} as DesignApi} drafts={drafts} checks={[]} />),
  );
  await click(step('Runs'));
}

beforeEach(async () => {
  el = document.createElement('div');
  document.body.append(el);
  store = createDesignStore();
  store.getState().load('SCH-TEST', newDesign(open).design, null);
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
const row = (id: string) => el.querySelector<HTMLTableRowElement>(`[data-testid="row-${id}"]`);
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
async function type(label: string, value: string) {
  const input = field<HTMLInputElement>(label);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => input.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
}
const design = () => store.getState().design!;

describe('Runs step', () => {
  it('lists every run with its source data and folds identical copies into a group', () => {
    expect(el.querySelector('main h2')?.textContent).toBe('Runs');
    expect(el.querySelector('[data-testid="run-count"]')?.textContent).toContain(`${design().runs.length} runs`);
    const linear = row('a1linear:1:1')!;
    expect(linear.textContent).toContain('Linear fixture');
    expect(linear.textContent).toContain('6 ft');
    expect(linear.textContent).toContain('26.4 W');
    expect(linear.textContent).toContain('Not assigned');
    const group = row('grp-e1other')!;
    expect(group.textContent).toContain('E1-1.1 … E1-6.1 (6 runs)');
    expect(group.textContent).toContain('Data by dealer');
    expect(group.textContent).toContain('0 of 6 assigned');
    expect(row('e1other:2:1')).toBeNull();
  });

  it('shows the strip preview and flags a run past its maximum in the row and the check panel', async () => {
    store.getState().edit((draft) => {
      draft.runs.find((run) => run.key === 'b1tape:1:2')!.lengthFt = 20;
    });
    await act(async () => undefined);
    expect(row('b1tape:1:2')?.textContent).toContain('this build allows 16 ft');
    expect(el.querySelector('[aria-label="Checks"]')?.textContent).toContain('Run B1-1.2');
    await click(button('B1-1.2'));
    const preview = el.querySelector('[data-testid="strip-preview"]')!;
    expect(preview.textContent).toContain('20 ft · 43.3 W · End feed · max 16 ft');
    expect(preview.querySelector('.ill-sd__strip-bar--over')).not.toBeNull();
    expect(preview.querySelectorAll('[data-testid="strip-feed"]')).toHaveLength(1);
    await click(button('A1-1.1'));
    expect(el.querySelector('[data-testid="strip-preview"]')?.textContent).toContain('A1-1.1');
  });

  it('bulk edits the selected runs as one undo step', async () => {
    await click(field('Select A1-1.1'));
    await click(field('Select A1-2.1'));
    expect(el.querySelector('[aria-label="Selected runs"]')?.textContent).toContain('2 runs selected');
    await choose('Selected environment', 'plenum');
    await choose('Move selected to space', 'space-hall');
    await type('Selected home run', '33');
    const edited = design().runs.filter((run) => run.key === 'a1linear:1:1' || run.key === 'a1linear:2:1');
    expect(edited.every((run) => run.envChoice === 'plenum' && run.spaceId === 'space-hall')).toBe(true);
    expect(edited.every((run) => run.homeRunLengthFt === 33 && run.homeRunProvenance === 'entered')).toBe(true);
    await choose('Selected home run quick pick', 'adjacent');
    expect(edited.length).toBe(2);
    expect(design().runs.find((run) => run.key === 'a1linear:1:1')).toMatchObject({
      homeRunLengthFt: 25,
      homeRunProvenance: 'estimate',
    });
    await click(button('Undo'));
    expect(design().runs.find((run) => run.key === 'a1linear:1:1')?.homeRunLengthFt).toBe(33);
  });

  it('splits a group, regroups copies and refuses mixed lines', async () => {
    await click(button('Show runs', row('grp-e1other')!));
    expect(row('e1other:2:1')).not.toBeNull();
    await click(button('Split', row('grp-e1other')!));
    expect(design().runs.some((run) => run.groupId)).toBe(false);
    expect(row('e1other:2:1')?.textContent).toContain('E1-2.1');

    await click(field('Select E1-1.1'));
    await click(field('Select E1-2.1'));
    await click(button('Group'));
    expect(design().runs.filter((run) => run.groupId === 'grp-e1other')).toHaveLength(2);
    expect(el.querySelector('[aria-label="Selected runs"]')).toBeNull();

    await click(field('Select E1-3.1'));
    await click(field('Select A1-1.1'));
    await click(button('Group'));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('Only runs of one schedule line can be grouped');
  });

  it('filters by space and is read-only on a locked schedule', async () => {
    await choose('Show space', 'space-living-room');
    expect(el.querySelector('[data-testid="run-count"]')?.textContent).toContain('4 runs');
    expect(row('a1linear:1:1')).toBeNull();

    act(() => root.unmount());
    await render({ ...open, schedule: { ...open.schedule, is_locked: true } });
    expect(el.querySelector<HTMLFieldSetElement>('.ill-sd__runs-step .ill-sd__fieldset')?.disabled).toBe(true);
  });
});
