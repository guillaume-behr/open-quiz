import { cspTest as test, expect } from "../fixtures"

// Runs against the built bundle served by the frontend image (Caddy), with
// the real API behind it: no request is mocked, and the page's Content
// Security Policy and headers are the production ones.

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
    })
})

test("the home page loads its scripts under the Content Security Policy", async ({
    page,
}) => {
    await page.goto("/")
    await expect(page).toHaveURL(/\/student\/login$/)
    await expect(
        page.getByRole("heading", { name: "Student space" })
    ).toBeVisible()
})

test("a deep link is served the application", async ({ page }) => {
    const response = await page.goto("/teacher/dashboard")
    expect(response?.status()).toBe(200)
    await expect(page.getByLabel("Username")).toBeVisible()
})

test("an unknown page shows the not-found page", async ({ page }) => {
    await page.goto("/no-such-page")
    await expect(
        page.getByRole("heading", { name: "Page not found" })
    ).toBeVisible()
})

test("a refused student sign-in goes through the real API", async ({
    page,
}) => {
    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("nobody")
    await page.getByLabel("Password", { exact: true }).fill("not-a-password")
    const response = page.waitForResponse("**/api/student-auth/login")
    await page.getByRole("button", { name: "Sign in" }).click()
    expect((await response).status()).toBeGreaterThanOrEqual(400)
    await expect(page.getByRole("alert")).toBeVisible()
})

test("a dark theme is applied before the first paint", async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("vite-ui-theme", "dark")
        document.addEventListener("DOMContentLoaded", () => {
            ;(window as unknown as { darkAtLoad: boolean }).darkAtLoad =
                document.documentElement.classList.contains("dark")
        })
    })
    await page.goto("/student/login")
    expect(
        await page.evaluate(
            () => (window as unknown as { darkAtLoad: boolean }).darkAtLoad
        )
    ).toBe(true)
})
