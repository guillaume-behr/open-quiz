import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
    })
})

test("student can open the quiz join form", async ({ page }) => {
    await page.goto("/")

    await expect(
        page.getByRole("heading", { name: "Join a quiz" })
    ).toBeVisible()
    await expect(page.getByLabel("Student ID")).toBeVisible()
    await expect(page.getByLabel("Quiz code")).toBeVisible()
    await expect(
        page.getByRole("button", { name: "Join the quiz" })
    ).toBeEnabled()
})

test("quiz code is normalized and a rejected join shows an error", async ({
    page,
}) => {
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Unknown quiz" }),
        })
    })
    await page.goto("/")

    await page.getByLabel("Student ID").fill("student-1")
    await page.getByLabel("Quiz code").fill("abcd")
    await expect(page.getByLabel("Quiz code")).toHaveValue("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()

    await expect(page.getByRole("alert")).toHaveText(
        "Unknown code, quiz already started, or unable to connect."
    )
})

test("teacher area navigation works without a page reload", async ({
    page,
}) => {
    await page.goto("/")
    await page.getByRole("link", { name: "Teacher area" }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible()
    await expect(page.getByRole("heading").first()).toBeVisible()
})

test("join form remains usable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/")

    const joinButton = page.getByRole("button", { name: "Join the quiz" })
    await expect(joinButton).toBeInViewport()
    await expect(page.getByLabel("Student ID")).toBeEditable()
    await expect(page.getByLabel("Quiz code")).toBeEditable()
})
