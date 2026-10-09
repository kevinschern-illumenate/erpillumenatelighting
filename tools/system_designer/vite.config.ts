import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Frappe Cloud runs `bench build`, not Vite, so the build output is committed (the Product Finder
// pattern). Entry names are stable for the portal template; lazy chunks may be hashed.
export const OUT_DIR = resolve(import.meta.dirname, '../../illumenate_lighting/public/system_designer');

export default defineConfig({
  root: resolve(import.meta.dirname, 'app'),
  base: '/assets/illumenate_lighting/system_designer/',
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: OUT_DIR,
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    rollupOptions: {
      input: resolve(import.meta.dirname, 'app/src/main.tsx'),
      output: {
        format: 'es',
        entryFileNames: 'designer.js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (asset) =>
          asset.names?.some((name) => name.endsWith('.css')) ? 'designer.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
});
