import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss()],
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
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
})
