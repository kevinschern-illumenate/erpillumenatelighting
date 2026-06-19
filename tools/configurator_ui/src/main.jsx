import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

const ROOT_ID = 'ill-configurator-root';

/**
 * Mount the configurator into a host element.
 *
 * @param {HTMLElement|string} el  Target element or its id/selector.
 * @param {object} [opts]          Optional config (also read from window.ILL_CONFIGURATOR_CONFIG).
 * @returns {{ unmount: () => void }}
 */
export function mountConfigurator(el, opts = {}) {
  const target =
    typeof el === 'string'
      ? document.getElementById(el) || document.querySelector(el)
      : el;

  if (!target) {
    // eslint-disable-next-line no-console
    console.error('[IllConfigurator] mount target not found:', el);
    return { unmount: () => {} };
  }

  // Ensure the mount target carries the scope id so Tailwind's `important`
  // scope and the scoped reset in index.css apply, even if the host used a
  // different selector to locate the element.
  if (target.id !== ROOT_ID) {
    target.id = ROOT_ID;
  }

  // Webflow embeds can pass config via a global; explicit opts win.
  const globalConfig =
    (typeof window !== 'undefined' && window.ILL_CONFIGURATOR_CONFIG) || {};
  const config = { ...globalConfig, ...opts };

  const root = ReactDOM.createRoot(target);
  root.render(
    <React.StrictMode>
      <App config={config} />
    </React.StrictMode>
  );

  return { unmount: () => root.unmount() };
}

// Expose a stable global for the Webflow embed: window.IllConfigurator.mount(...)
if (typeof window !== 'undefined') {
  window.IllConfigurator = window.IllConfigurator || {};
  window.IllConfigurator.mount = mountConfigurator;
}

// Auto-mount in the dev host (and in any page that already has the root div),
// unless the host explicitly opts out with data-ill-manual-mount.
if (typeof document !== 'undefined') {
  const auto = document.getElementById(ROOT_ID);
  if (auto && !auto.hasAttribute('data-ill-manual-mount')) {
    mountConfigurator(auto);
  }
}

export default mountConfigurator;
