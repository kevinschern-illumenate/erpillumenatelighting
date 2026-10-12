import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    // The riser's heaviest layout cases take ~8 s on a shared runner; the 5 s default is too tight.
    testTimeout: 30_000,
    include: ['app/src/**/*.test.{ts,tsx}', 'packages/*/src/**/*.test.ts', 'packages/*/test/**/*.test.ts'],
  },
});
