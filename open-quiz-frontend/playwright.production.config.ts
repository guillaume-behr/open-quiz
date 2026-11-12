import { defineConfig, devices } from "@playwright/test"

// A smoke subset against the built frontend image (Caddy) and the real API:
// `docker compose up` first, then `pnpm test:e2e:production`. The CI
// containers job runs it on the images it has just built.
export default defineConfig({
    testDir: "./tests/e2e/production",
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 2 : 0,
    failOnFlakyTests: Boolean(process.env.CI),
    workers: 1,
    reporter: process.env.CI ? "github" : "list",
    use: {
        baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:7800",
        locale: "en-US",
        // What the TLS edge proxy in front of Caddy sends: without it, the
        // API redirects plain HTTP to HTTPS.
        extraHTTPHeaders: { "X-Forwarded-Proto": "https" },
        trace: "on-first-retry",
    },
    projects: [
        { name: "chromium", use: { ...devices["Desktop Chrome"] } },
        { name: "webkit", use: { ...devices["Desktop Safari"] } },
        { name: "mobile", use: { ...devices["Pixel 7"] } },
    ],
})
