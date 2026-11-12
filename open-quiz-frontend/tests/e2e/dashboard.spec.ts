import { expect, test } from "./fixtures"

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        sessionStorage.clear()
    })
    await page.route("**/api/auth/refresh", async (route) => {
        await route.fulfill({ status: 401, body: "{}" })
    })
})

test("temporary refresh failures preserve the recoverable session", async ({
    page,
}) => {
    await page.addInitScript(() => {
        sessionStorage.setItem("open-quiz-refresh-proof", "recoverable-proof")
    })
    await page.route("**/api/auth/refresh", async (route) => {
        await route.fulfill({ status: 503, body: "{}" })
    })

    await page.goto("/teacher/dashboard")

    await expect(page.getByLabel("Username")).toBeVisible()
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-refresh-proof")
            )
        )
        .toBe("recoverable-proof")
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
                status: "verification_required",
                challenge_token: "challenge-token",
                secret: null,
                provisioning_uri: null,
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
            timezone: expect.any(String),
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

test("a browser trusted today signs in without a two-factor code", async ({
    page,
}) => {
    const requestedPaths: string[] = []
    let meAuthorization: string | null = null
    await page.route(
        /^http:\/\/127\.0\.0\.1:4173\/api\/(?!auth\/refresh)/,
        async (route) => {
            const path = new URL(route.request().url()).pathname
            requestedPaths.push(path)
            if (path === "/api/auth/login") {
                return route.fulfill({
                    json: {
                        status: "authenticated",
                        access_token: "teacher-access-token",
                        refresh_proof: "teacher-proof",
                        token_type: "bearer",
                    },
                })
            }
            if (path === "/api/users/me") {
                meAuthorization = await route
                    .request()
                    .headerValue("authorization")
                return route.fulfill({
                    json: {
                        id: 7,
                        username: "teacher",
                        display_name: "Ada Lovelace",
                        is_admin: false,
                        is_active: true,
                        created_at: "2026-01-01T00:00:00Z",
                    },
                })
            }
            return route.fulfill({
                json: [],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": "0",
                },
            })
        }
    )
    await page.goto("/teacher/login")
    await page.getByLabel("Username").fill("teacher")
    await page.getByLabel("Password", { exact: true }).fill("secret-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page).toHaveURL(/\/teacher\/dashboard$/)
    await expect(page.getByLabel("Authentication code")).toHaveCount(0)
    expect(requestedPaths).not.toContain("/api/auth/2fa/verify")
    expect(meAuthorization).toBe("Bearer teacher-access-token")
})
