import { readFileSync } from "node:fs"
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// package.json is the single source of the interface version shown in the
// footer; the build replaces __APP_VERSION__ with it.
const { version } = JSON.parse(
    readFileSync(path.resolve(__dirname, "package.json"), "utf8")
) as { version: string }

// https://vite.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss()],
    define: {
        __APP_VERSION__: JSON.stringify(version),
    },
    // Pyodide is imported only from a Web Worker, so Vite's initial source
    // scan does not discover it. Pre-bundle it at startup to avoid a runtime
    // dependency-optimization reload that interrupts the first execution.
    optimizeDeps: {
        include: ["pyodide"],
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
    test: {
        // Unit tests only: the Playwright specs under tests/e2e run apart.
        include: ["src/**/*.test.ts"],
    },
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
})
