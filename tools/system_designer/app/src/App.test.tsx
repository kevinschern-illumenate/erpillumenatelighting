// @vitest-environment jsdom
import 'fake-indexeddb/auto';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { DesignApiError, type DesignApi } from './design/api';
import { openDrafts, type DraftStore } from './design/drafts';
import { mount } from './mount';
import { openFixture } from './shell/fixture';
import { newDesign, type OpenDesign } from './shell/open';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const options = { schedule: 'SCH-TEST', csrfToken: 't', apiBase: '/api/method/x' };
const savedMeta = {
  name: 'SYSD-2026-00001',
  revision: 'A',
  status: 'Draft',
  modified: '2026-10-09 12:04:31.000001',
  schedule_version: 2,
  is_current: true,
  terms_accepted: true,
};

let drafts: DraftStore;
let dbIndex = 0;
let root: Root | undefined;
let el: HTMLDivElement;

beforeEach(() => {
  drafts = openDrafts(`app-test-${dbIndex++}`);
  el = document.createElement('div');
  document.body.append(el);
});

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  drafts.close();
  document.body.replaceChildren();
});

function apiFor(open: OpenDesign | Error, overrides: Partial<DesignApi> = {}) {
  return {
    openDesign: vi.fn(() => (open instanceof Error ? Promise.reject(open) : Promise.resolve(open))),
    saveDesign: vi.fn().mockResolvedValue({
      name: 'SYSD-2026-00002',
      revision: 'A',
      modified: '2026-10-09 15:42:10.000000',
      build_hash: 'b'.repeat(64),
      summary: {},
    }),
    copyDesignToVersion: vi.fn().mockResolvedValue({ name: 'SYSD-2026-00003' }),
    createRevision: vi.fn(),
    reconcileDesign: vi.fn(),
    ...overrides,
  } as unknown as DesignApi;
}

async function render(api: DesignApi, navigate = vi.fn()) {
  root = createRoot(el);
  await act(async () => {
    root!.render(<App options={options} services={{ api, drafts, navigate }} />);
  });
  // Let the open request, the draft lookup and the state update settle.
  for (let i = 0; i < 5; i += 1) await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
  return navigate;
}

const button = (name: string) =>
  [...el.querySelectorAll('button, a')].find((node) => node.textContent?.trim() === name) as HTMLElement | undefined;
const click = async (node: HTMLElement | undefined) => {
  if (!node) throw new Error('missing control');
  await act(async () => node.click());
};

describe('mount', () => {
  it('asks for a schedule when opened without one (D2)', async () => {
    await act(async () => {
      root = mount(el, { schedule: null, csrfToken: 't', apiBase: '/api/method/x' });
    });
    expect(el.querySelector('h1')?.textContent).toBe('ilLumenate System Designer');
    expect(el.textContent).toContain('Design system');
  });

  it('refuses a missing element', () => {
    expect(() => mount(null, { schedule: null, csrfToken: '', apiBase: '' })).toThrow(/mount element/);
  });
});

