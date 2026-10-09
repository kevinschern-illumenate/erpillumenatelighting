// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import catalogPayload from '../../../packages/core-schemas/fixtures/catalog/payload.json';
import { codeTables } from '@ill/data/codeTables';
import { buildDrawing } from '@ill/drawing/build';
import { checkDesign, vdLimits } from '@ill/engine/designCheck';
import { addCabinet, distanceDefaults } from '@ill/engine/site';
import type { DesignApi } from '../design/api';
import { parseCatalog } from '../design/catalog';
import type { CheckState } from '../design/engine';
import { createDesignStore, type DesignStore } from '../design/store';
import { openFixture } from './fixture';
import { newDesign, type OpenDesign } from './open';
import { ViewsStep, type ViewsDeps } from './ViewsStep';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const fonts = resolve(import.meta.dirname, '../../../packages/serializers/fonts');
const fontBytes = {
  regular: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Regular.ttf'))),
  bold: new Uint8Array(readFileSync(resolve(fonts, 'Arimo-Bold.ttf'))),
  name: 'Arimo' as const,
};
const META = {
  name: 'SYSD-1',
  revision: 'A',
  status: 'Draft',
  modified: '2026-10-09 12:00:00',
  schedule_version: 2,
  is_current: true,
  terms_accepted: true,
};

let root: Root;
let el: HTMLDivElement;
let store: DesignStore;
let engine: CheckState;
let api: DesignApi;
let deps: ViewsDeps & { save: ReturnType<typeof vi.fn<(blob: Blob, filename: string) => void>> };
const open = openFixture({ catalog_hash: 'd'.repeat(64), user: 'dealer@example.com' });

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
    uploadDeliverable: vi.fn().mockImplementation(async (args: { kind: string; variant: string; sha256: string }) => ({
      file_url: '/private/files/riser.pdf',
      row: {
        name: 'row-1',
        kind: args.kind,
        variant: args.variant,
        file: '/private/files/riser.pdf',
        file_sha256: args.sha256,
        revision: 'A',
        build_hash: 'b'.repeat(64),
        created_by: 'dealer@example.com',
        created_on: '2026-10-09 12:01:00',
      },
    })),
  } as unknown as DesignApi;
  deps = {
    draw: (input) => buildDrawing(input.project, input.library, input.result, input.options),
    fonts: vi.fn().mockResolvedValue(fontBytes),
    logo: vi.fn().mockResolvedValue(null),
    save: vi.fn<(blob: Blob, filename: string) => void>(),
  };
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

async function render(value: OpenDesign = open) {
  root = createRoot(el);
  await act(async () => root.render(<ViewsStep open={value} store={store} engine={engine} api={api} deps={deps} />));
}
const button = (name: string) =>
  [...el.querySelectorAll('button')].find((node) => node.textContent?.trim() === name) as HTMLButtonElement;
const byTest = (id: string) => el.querySelector<HTMLElement>(`[data-testid="${id}"]`);
// Drawing and exporting finish a few tasks later; wait until the step is idle again.
async function click(node: HTMLElement) {
  await act(async () => node.click());
  for (let i = 0; i < 200 && el.textContent?.match(/Drawing the riser|Preparing the/); i += 1)
    await act(async () => {
      await new Promise((done) => setTimeout(done, 25));
    });
}

describe('Views step', () => {
  it('draws the riser and keeps the PDF on the saved revision', async () => {
    await render();
    const stamps = [...el.querySelectorAll('[data-testid="riser-options"] select')[1]!.querySelectorAll('option')];
    expect(stamps.map((option) => option.value)).toEqual(['PRELIMINARY', 'NOT FOR CONSTRUCTION', 'FOR REFERENCE']);
    await click(button('Draw riser'));
    expect(byTest('riser-preview')?.textContent).toContain('Sheet 1 of');
    await click(button('Download PDF'));
    expect(deps.save).toHaveBeenCalledTimes(1);
    const [blob, filename] = deps.save.mock.calls[0]!;
    expect(filename).toBe('ilLumenate-System-Designer_SCH-TEST_revA_Tabloid.pdf');
    expect((blob as Blob).type).toBe('application/pdf');
    expect(api.uploadDeliverable).toHaveBeenCalledWith(
      expect.objectContaining({ design: 'SYSD-1', kind: 'Riser PDF', variant: 'Tabloid', filename }),
    );
    const sent = vi.mocked(api.uploadDeliverable).mock.calls[0]![0];
    expect(sent.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(byTest('views-notice')?.textContent).toBe('Downloaded and kept on revision A.');
    expect(byTest('deliverables')?.textContent).toContain('Riser PDF · Tabloid');
  });

  it('only downloads while the design has unsaved changes, and offers the review stamp once approved', async () => {
    store.setState({ dirty: true });
    await render();
    await click(button('Draw riser'));
    await click(button('Download DXF (ZIP)'));
    expect(deps.save.mock.calls[0]![1]).toBe('ilLumenate-System-Designer_SCH-TEST_revA_Tabloid.zip');
    expect(api.uploadDeliverable).not.toHaveBeenCalled();
    expect(byTest('views-notice')?.textContent).toBe('Downloaded. Save the design to keep its drawings on it.');
    act(() => root.unmount());
    store.setState({ meta: { ...META, status: 'Approved', approved_by: 'Avery Engineer' } });
    await render();
    const stamps = [...el.querySelectorAll('[data-testid="riser-options"] select')[1]!.querySelectorAll('option')];
    expect(stamps.map((option) => option.value)).toContain('REVIEWED BY ILLUMENATE');
  });
});
