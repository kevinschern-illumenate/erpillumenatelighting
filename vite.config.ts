import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Prebundle lazy export dependencies so the first PDF download cannot trigger a dev reload.
  optimizeDeps: {
    include: [
      '@cantoo/pdf-lib',
      '@cantoo/fontkit',
      'jszip',
      'papaparse',
      'ag-grid-community',
      'ag-grid-react',
    ],
  },
  server: { proxy: { '/api/erp': { target: 'http://127.0.0.1:8787', changeOrigin: true } } },
});
