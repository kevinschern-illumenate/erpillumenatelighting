# Product Finder UI

The Finder uses the ERP definition, matching service and owner-bound sessions. Both bundles are committed because Frappe Cloud runs `bench build`, not Vite. The former seed-catalog/Vercel prototype has been retired. Staff manage live questions, images, glossary, conditions and ERP value maps in Desk.

```sh
npm ci --prefix tools/configurator_ui
npm test --prefix tools/configurator_ui
npm run build:portal --prefix tools/configurator_ui
npm run build:public --prefix tools/configurator_ui
git diff --exit-code illumenate_lighting/public/product_finder
```

For development use `npm run dev --prefix tools/configurator_ui` with a mocked client or an ERP host exposing the authenticated endpoints. The public app requires an explicit API base and brand. It never uses portal credentials.

Portal `/portal/product-finder` passes `mode: 'portal'`, the CSRF token, and optional `sessionToken`, `claimToken`, or authorized staff `preview`. Answers autosave after 500 ms; visible-option counts update after 150 ms. Reopening a session checks the current definition and catalog. A saved public claim in local storage resumes after dealer approval.

Webflow embed (replace the ERP host and exact Brand name):

```html
<link rel="stylesheet" href="https://ERP-HOST/assets/illumenate_lighting/product_finder/public/ill-finder.css">
<div id="ill-configurator-root" data-ill-manual-mount></div>
<script src="https://ERP-HOST/assets/illumenate_lighting/product_finder/public/ill-finder.js"></script>
<script>
IllConfigurator.mount('ill-configurator-root', {
  mode: 'public', apiBase: 'https://ERP-HOST', brand: 'EXACT-BRAND-NAME'
});
</script>
```

Set the brand's HTTPS `webflow_site_url`, enable it in Product Finder Settings → Public Brands, and publish/sync the intended products to that brand. Public results contain published product links, images and fit information only. The dealer CTA claims the session after login; an unclaimed session expires after seven days.

`--ill-finder-top` controls sticky-header spacing. Styles are scoped to `#ill-configurator-root`; mounts expose `unmount()`. No competitor table or offline recommendation data ships in either bundle.

Local React/DOM/service tests exercise contracts. They do not prove database migrations, real CORS, publication data or live engineering combinations; run the staging scenarios in `docs/B2B_CLOUD_ACCEPTANCE.md` after deployment.
