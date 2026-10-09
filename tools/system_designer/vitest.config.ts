import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['app/src/**/*.test.{ts,tsx}', 'packages/*/src/**/*.test.ts', 'packages/*/test/**/*.test.ts'],
  },
});
