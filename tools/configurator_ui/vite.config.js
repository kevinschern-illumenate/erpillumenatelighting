import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// Two build modes:
//   npm run dev   -> serves index.html (dev host with #ill-configurator-root)
//   npm run build -> produces an embeddable IIFE bundle for Webflow that
//                    exposes window.IllConfigurator.mount(el, opts).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    open: true,
  },
  build: {
    // Library / embed target. The IIFE bundle inlines React + CSS so it can be
    // dropped onto a Webflow page with a single <script> tag.
    lib: {
      entry: resolve(__dirname, 'src/main.jsx'),
      name: 'IllConfigurator',
      formats: ['iife'],
      fileName: () => 'ill-configurator.js',
    },
    cssCodeSplit: false,
    // Keep React bundled inside the IIFE so the embed is self-contained.
    rollupOptions: {
      output: {
        // Emit a predictable CSS filename for the embed host to reference.
        assetFileNames: 'ill-configurator.[ext]',
      },
    },
  },
});
