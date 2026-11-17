// @vitest-environment jsdom
import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Button, ConfirmDialog, ErrorState, IconButton, LoadBar, loadTone, ToastProvider, UnitInput, useToast } from '.';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let el: HTMLDivElement;

beforeEach(() => {
  el = document.createElement('div');
  document.body.append(el);
  root = createRoot(el);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
  vi.useRealTimers();
});

const render = (node: React.ReactNode) => act(() => root.render(node));

describe('buttons', () => {
  it('gives an icon button a real text name', () => {
    render(<IconButton label="Undo" icon={<span>↶</span>} />);
    const button = el.querySelector('button')!;
    expect(button.textContent).toBe('↶Undo');
    expect(button.querySelector('.sd-sr-only')?.textContent).toBe('Undo');
  });

  it('disables a loading button and marks it busy', () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    const button = el.querySelector('button')!;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');
    expect(button.type).toBe('button');
  });
});

describe('ConfirmDialog', () => {
  it('starts on Cancel and reports the choice', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    await act(async () =>
      root.render(
        <ConfirmDialog open title="Leave with errors?" confirmLabel="Continue anyway" onConfirm={onConfirm} onCancel={onCancel}>
          3 errors are open.
        </ConfirmDialog>,
      ),
    );
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain('Leave with errors?');
    expect(document.activeElement?.textContent).toBe('Cancel');
    const confirm = [...dialog.querySelectorAll('button')].find((node) => node.textContent === 'Continue anyway')!;
    await act(async () => confirm.click());
    expect(onConfirm).toHaveBeenCalled();
    await act(async () => {
      document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('toasts', () => {
  function Pusher({ onUndo }: { onUndo(): void }) {
    const toast = useToast();
    return (
      <button type="button" onClick={() => toast({ title: 'Run deleted', action: { label: 'Undo', onClick: onUndo } })}>
        push
      </button>
    );
  }

  it('announces in a live region, runs the action and expires', async () => {
    vi.useFakeTimers();
    const onUndo = vi.fn();
    render(
      <ToastProvider>
        <Pusher onUndo={onUndo} />
      </ToastProvider>,
    );
    const region = el.querySelector('[aria-live="polite"]')!;
    await act(async () => el.querySelector('button')!.click());
    await act(async () => el.querySelector('button')!.click());
    expect(region.querySelectorAll('[data-testid="toast"]')).toHaveLength(2);
    const undo = [...region.querySelectorAll('button')].find((node) => node.textContent === 'Undo')!;
    await act(async () => undo.click());
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(region.querySelectorAll('[data-testid="toast"]')).toHaveLength(1);
    await act(async () => vi.advanceTimersByTime(10_001));
    expect(region.querySelectorAll('[data-testid="toast"]')).toHaveLength(0);
  });

  it('is a no-op without a provider', () => {
    render(<Pusher onUndo={() => {}} />);
    expect(() => act(() => el.querySelector('button')!.click())).not.toThrow();
  });
});

describe('UnitInput', () => {
  function Harness({ onCommit }: { onCommit(value: number): void }) {
    const [value, setValue] = useState(10);
    return (
      <UnitInput
        label="Home run"
        value={value}
        onCommit={(feet) => {
          setValue(feet);
          onCommit(feet);
        }}
      />
    );
  }

  const type = async (input: HTMLInputElement, text: string) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    await act(async () => {
      setter.call(input, text);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => {
      input.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    });
  };

  it('commits feet and inches, and explains a bad entry', async () => {
    const onCommit = vi.fn();
    render(<Harness onCommit={onCommit} />);
    const input = el.querySelector('input')!;
    await type(input, '12\' 6"');
    expect(onCommit).toHaveBeenCalledWith(12.5);
    expect(input.value).toBe('12.5');
    await type(input, 'twelve');
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(el.textContent).toContain('Enter a length like');
  });
});

describe('states', () => {
  it('offers Retry, the code and a contact link', async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="The server answered 502" code="INTERNAL" onRetry={onRetry} />);
    expect(el.querySelector('[role="alert"]')?.textContent).toBe('The server answered 502');
    expect(el.textContent).toContain('Error code: INTERNAL');
    expect(el.querySelector('a')?.getAttribute('href')).toBe('/portal/support');
    await act(async () => el.querySelector('button')!.click());
    expect(onRetry).toHaveBeenCalled();
  });

  it('shows load by shape and text', () => {
    expect(loadTone(50, 100)).toBe('ok');
    expect(loadTone(80, 100)).toBe('warning');
    expect(loadTone(101, 100)).toBe('error');
    expect(loadTone(1, 0)).toBe('error');
    render(<LoadBar value={120} max={100} label="PS-1 load" />);
    expect(el.querySelector('[role="meter"]')?.getAttribute('aria-valuetext')).toBe('120 of 100 W (120%)');
    expect(el.textContent).toContain('Error: 120 / 100 W · 120%');
  });
});