describe('designer shell', () => {
  it('opens a new design behind the terms, then saves with the acceptance', async () => {
    const api = apiFor(openFixture());
    await render(api);
    expect(api.openDesign).toHaveBeenCalledWith('SCH-TEST');
    expect(el.querySelector('h1')?.textContent).toBe('ilLumenate System Designer');
    expect(el.querySelector('[data-testid="schedule-name"]')?.textContent).toBe('Test house · Version 2');
    expect(el.textContent).toContain('New design');
    expect(el.querySelector('[data-testid="review-chip"]')?.textContent).toBe('Review optional');
    const dialog = el.querySelector('[role="dialog"]');
    expect(dialog?.textContent).toContain('Design aid. Verify against product documentation');
    expect(document.activeElement?.textContent).toBe('Accept and continue');
    expect(el.querySelector('[data-testid="save-state"]')?.textContent).toBe('Unsaved changes');

    await click(button('Accept and continue'));
    expect(el.querySelector('[role="dialog"]')).toBeNull();
    await click(button('Save'));
    expect(vi.mocked(api.saveDesign).mock.calls[0]?.[0]).toMatchObject({
      schedule: 'SCH-TEST',
      termsAccepted: true,
      designName: undefined,
    });
    expect(el.querySelector('[data-testid="save-state"]')?.textContent).toBe('Saved · 15:42');
    expect(el.textContent).toContain('Revision A');
  });

  it('shows readiness and the check panel counts, and collapses the panel', async () => {
    await render(apiFor(openFixture({ design: null })));
    expect(el.querySelector('[data-testid="design-size"]')?.textContent).toMatch(
      /This design has \d+ runs in \d+ spaces/,
    );
    expect(el.textContent).toContain('1 line need dealer data');
    const toggle = el.querySelector<HTMLButtonElement>('.ill-sd__checks-toggle')!;
    expect(toggle.textContent).toContain('✖ 0 errors');
    expect(toggle.textContent).toContain('▲ 2 warnings');
    expect(toggle.textContent).toContain('ℹ 1 notes');
    expect(el.querySelectorAll('.ill-sd__check')).toHaveLength(3);
    await click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(el.querySelectorAll('.ill-sd__check')).toHaveLength(0);
  });

  it('walks the steps and switches to engineering tabs', async () => {
    await render(apiFor(openFixture({ design_meta: null })));
    await click(button('Accept and continue'));
    expect(button('Back')).toHaveProperty('disabled', true);
    await click(button('Continue'));
    expect(el.querySelector('main h2')?.textContent).toBe('Spaces');
    expect(el.querySelector('[aria-current="step"]')?.textContent).toBe('2Spaces');
    await click(button('Engineering'));
    expect(el.querySelector('nav')?.getAttribute('aria-label')).toBe('Design tabs');
    expect(button('Continue')).toBeUndefined();
    expect(el.querySelector('[aria-current="step"]')?.textContent).toBe('Spaces');
  });

  it('flags a required review and applies schedule changes as one undoable edit', async () => {
    const open = openFixture();
    const design = newDesign(open).design;
    const dropped = design.runs[0]!;
    const saved = { ...design, runs: design.runs.slice(1) };
    const api = apiFor(
      openFixture({
        design: saved,
        design_meta: savedMeta,
        review_requirement: {
          required: true,
          reasons: [
            { code: 'DMX', detail: null },
            { code: 'LOAD_OVER_THRESHOLD', detail: '1,640 W' },
          ],
          satisfied: false,
        },
        reconcile: {
          added: [{ key: dropped.lineKey, lineId: dropped.lineId }],
          removed: [],
          changed: [],
          qty: [],
          in_sync: false,
        },
      }),
    );
    await render(api);
    expect(el.querySelector('[role="dialog"]')).toBeNull();
    expect(el.querySelector('[data-testid="review-chip"]')?.textContent).toBe('Review required');
    expect(el.querySelector('[data-testid="review-banner"]')?.textContent).toContain(
      'The connected load is over the review threshold (1,640 W).',
    );
    expect(el.querySelector('[data-testid="reconcile"]')?.textContent).toContain('1 line added');
    expect(el.querySelector('[data-testid="save-state"]')?.textContent).toBe('Saved · 12:04');
    await click(button('Apply schedule changes'));
    expect(el.querySelector('[data-testid="reconcile"]')).toBeNull();
    expect(el.querySelector('[data-testid="save-state"]')?.textContent).toBe('Unsaved changes');
    await click(button('Save'));
    expect(vi.mocked(api.saveDesign).mock.calls[0]?.[0]).toMatchObject({
      designName: savedMeta.name,
      expectedModified: savedMeta.modified,
      reconciled: true,
    });
    const sent = vi.mocked(api.saveDesign).mock.calls[0]![0].design;
    expect(sent.runs.some((run) => run.key === dropped.key)).toBe(true);
  });

  it('keeps a locked version read-only and copies the design forward', async () => {
    const design = newDesign(openFixture()).design;
    const api = apiFor(
      openFixture({
        schedule: { ...openFixture().schedule, is_locked: true },
        design,
        design_meta: { ...savedMeta, terms_accepted: false },
        newer_version: { name: 'SCH-TEST-V3', version: 3 },
      }),
    );
    const navigate = await render(api);
    expect(el.querySelector('[role="dialog"]')).toBeNull();
    expect(el.textContent).toContain('This schedule version is locked');
    expect(button('Save')).toHaveProperty('disabled', true);
    await click(button('Design on version 3'));
    expect(api.copyDesignToVersion).toHaveBeenCalledWith(savedMeta.name, 'SCH-TEST-V3');
    expect(navigate).toHaveBeenCalledWith('/portal/schedules/SCH-TEST-V3/design');
  });

  it('explains a copy that fails, and an open that fails', async () => {
    const api = apiFor(
      openFixture({
        schedule: { ...openFixture().schedule, is_locked: true },
        design: newDesign(openFixture()).design,
        design_meta: savedMeta,
        newer_version: { name: 'SCH-TEST-V3', version: 3 },
      }),
      { copyDesignToVersion: vi.fn().mockRejectedValue(new DesignApiError('CONFLICT', 'That version has a design')) },
    );
    const navigate = await render(api);
    await click(button('Design on version 3'));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('That version has a design');
    expect(navigate).not.toHaveBeenCalled();

    act(() => root?.unmount());
    el.replaceChildren();
    await render(apiFor(new DesignApiError('FORBIDDEN', 'The System Designer is not available for your account yet')));
    expect(el.querySelector('[role="alert"]')?.textContent).toBe(
      'The System Designer is not available for your account yet',
    );
  });
});
