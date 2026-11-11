// Lint for the app source (replaces the lint step inside the Create React App build, 2026-11-11). That build
// enforced the craco react-hooks rules; these add react-app's core correctness rules. CI runs
// `yarn lint --max-warnings 0`, as the CRA build failed on any warning there.
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import importPlugin from "eslint-plugin-import";

export default [
  { ignores: ["build/**", "node_modules/**"] },
  {
    files: ["src/**/*.{js,jsx}"],
    // ESLint 8 (inside Create React App) did not report unused disable comments.
    linterOptions: { reportUnusedDisableDirectives: "off" },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.jest, process: "readonly" },
    },
    plugins: { react, "react-hooks": reactHooks, "jsx-a11y": jsxA11y, import: importPlugin },
    settings: { react: { version: "detect" } },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/jsx-no-undef": "error",
      "react/jsx-uses-vars": "warn",
      "react/jsx-uses-react": "warn",
      "react/jsx-no-duplicate-props": "warn",
      "react/no-danger-with-children": "warn",
      "react/no-direct-mutation-state": "warn",
      "react/require-render-return": "error",
      "no-undef": "error",
      "no-unused-vars": ["warn", { args: "none", ignoreRestSiblings: true, caughtErrors: "none" }],
      "no-dupe-keys": "warn",
      "no-dupe-args": "warn",
      "no-duplicate-case": "warn",
      "no-unreachable": "warn",
      "no-const-assign": "warn",
      "no-redeclare": "warn",
      "no-self-assign": "warn",
      "no-use-before-define": ["warn", { functions: false, classes: false, variables: false }],
      "import/first": "error",
      "import/no-anonymous-default-export": "warn",
      "jsx-a11y/alt-text": "warn",
      "jsx-a11y/anchor-is-valid": "warn",
    },
  },
  // Tests run in Node under Jest (require, global), as react-app's jest override allowed.
  { files: ["src/**/*.test.{js,jsx}", "src/testHelpers/**", "src/testFixtures/**"], languageOptions: { globals: { ...globals.node } } },
];
