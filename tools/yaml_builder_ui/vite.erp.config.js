import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react(), {
    name: 'no-erp-reference-in-public-bundle',
    generateBundle() {
      // IIFE builds inline dynamic imports too; forbid the snapshot anywhere in the graph.
      for (const id of this.getModuleIds()) {
        if (id.split('?')[0].endsWith('/erp-reference.json')) {
          this.error('The ERPNext reference snapshot must only be loaded by the authenticated endpoint.');
        }
      }
    },
  }],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  base: '/assets/illumenate_lighting/catalog_builder/',
  build: {
    outDir: resolve(import.meta.dirname, '../../illumenate_lighting/public/catalog_builder'),
    emptyOutDir: true,
    lib: {
      entry: resolve(import.meta.dirname, 'src/erp-main.jsx'),
      name: 'IllCatalogBuilder',
      formats: ['iife'],
      fileName: () => 'catalog-builder.js',
    },
    cssCodeSplit: false,
    rollupOptions: { output: { assetFileNames: 'catalog-builder.[ext]' } },
  },
});
