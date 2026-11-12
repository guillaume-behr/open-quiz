import js from "@eslint/js"
import globals from "globals"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"
import tseslint from "typescript-eslint"
import { defineConfig, globalIgnores } from "eslint/config"

export default defineConfig([
    globalIgnores([
        "dist",
        "coverage",
        "test-results",
        "playwright-report",
        // A git-ignored local override of playwright.config.ts.
        "playwright.local.config.ts",
    ]),
    {
        files: ["**/*.{ts,tsx}"],
        extends: [
            js.configs.recommended,
            tseslint.configs.recommendedTypeChecked,
        ],
        languageOptions: {
            parserOptions: {
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
    },
    {
        files: ["src/**/*.{ts,tsx}"],
        extends: [
            reactHooks.configs.flat.recommended,
            reactRefresh.configs.vite,
        ],
        languageOptions: { globals: globals.browser },
    },
    {
        // Assertions read mocked methods off their objects
        // (expect(window.print).toHaveBeenCalled()), which this rule takes
        // for unbound calls.
        files: ["src/**/*.test.{ts,tsx}"],
        rules: { "@typescript-eslint/unbound-method": "off" },
    },
    {
        // Node-side code: build scripts, configs and the Playwright specs,
        // whose callbacks passed to page.evaluate run in the browser.
        files: ["scripts/**/*.mjs", "*.config.{js,ts}", "tests/e2e/**/*.ts"],
        languageOptions: { globals: { ...globals.node, ...globals.browser } },
    },
    {
        // Fakes of async browser APIs (the Translator) return plain values
        // from async functions, as the real ones would resolve them.
        files: ["tests/e2e/**/*.ts"],
        rules: { "@typescript-eslint/require-await": "off" },
    },
    {
        files: ["scripts/**/*.mjs", "eslint.config.js"],
        extends: [js.configs.recommended],
        languageOptions: { globals: globals.node },
    },
    {
        // Loaded as a classic script before the bundle.
        files: ["public/**/*.js"],
        extends: [js.configs.recommended],
        languageOptions: { sourceType: "script", globals: globals.browser },
    },
])
