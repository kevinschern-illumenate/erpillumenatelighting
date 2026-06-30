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
        chunkFileNames: 'configurator-ui.js', // collapses into entry, see manualChunks below
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) return 'configurator-ui.css';
          return 'assets/[name]-[hash][extname]';
        },
        manualChunks: undefined, // force a single JS file, no dynamic-import splitting
      },
    },
  },
});