import js from '@eslint/js';
import hooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const noRawHtml = {
  selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
  message: 'Render text through React; raw HTML is not allowed in the System Designer (plan 15.6).',
};

export default tseslint.config(
  { ignores: ['node_modules', 'coverage', 'playwright-report', 'test-results', 'vendor', 'reference'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { 'react-hooks': hooks },
    rules: {
      ...hooks.configs.recommended.rules,
      'no-restricted-syntax': ['error', noRawHtml],
      'no-restricted-properties': [
        'error',
        { property: 'innerHTML', message: 'Use DOM text APIs or React; innerHTML is not allowed.' },
        { property: 'outerHTML', message: 'Use DOM text APIs or React; outerHTML is not allowed.' },
      ],
    },
  },
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: globals.node },
  },
  {
    // Engine purity (plan H1 rule 4): no React, DOM, storage or network in the pure packages.
    files: ['packages/{core-schemas,data,engine,drawing,serializers}/src/**/*.ts'],
    ignores: ['**/*.test.ts'],
    languageOptions: { globals: {} },
    rules: {
      'no-restricted-imports': [
        'error',
        { patterns: [{ group: ['react', 'react-dom', 'react/*', 'react-dom/*', 'dexie', 'zustand', 'zustand/*'], message: 'Pure packages must not depend on UI or storage.' }] },
      ],
      'no-restricted-globals': [
        'error',
        ...['window', 'document', 'navigator', 'localStorage', 'sessionStorage', 'indexedDB', 'fetch', 'XMLHttpRequest', 'WebSocket'].map(
          (name) => ({ name, message: 'Pure packages must not touch the DOM, storage or network.' }),
        ),
      ],
    },
  },
);
