/* ESLint configuration (ESLint 8 classic config format).
 *
 * `npm run lint` used to be a no-op script with no configuration file behind it.
 * The rule set below is deliberately close to the TypeScript defaults so the
 * check is actionable rather than aspirational.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } },
  plugins: ['@typescript-eslint', 'react-hooks', 'react-refresh'],
  settings: { react: { version: 'detect' } },
  ignorePatterns: ['dist', 'node_modules', 'playwright-report', 'test-results', '*.config.js'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended'],
  rules: {
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/no-explicit-any': 'warn',
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
  overrides: [
    {
      // Hook modules legitimately export both a provider component and the hook
      // that consumes its context; that is not a fast-refresh hazard.
      files: ['src/hooks/*.ts', 'src/hooks/*.tsx'],
      rules: { 'react-refresh/only-export-components': 'off' },
    },
    {
      files: ['src/test/**/*.{ts,tsx}', 'tests/**/*.ts'],
      env: { browser: true, node: true },
      rules: { 'no-console': 'off', '@typescript-eslint/no-explicit-any': 'off' },
    },
  ],
};
