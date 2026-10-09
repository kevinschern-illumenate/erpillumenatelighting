import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { App } from './App';
import './styles.css';

export interface MountOptions {
  /** Fixture schedule name, or null when opened from /portal/design without one. */
  schedule: string | null;
  /** Frappe CSRF token; every write sends it as X-Frappe-CSRF-Token. */
  csrfToken: string;
  /** Base URL of the whitelisted endpoints, e.g. /api/method/<module>.api */
  apiBase: string;
}

const roots = new WeakMap<Element, Root>();

export function mount(element: Element | null, options: MountOptions): Root {
  if (!element) throw new Error('ilLumenate System Designer: mount element not found');
  roots.get(element)?.unmount();
  const root = createRoot(element);
  roots.set(element, root);
  root.render(
    <StrictMode>
      <App options={options} />
    </StrictMode>,
  );
  return root;
}
