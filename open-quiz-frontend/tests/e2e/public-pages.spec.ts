import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
    })
    await page.route("**/api/public-information", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                host: {
                    name: "Example host",
                    address: "Paris",
                    phone: "+33 1 23 45 67 89",
                },
                privacy: {
                    controller_name: "Example school",
                    controller_contact: "privacy@example.test",
                    dpo_contact: "dpo@example.test",
                    legal_basis: "Public-interest task",
                    recipients: "Authorized school staff",
                    teacher_data_retention: "Until account deletion",
                    student_data_retention: "Until class deletion",
                    security_log_retention: "One year",
                    quiz_result_retention_days: 365,
                    training_result_retention_days: 365,
                    problem_report_retention_days: 90,
                },
                cookies: { authentication_max_age_days: 30 },
                accessibility: {
                    contact: "accessibility@example.test",
                    scheme_url: "https://example.test/scheme",
                    action_plan_url: "https://example.test/action-plan",
                },
            }),
        })
    })
})

test("legal notice reports unavailable instance information", async ({
    page,
}) => {
    await page.route("**/api/public-information", async (route) => {
        await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Unavailable" }),
        })
    })

    await page.goto("/legal-notice")

    await expect(
        page.getByRole("heading", { name: "Legal notice" })
    ).toBeVisible()
    await expect(page).toHaveTitle("Open Quiz | Legal notice")
    await expect(page.getByRole("alert")).toContainText(
        "Information specific to this instance is unavailable."
    )
})

test("footer links open each public information page", async ({ page }) => {
    await page.goto("/student/login")

    await expect(page.locator("footer")).toContainText("0.3.0")

    const destinations = [
        ["Personal data", "/privacy"],
        ["Accessibility statement", "/accessibility"],
        ["Cookie settings", "/cookie-settings"],
    ] as const

    for (const [heading, path] of destinations) {
        await page.goto("/student/login")
        await page.locator(`footer a[href="${path}"]`).click()
        await expect(page).toHaveURL(new RegExp(`${path}$`))
        await expect(page.getByRole("heading", { name: heading })).toBeVisible()
    }
})

test("problem report ignores a network-path source", async ({ page }) => {
    await page.goto("/report-a-problem")
    await page.evaluate(() => {
        history.replaceState({ usr: { from: "//example.test/phishing" } }, "")
        dispatchEvent(new PopStateEvent("popstate", { state: history.state }))
    })

    await expect(page.getByText("/", { exact: true })).toBeVisible()
})

test("unsafe configured external URLs are not rendered as links", async ({
    page,
}) => {
    await page.route("**/api/public-information", async (route) => {
        await route.fulfill({
            json: {
                host: {
                    name: "Example host",
                    address: "Paris",
                    phone: "+33 1 23 45 67 89",
                },
                privacy: {
                    controller_name: "Example school",
                    controller_contact: "privacy@example.test",
                    dpo_contact: "dpo@example.test",
                    legal_basis: "Public-interest task",
                    recipients: "Authorized school staff",
                    teacher_data_retention: "Until account deletion",
                    student_data_retention: "Until class deletion",
                    security_log_retention: "One year",
                    quiz_result_retention_days: 365,
                    training_result_retention_days: 365,
                    problem_report_retention_days: 90,
                },
                cookies: { authentication_max_age_days: 30 },
                accessibility: {
                    contact: "accessibility@example.test",
                    scheme_url: "javascript:alert(document.cookie)",
                    action_plan_url: "https://example.test/action-plan",
                },
            },
        })
    })

    await page.goto("/accessibility")

    await expect(
        page.getByRole("link", { name: "View the multi-year scheme" })
    ).toHaveCount(0)
    await expect(
        page.getByText("View the multi-year scheme", { exact: true })
    ).toBeVisible()
    await expect(
        page.getByRole("link", { name: "View the action plan" })
    ).toHaveAttribute("href", "https://example.test/action-plan")
})

test("problem report preserves its source page and sends the form", async ({
    page,
}) => {
    let requestBody: unknown
    await page.route("**/api/problem-reports", async (route) => {
        requestBody = route.request().postDataJSON()
        await route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify({
                id: 1,
                message: "The page stopped responding",
                page_path: "/privacy",
                created_at: "2026-08-01T10:00:00Z",
            }),
        })
    })

    await page.goto("/privacy")
    await page.getByRole("link", { name: "Report a problem" }).click()
    await expect(page.getByText("/privacy", { exact: true })).toBeVisible()

    await page.getByLabel("Your message").fill("The page stopped responding")
    await page.getByRole("button", { name: "Send report" }).click()

    await expect(page.getByRole("status")).toHaveText(
        /The report was sent to the administrator\./
    )
    expect(requestBody).toEqual({
        message: "The page stopped responding",
        page_path: "/privacy",
    })
    await expect(page.getByLabel("Your message")).toHaveValue("")
})

test("problem report displays an API error", async ({ page }) => {
    await page.route("**/api/problem-reports", async (route) => {
        await route.fulfill({
            status: 429,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Too many reports" }),
        })
    })
    await page.goto("/report-a-problem")
    await page.getByLabel("Your message").fill("A useful report")
    await page.getByRole("button", { name: "Send report" }).click()

    await expect(page.getByRole("alert")).toHaveText(
        "Unable to send the report."
    )
})

test("cookie settings clear local quiz and preference data", async ({
    page,
}) => {
    await page.addInitScript(() => {
        localStorage.setItem("vite-ui-theme", "dark")
        sessionStorage.setItem(
            "open-quiz-student-access-token",
            "student-token"
        )
        sessionStorage.setItem("open-quiz-student-session", "stored-session")
        sessionStorage.setItem("open-quiz-training-session", "training-session")
        sessionStorage.setItem("open-quiz-refresh-proof", "stored-proof")
    })
    await page.route("**/api/auth/logout", async (route) => {
        await route.fulfill({ status: 204 })
    })
    await page.goto("/cookie-settings")
    await page.getByRole("button", { name: "Clear and sign out" }).click()

    await expect(page.getByRole("status")).toHaveText(
        "Local data and the sign-in session have been cleared."
    )
    await expect
        .poll(() =>
            page.evaluate(() => ({
                language: localStorage.getItem("i18nextLng"),
                theme: localStorage.getItem("vite-ui-theme"),
                studentToken: sessionStorage.getItem(
                    "open-quiz-student-access-token"
                ),
                quiz: sessionStorage.getItem("open-quiz-student-session"),
                training: sessionStorage.getItem("open-quiz-training-session"),
                proof: sessionStorage.getItem("open-quiz-refresh-proof"),
            }))
        )
        .toEqual({
            language: null,
            theme: null,
            studentToken: null,
            quiz: null,
            training: null,
            proof: null,
        })
})
