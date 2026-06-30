import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Standalone SPA build for internal preview / Vercel deployment.
// Does NOT produce the IIFE embed bundle — that is handled by vite.config.js.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-preview',
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: 'configurator-ui.js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) return 'configurator-ui.css';
          return 'assets/[name]-[hash][extname]'; // images/fonts etc., fine to keep hashed
        },
        // No lazy-loaded routes in this widget, so collapse everything into
        // one file rather than letting dynamic imports spawn extra chunks.
        inlineDynamicImports: true,
      },
    },
  },
});