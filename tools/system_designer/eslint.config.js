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
);
