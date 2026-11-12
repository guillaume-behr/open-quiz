import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
    testDir: "./tests/e2e",
    // Run by playwright.production.config.ts against the built image.
    testIgnore: "production/**",
    fullyParallel: true,
    forbidOnly: Boolean(process.env.CI),
    // Retries keep a trace of a failure, but a test that only passes on a
    // retry still fails the run: otherwise a flaky test stays green.
    retries: process.env.CI ? 2 : 0,
    failOnFlakyTests: Boolean(process.env.CI),
    workers: process.env.CI ? 1 : undefined,
    reporter: process.env.CI ? "github" : "list",
    use: {
        baseURL: "http://127.0.0.1:4173",
        locale: "en-US",
        trace: "on-first-retry",
    },
    projects: [
        {
            name: "chromium",
            use: { ...devices["Desktop Chrome"] },
        },
    ],
    webServer: [
        {
            command: "node scripts/network-test-server.mjs",
            url: "http://127.0.0.1:4180/healthz",
            reuseExistingServer: false,
        },
        {
            command:
                "VITE_API_PROXY_TARGET=http://127.0.0.1:4180 pnpm dev --host 127.0.0.1 --port 4173",
            url: "http://127.0.0.1:4173",
            reuseExistingServer: false,
        },
    ],
})
