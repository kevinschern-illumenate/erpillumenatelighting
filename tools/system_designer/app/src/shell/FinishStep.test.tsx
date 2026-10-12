// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign, vdLimits } from '@ill/engine/designCheck';
import { addCabinet, distanceDefaults } from '@ill/engine/site';
import type { DesignApi, WritebackPreview } from '../design/api';
import { parseCatalog } from '../design/catalog';
import type { CheckState } from '../design/engine';
import { createDesignStore, type DesignStore } from '../design/store';
import { FinishStep, wireFeet } from './FinishStep';
import { openFixture } from './fixture';
import { newDesign } from './open';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const META = {
  name: 'SYSD-1',
  revision: 'A',
  status: 'Draft',
  modified: '2026-10-09 12:00:00',
  schedule_version: 2,
  is_current: true,
  terms_accepted: true,
};
const PREVIEW: WritebackPreview = {
  add: [
    { key: 'Supply:PSU-96', role: 'Supply', item_code: 'PSU-96', item_name: '96 W supply', qty: 1, location: 'Pantry' },
    {
      key: 'Wire:W18',
      role: 'Wire',
      item_code: 'W18',
      item_name: '18/2 CL2',
      qty: 2,
      unit: 'spool',
      location: 'Field wire',
    },
  ],
  update: [],
  remove: [{ key: 'Accessory:OLD', item_code: 'OLD', item_name: 'Old clip', qty: 4, line_id: 'ACC1' }],
  replaces_configurator_lines: [
    { key: 'replace:k1', for_line: 'k1', line_id: 'A1', lines: [{ item_code: 'CFG-60', item_name: '60 W', qty: 2 }] },
  ],
  blocked: [{ ref: 'X-1', reason: 'X-1 is not an orderable ilLumenate product' }],
  error_count: 0,
  can_apply: true,
};

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
let engine: CheckState;
let api: DesignApi;
const open = openFixture({ catalog_hash: 'd'.repeat(64) });

