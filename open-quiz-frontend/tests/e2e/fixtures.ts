import { test as base, expect } from "@playwright/test"

export { expect }
export type { Page, Request, Route, WebSocketRoute } from "@playwright/test"

/**
 * Fails the test on any Content Security Policy violation, whichever server
 * sends the page.
 */
export const cspTest = base.extend<{ cspGuard: void }>({
    cspGuard: [
        async ({ page }, use) => {
            const violations: string[] = []
            await page.addInitScript(() => {
                document.addEventListener(
                    "securitypolicyviolation",
                    (event) => {
                        console.error(
                            `CSP violation: ${event.violatedDirective} ${event.blockedURI}`
                        )
                    }
                )
            })
            page.on("console", (message) => {
                if (
                    message.type() === "error" &&
                    /Content Security Policy|CSP violation/i.test(
                        message.text()
                    )
                )
                    violations.push(message.text())
            })
            await use()
            expect(violations, "Content Security Policy violations").toEqual([])
        },
        { auto: true },
    ],
})

/**
 * Every dev-server spec imports `test` from here. On top of the CSP guard,
 * an API call that no spec mocks fails its test: the catch-all below is
 * registered first, so a spec's own routes, registered later, still win.
 * A spec that wants the real upstream calls `page.unrouteAll()`.
 */
export const test = cspTest.extend<{ apiGuard: void }>({
    apiGuard: [
        async ({ page }, use) => {
            const unexpected: string[] = []
            await page.route(
                (url) => url.pathname.startsWith("/api/"),
                async (route) => {
                    const request = route.request()
                    unexpected.push(
                        `${request.method()} ${new URL(request.url()).pathname}`
                    )
                    await route.fulfill({
                        status: 501,
                        json: { detail: "Not mocked by this test" },
                    })
                }
            )
            await use()
            expect(unexpected, "API calls this test does not mock").toEqual([])
        },
        { auto: true },
    ],
})
