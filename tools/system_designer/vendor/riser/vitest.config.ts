import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'server/**/*.test.mjs'],
    setupFiles: ['src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: [
        'src/engine/**/*.ts',
        'src/drawing/**/*.ts',
        'src/serializers/**/*.ts',
        'src/features/erp/sync.ts',
        'src/features/library/import.ts',
        'src/state/project-store.ts',
        'src/storage/**/*.ts',
        'src/schemas/**/*.ts',
      ],
      exclude: ['src/**/*.test.ts'],
      reporter: ['text', 'html'],
    },
  },
});
