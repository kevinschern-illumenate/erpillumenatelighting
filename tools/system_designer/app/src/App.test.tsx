// @vitest-environment jsdom
import { act } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { mount } from './mount';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.replaceChildren();
});

describe('mount', () => {
  it('renders the product name and the schedule (D2)', async () => {
    const el = document.createElement('div');
    document.body.append(el);
    await act(async () => {
      mount(el, { schedule: 'SCH-0001', csrfToken: 't', apiBase: '/api/method/x' });
    });
    expect(el.querySelector('h1')?.textContent).toBe('ilLumenate System Designer');
    expect(el.textContent).toContain('Schedule SCH-0001');
  });

  it('asks for a schedule when opened without one', async () => {
    const el = document.createElement('div');
    document.body.append(el);
    await act(async () => {
      mount(el, { schedule: null, csrfToken: 't', apiBase: '/api/method/x' });
    });
    expect(el.textContent).toContain('Design system');
  });

  it('refuses a missing element', () => {
    expect(() => mount(null, { schedule: null, csrfToken: '', apiBase: '' })).toThrow(/mount element/);
  });
});
