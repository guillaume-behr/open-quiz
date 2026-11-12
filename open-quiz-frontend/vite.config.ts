import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// package.json is the single source of the interface version shown in the
// footer; the build replaces __APP_VERSION__ with it.
const { version } = JSON.parse(
    readFileSync(new URL("package.json", import.meta.url), "utf8")
) as { version: string }

// The Pyodide runtime is served from /pyodide/<version>/
// (scripts/copy-pyodide.mjs), so that an update changes its address.
const { version: pyodideVersion } = JSON.parse(
    readFileSync(
        new URL("node_modules/pyodide/package.json", import.meta.url),
        "utf8"
    )
) as { version: string }

// https://vite.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss()],
    define: {
        __APP_VERSION__: JSON.stringify(version),
        __PYODIDE_VERSION__: JSON.stringify(pyodideVersion),
    },
    server: {
        proxy: {
            "/api": {
                target:
                    process.env.VITE_API_PROXY_TARGET ??
                    "http://localhost:8000",
                ws: true,
            },
        },
    },
    build: {
        rolldownOptions: {
            output: {
                // Libraries every page needs get stable, named chunks that
                // stay cached across releases of the app's own code. Prism
                // is only needed by the pages that show code.
                codeSplitting: {
                    groups: [
                        {
                            name: "react",
                            test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
                        },
                        {
                            name: "router",
                            test: /node_modules[\\/]react-router[\\/]/,
                        },
                        {
                            name: "i18n",
                            test: /node_modules[\\/](i18next[^\\/]*|react-i18next)[\\/]/,
                        },
                        {
                            // Before Prism, which would otherwise take clsx
                            // along and be preloaded by every page.
                            name: "class-names",
                            test: /node_modules[\\/](clsx|tailwind-merge|class-variance-authority)[\\/]/,
                        },
                        {
                            name: "prism",
                            test: /node_modules[\\/]prism-react-renderer[\\/]/,
                        },
                    ],
                },
            },
        },
    },
    test: {
        // Unit tests only: the Playwright specs under tests/e2e run apart.
        include: ["src/**/*.test.{ts,tsx}"],
        // Files switch to jsdom and touch localStorage, timers and globals:
        // each runs in a fresh context rather than trusting every file to
        // clean up after itself.
        isolate: true,
        clearMocks: true,
        restoreMocks: true,
        unstubGlobals: true,
        setupFiles: ["src/test/setup.ts"],
        coverage: {
            provider: "v8",
            include: ["src/**/*.{ts,tsx}"],
            exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/**/*.d.ts"],
            reporter: ["text-summary", "lcov"],
            thresholds: {
                // A floor under the whole frontend, to raise as tests are
                // added: never lower it.
                lines: 32,
                statements: 32,
                functions: 25,
                branches: 23,
                // The API client, live updates, hooks and the exam logic
                // stay covered on their own.
                ...Object.fromEntries(
                    [
                        "src/api/client.ts",
                        "src/api/quizzes.ts",
                        "src/lib/live-updates.ts",
                        "src/hooks/use-async-action.ts",
                        "src/hooks/use-object-url.ts",
                        "src/hooks/use-paged-list.ts",
                        "src/hooks/use-resource.ts",
                        "src/components/student-quiz/use-quiz-monitoring.ts",
                        "src/components/student-quiz/use-quiz-translation.ts",
                        "src/components/quizzes/print-quiz.ts",
                        "src/components/classes/print-credentials.ts",
                        "src/components/quizzes/use-live-quiz-sessions.ts",
                        "src/components/quizzes/session-display.ts",
                        "src/components/question-banks/use-bank-transfer.ts",
                        "src/components/question-banks/python-runner.ts",
                    ].map((file) => [file, { lines: 90, statements: 90 }])
                ),
            },
        },
    },
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
})
