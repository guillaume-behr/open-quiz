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
    test: {
        // Unit tests only: the Playwright specs under tests/e2e run apart.
        include: ["src/**/*.test.ts"],
        // The unit tests share no global state, so workers are reused across
        // files instead of spawning one per file.
        isolate: false,
    },
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
})
