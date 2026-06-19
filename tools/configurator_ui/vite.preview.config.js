import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Standalone SPA build for internal preview / Vercel deployment.
// Does NOT produce the IIFE embed bundle — that is handled by vite.config.js.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-preview',
  },
});
