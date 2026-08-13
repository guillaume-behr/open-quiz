import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        sessionStorage.clear()
    })
    await page.route("**/api/auth/refresh", async (route) => {
        await route.fulfill({ status: 401, body: "{}" })
    })
})

test("teacher sees a login error returned by the API", async ({ page }) => {
    await page.route("**/api/auth/login", async (route) => {
        await route.fulfill({
            status: 401,
            contentType: "application/json",
            body: JSON.stringify({
                detail: { code: "AUTH_INVALID_CREDENTIALS" },
            }),
        })
    })
    await page.goto("/teacher/login")

    await page.getByLabel("Username").fill("teacher")
    await page.getByLabel("Password", { exact: true }).fill("incorrect")
    await page.evaluate(() =>
        sessionStorage.setItem("open-quiz-refresh-proof", "existing-proof")
    )
    expect(
        await page.evaluate(() =>
            sessionStorage.getItem("open-quiz-refresh-proof")
        )
    ).toBe("existing-proof")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page.getByRole("alert")).toHaveText(
        "Incorrect ID or password."
    )
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-refresh-proof")
            )
        )
        .toBe("existing-proof")
})

test("successful credentials advance to two-factor authentication", async ({
    page,
}) => {
    await page.route("**/api/auth/login", async (route) => {
        expect(route.request().postDataJSON()).toEqual({
            username: "teacher",
            password: "secret-password",
            audience: "professor",
        })
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                status: "code_required",
                challenge_token: "challenge-token",
            }),
        })
    })
    await page.goto("/teacher/login")

    await page.getByLabel("Username").fill("teacher")
    await page.getByLabel("Password", { exact: true }).fill("secret-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(
        page.getByRole("heading", { name: "Two-factor authentication" })
    ).toBeVisible()
    await expect(page.getByLabel("Authentication code")).toBeFocused()
    await page.getByRole("button", { name: "Back to sign in" }).click()
    await expect(page.getByLabel("Username")).toBeVisible()
})

test("invalid two-factor code returns to an actionable verification form", async ({
    page,
}) => {
    await page.route("**/api/auth/login", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                status: "verification_required",
                challenge_token: "challenge-token",
                secret: null,
                provisioning_uri: null,
            }),
        })
    })
    await page.route("**/api/auth/2fa/verify", async (route) => {
        expect(route.request().postDataJSON()).toEqual({
            challenge_token: "challenge-token",
            code: "123456",
        })
        await route.fulfill({ status: 401, body: "{}" })
    })
    await page.goto("/teacher/login")
    await page.getByLabel("Username").fill("teacher")
    await page.getByLabel("Password", { exact: true }).fill("secret-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByLabel("Authentication code").fill("123456")
    await page.getByRole("button", { name: "Continue" }).click()

    await expect(page.getByRole("alert")).toHaveText(
        "Unable to verify this code."
    )
    await expect(page.getByLabel("Authentication code")).toBeEditable()
})
