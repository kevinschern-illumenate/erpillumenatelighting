/**
 * Phase 4 - Legacy shim.
 *
 * The original Webflow configurator (~50 KB IIFE) has been replaced by the
 * scoped, multi-instance-safe IllConfigurator module system in:
 *   public/js/configurator/shared_configurator.js
 *   public/js/configurator/fixture_steps.js
 *   public/js/configurator/tape_neon_steps.js
 *
 * Those modules are loaded globally via hooks.py (web_include_js /
 * app_include_js) and provide the legacy globals
 * (window.WebflowConfigurator, initWebflowConfigurator, resetConfiguration,
 * validateConfiguration, addToSchedule) for backwards compatibility with
 * inline onclick handlers and product_detail.js.
 *
 * This file is retained only because templates/pages/product_detail.html
 * still emits a <script src="..."> reference to it. It intentionally has
 * no runtime effect.
 */
if (typeof window !== 'undefined' && !window.IllConfigurator) {
    console.warn('[illumenate_lighting] webflow_configurator.js loaded but IllConfigurator namespace missing; check hooks.py web_include_js order.');
}