beforeEach(() => {
  el = document.createElement('div');
  document.body.append(el);
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
  store.getState().load('SCH-TEST', design, META);
  const catalog = parseCatalog('d'.repeat(64), catalogPayload);
  const loaded = store.getState().design!;
  engine = {
    state: 'ready',
    design: loaded,
    check: checkDesign({
      design: loaded,
      products: catalog.items,
      wires: catalog.wires,
      codeTables,
      lines: open.lines,
      limits: vdLimits(open.settings),
    }),
  };
  api = {
    writebackPreview: vi.fn().mockResolvedValue(PREVIEW),
    writebackApply: vi.fn().mockResolvedValue({ added: 2, updated: 0, removed: 0, replaced: 1 }),
  } as unknown as DesignApi;
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

async function render() {
  root = createRoot(el);
  await act(async () => root.render(<FinishStep open={open} store={store} engine={engine} api={api} />));
}
const button = (text: RegExp) =>
  [...el.querySelectorAll('button')].find((node) => text.test(node.textContent ?? '')) as HTMLButtonElement;
async function click(node: HTMLElement) {
  await act(async () => node.click());
}

describe('Finish step write-back', () => {
  it('sends the engine wire footage and writes only the changes left ticked', async () => {
    await render();
    await click(button(/Show the changes/));
    const feet = wireFeet(engine.state === 'ready' ? engine.check.result.bom : []);
    expect(Object.keys(feet).every((id) => id.startsWith('wire:'))).toBe(true);
    expect(api.writebackPreview).toHaveBeenCalledWith('SYSD-1', feet);
    const rows = [...el.querySelectorAll('[data-testid="writeback-changes"] tbody tr')].map((row) =>
      [...row.querySelectorAll('td')].slice(1).map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ['Add', '96 W supply', '1', 'Pantry'],
      ['Add', '18/2 CL2', '2 spools', 'Field wire'],
      ['Remove', 'Old clip', '4', 'ACC1'],
      ['Replace', '60 W', '2', 'Supplies of line A1'],
    ]);
    expect(el.querySelector('[data-testid="price-delta"]')).toBeNull();
    expect(el.querySelector('[data-testid="writeback-blocked"]')!.textContent).toContain('X-1');
    await click(el.querySelector<HTMLInputElement>('input[aria-label="Include remove Old clip"]')!);
    await click(button(/Add 3 changes/));
    expect(api.writebackApply).toHaveBeenCalledWith('SYSD-1', ['Supply:PSU-96', 'Wire:W18', 'replace:k1'], feet);
    expect(el.querySelector('[data-testid="writeback-notice"]')!.textContent).toBe(
      'The schedule is updated: 2 added, 1 configurator supply group replaced.',
    );
  });

  it('shows the price change only when the server sends one', async () => {
    vi.mocked(api.writebackPreview).mockResolvedValue({
      ...PREVIEW,
      price_delta: { amount: 170, price_list: 'Standard Selling', unpriced: ['W18'] },
    });
    await render();
    await click(button(/Show the changes/));
    expect(el.querySelector('[data-testid="price-delta"]')!.textContent).toBe(
      'Price change: +$170.00 at Standard Selling prices (no price yet for W18).',
    );
  });

  it('asks for a save before comparing', async () => {
    store.getState().edit((draft) => {
      draft.project.equipment[0]!.qty = 2;
    });
    await render();
    expect(button(/Show the changes/)).toBeUndefined();
    expect(el.textContent).toContain('Save your changes first.');
  });
});

describe('Finish step review request', () => {
  it('sends the saved revision with its counts and shows who reviews it', async () => {
    const ready = engine as Extract<CheckState, { state: 'ready' }>;
    engine = { ...ready, check: { ...ready.check, messages: [] } };
    api.requestReview = vi.fn().mockResolvedValue({
      request: 'ILL-REQ-1',
      reviewer: 'Ada Engineer',
      design_meta: { ...META, status: 'In Review', review_request: 'ILL-REQ-1' },
    });
    await render();
    const card = el.querySelector('[data-testid="review-card"]')!;
    expect(card.querySelector('[data-testid="review-requirement"]')!.textContent).toContain('optional');
    const send = button(/Request review/);
    expect(send.disabled).toBe(false);
    await act(async () => {
      const select = card.querySelector('select')!;
      select.value = 'High';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await click(send);
    expect(api.requestReview).toHaveBeenCalledWith(
      expect.objectContaining({ design: 'SYSD-1', priority: 'High', errorCount: 0 }),
    );
    expect(store.getState().meta?.status).toBe('In Review');
    expect(el.querySelector('[data-testid="review-notice"]')!.textContent).toBe(
      'Review requested. Ada Engineer will review revision A.',
    );
    expect(button(/Request review/)).toBeUndefined();
    expect(el.querySelector('[data-testid="review-status"]')!.textContent).toContain('is with ilLumenate');
  });

  it('blocks the request while the design has errors', async () => {
    engine = {
      ...(engine as Extract<CheckState, { state: 'ready' }>),
      check: {
        ...(engine as Extract<CheckState, { state: 'ready' }>).check,
        messages: [{ code: 'PSU_OVERLOAD', severity: 'error', entityRef: 'PS-1', text: 'Overloaded' }],
      },
    };
    await render();
    expect(button(/Request review/).disabled).toBe(true);
    expect(el.textContent).toContain('Fix the error on the Check step first.');
  });
});

describe('Finish step reviewer mode', () => {
  const reviewer = openFixture({
    catalog_hash: 'd'.repeat(64),
    permissions: { can_edit: false, can_review: true, can_view_pricing: false, can_engineer: true },
  });
  const inReview = { ...META, status: 'In Review', review_request: 'ILL-REQ-1' };
  async function renderAs(value = reviewer, navigate?: (url: string) => void) {
    root = createRoot(el);
    await act(async () =>
      root.render(<FinishStep open={value} store={store} engine={engine} api={api} navigate={navigate} />),
    );
  }
  const withMessages = (messages: Extract<CheckState, { state: 'ready' }>['check']['messages']) => {
    const ready = engine as Extract<CheckState, { state: 'ready' }>;
    engine = { ...ready, check: { ...ready.check, messages } };
  };
  async function type(node: HTMLInputElement | HTMLTextAreaElement, value: string) {
    await act(async () => {
      const proto = node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(node, value);
      node.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  it('overrides an open error with a reason before approval is possible', async () => {
    store.setState({ meta: inReview });
    withMessages([{ code: 'PSU_OVERLOAD', severity: 'error', entityRef: 'PS-1', text: 'Overloaded' }]);
    const override = {
      code: 'PSU_OVERLOAD',
      entityRef: 'PS-1',
      kind: 'staff-override' as const,
      reason: 'Load is intermittent',
      by: 'ae@example.com',
      at: '2026-10-09T12:00:00.000Z',
    };
    api.overrideCheck = vi.fn().mockResolvedValue({
      overrides: [override],
      build_hash: 'e'.repeat(64),
      design_meta: { ...inReview, modified: '2026-10-09 12:05:00' },
    });
    await renderAs();
    expect(button(/^Approve$/).disabled).toBe(true);
    expect(button(/Request review/)).toBeUndefined();
    const reason = el.querySelector<HTMLInputElement>('input[aria-label="Override reason for PSU_OVERLOAD on PS-1"]')!;
    await type(reason, 'Load is intermittent');
    await click(button(/^Override$/));
    expect(api.overrideCheck).toHaveBeenCalledWith({
      design: 'SYSD-1',
      code: 'PSU_OVERLOAD',
      entityRef: 'PS-1',
      reason: 'Load is intermittent',
    });
    expect(store.getState().design!.overrides).toEqual([override]);
    expect(store.getState().dirty).toBe(false);
    expect(store.getState().meta!.modified).toBe('2026-10-09 12:05:00');
  });

  it('asks for a note before requesting changes and records an approval', async () => {
    store.setState({ meta: inReview });
    withMessages([]);
    api.reviewDecide = vi.fn().mockImplementation(async (_design: string, decision: string) => ({
      review: 'REV-1',
      status: decision,
      design_meta: { ...inReview, status: decision, approved_by: 'ae@example.com' },
    }));
    await renderAs();
    expect(button(/Request changes/).disabled).toBe(true);
    await click(button(/^Approve$/));
    expect(api.reviewDecide).toHaveBeenCalledWith('SYSD-1', 'Approved', '');
    expect(store.getState().meta?.status).toBe('Approved');
    expect(el.querySelector('[data-testid="review-status"]')!.textContent).toContain('approved by ae@example.com');
    expect(el.querySelector('[data-testid="reviewer-panel"]')).toBeNull();
    expect(el.querySelector('[data-testid="review-notice"]')!.textContent).toBe('Revision A is approved.');
  });

  it('sends a requested change with its note', async () => {
    store.setState({ meta: inReview });
    withMessages([]);
    api.reviewDecide = vi.fn().mockResolvedValue({
      review: 'REV-1',
      status: 'Changes Requested',
      design_meta: { ...inReview, status: 'Changes Requested' },
    });
    await renderAs();
    await type(el.querySelector<HTMLTextAreaElement>('textarea[aria-label="Review note"]')!, 'Split PS-1');
    await click(button(/Request changes/));
    expect(api.reviewDecide).toHaveBeenCalledWith('SYSD-1', 'Changes Requested', 'Split PS-1');
    expect(store.getState().meta?.status).toBe('Changes Requested');
  });

  it('starts the next revision of an approved design and opens it', async () => {
    store.setState({ meta: { ...META, status: 'Approved' } });
    api.createRevision = vi.fn().mockResolvedValue({ name: 'SYSD-2', revision: 'B' });
    const navigate = vi.fn();
    await renderAs(open, navigate);
    await click(button(/Start the next revision/));
    expect(api.createRevision).toHaveBeenCalledWith('SYSD-1', 'Started after revision A was approved');
    expect(navigate).toHaveBeenCalledWith('/portal/schedules/SCH-TEST/design');
  });

  it('lists the review comments and adds one', async () => {
    api.listComments = vi.fn().mockResolvedValue([
      {
        comment_id: 'c1',
        view: 'General',
        anchor: null,
        body: 'Check the garage run',
        author: 'ae@example.com',
        author_name: 'Ada Engineer',
        created_on: '2026-10-09 12:00:00',
        resolved: false,
        resolved_by: null,
      },
    ]);
    api.addComment = vi.fn().mockImplementation(async (args: { body: string; view: string }) => ({
      comment_id: 'c2',
      view: args.view,
      anchor: null,
      body: args.body,
      author: 'dealer@example.com',
      author_name: 'Dee Dealer',
      created_on: '2026-10-09 12:10:00',
      resolved: false,
      resolved_by: null,
    }));
    await renderAs(open);
    const thread = () => el.querySelector('[data-testid="comments-General"]')!;
    expect(thread().textContent).toContain('Check the garage run');
    await type(thread().querySelector('textarea')!, 'Done, moved it to PS-2');
    await click(button(/Add comment/));
    expect(api.addComment).toHaveBeenCalledWith({
      design: 'SYSD-1',
      body: 'Done, moved it to PS-2',
      view: 'General',
      anchor: undefined,
    });
    expect(thread().querySelectorAll('li')).toHaveLength(2);
  });
});

describe('Finish step review gate', () => {
  const required = {
    required: true,
    reasons: [{ code: 'DMX', detail: 'DMX control' }],
    satisfied: false,
  };
  async function renderWith(value: ReturnType<typeof openFixture>) {
    root = createRoot(el);
    await act(async () => root.render(<FinishStep open={value} store={store} engine={engine} api={api} />));
  }

  it('lets an Applications Engineer allow ordering without review, with a reason', async () => {
    api.overrideReviewGate = vi.fn().mockResolvedValue({
      override_id: 'k',
      review_requirement: {
        ...required,
        satisfied: true,
        override: { by: 'ae@example.com', reason: 'Signed off', on: '2026-10-09' },
      },
    });
    await renderWith(
      openFixture({
        catalog_hash: 'd'.repeat(64),
        review_requirement: required,
        permissions: { can_edit: false, can_review: true, can_view_pricing: false, can_engineer: true },
      }),
    );
    const input = el.querySelector<HTMLInputElement>('[data-testid="gate-override"] input')!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'Signed off');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await click(button(/Allow ordering without review/));
    expect(api.overrideReviewGate).toHaveBeenCalledWith('SCH-TEST', 'Signed off');
    expect(el.querySelector('[data-testid="review-gate"]')!.textContent).toContain('ae@example.com overrode it');
    expect(el.querySelector('[data-testid="gate-override"]')).toBeNull();
  });

  it('offers no override to dealers and says when an approval no longer matches', async () => {
    store.setState({ meta: { ...META, status: 'Approved' } });
    await renderWith(openFixture({ catalog_hash: 'd'.repeat(64), review_requirement: required }));
    expect(el.querySelector('[data-testid="gate-override"]')).toBeNull();
    expect(el.querySelector('[data-testid="review-gate"]')!.textContent).toContain('changed after this revision');
  });
});
