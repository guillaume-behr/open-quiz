import { expect, test } from "./fixtures"

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        localStorage.setItem("vite-ui-theme", "light")
    })
    await page.goto("/student/login")
})

test("theme selection is applied and persisted", async ({ page }) => {
    await page.getByRole("button", { name: "Change theme" }).click()
    await page.getByRole("menuitem", { name: "Dark" }).click()

    await expect(page.locator("html")).toHaveClass(/dark/)
    await expect
        .poll(() => page.evaluate(() => localStorage.getItem("vite-ui-theme")))
        .toBe("dark")
})

test("language selection updates the interface and document direction", async ({
    page,
}) => {
    await page.getByRole("button", { name: "Change language" }).click()
    await page.getByRole("menuitem", { name: "العربية" }).click()

    await expect(
        page.getByRole("heading", { name: "مساحة الطالب" })
    ).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl")
    await expect
        .poll(() => page.evaluate(() => localStorage.getItem("i18nextLng")))
        .toBe("ar")
})

test("a locale that fails to load falls back to French", async ({ page }) => {
    test.setTimeout(30_000)
    await page.route("**/locales/en/translation.json", (route) => route.abort())
    await page.goto("/no-such-page")
    await expect(
        page.getByRole("heading", { name: "Page introuvable" })
        // i18next retries the failed file a few times before falling back.
    ).toBeVisible({ timeout: 20_000 })
})
