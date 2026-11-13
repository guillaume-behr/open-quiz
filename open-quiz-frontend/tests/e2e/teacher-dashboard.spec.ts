import { expect, test, type Request } from "./fixtures"
import { teacher, mockTeacherApi } from "./teacher-api"

test("restores a teacher session and displays their classes", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("button", { name: "Log out" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("link", { name: "Homepage" })
    ).toHaveCount(0)
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()
    await expect(page.getByText(/Grade 8/).last()).toBeVisible()
    await expect
        .poll(
            () =>
                requests
                    .find((request) =>
                        request.url().includes("/api/classes/grade-levels")
                    )
                    ?.headers()["authorization"]
        )
        .toBe("Bearer teacher-access-token")
})

test("teacher dashboard does not overflow on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    await expect(page.getByRole("button", { name: "New class" })).toBeVisible()
    await expect
        .poll(() =>
            page.evaluate(() => ({
                viewport: document.documentElement.clientWidth,
                content: document.documentElement.scrollWidth,
            }))
        )
        .toEqual({ viewport: 390, content: 390 })
})

test("teacher can switch between all dashboard sections", async ({ page }) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()

    for (const section of [
        "Exam quizzes",
        "Training",
        "Question banks",
        "Results",
    ] as const) {
        await page.getByRole("button", { name: section, exact: true }).click()
        await expect(
            page.getByRole("heading", {
                name: section,
                exact: true,
                level: 2,
            })
        ).toBeVisible()
        await expect(
            page.getByRole("button", { name: section, exact: true })
        ).toHaveAttribute("aria-current", "page")
    }
})

test("teacher filters student accounts and classes from side panels", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")

    await page.getByRole("button", { name: "Students", exact: true }).click()
    await page.getByRole("combobox", { name: "Class" }).selectOption("11")
    await page
        .getByRole("combobox", { name: "Account status" })
        .selectOption("true")
    await expect
        .poll(() =>
            requests.some((request) => {
                const url = new URL(request.url())
                return (
                    url.pathname === "/api/students" &&
                    url.searchParams.get("class_id") === "11" &&
                    url.searchParams.get("is_active") === "true"
                )
            })
        )
        .toBe(true)

    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await page
        .getByRole("combobox", { name: "Grade level" })
        .selectOption("Grade 8")
    await expect
        .poll(() =>
            requests.some((request) => {
                const url = new URL(request.url())
                return (
                    url.pathname === "/api/classes" &&
                    url.searchParams.get("grade_level") === "Grade 8"
                )
            })
        )
        .toBe(true)
})

test("teacher can open class and question-bank creation dialogs", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await expect(page.getByRole("button", { name: "New class" })).toBeVisible()

    await page.getByRole("button", { name: "New class" }).click()
    const classDialog = page.getByRole("dialog", { name: "New class" })
    await expect(classDialog).toBeVisible()
    await expect
        .poll(() =>
            classDialog.evaluate(
                (element) => getComputedStyle(element).transitionDuration
            )
        )
        .not.toBe("0s")
    await expect(
        classDialog.getByRole("combobox", { name: "Class" })
    ).toBeEditable()
    await classDialog.getByLabel("Grade level").selectOption("Grade 8")
    await classDialog
        .getByRole("button", { name: "Delete grade level Grade 8" })
        .click()
    const deleteGradeDialog = page.getByRole("dialog", {
        name: "Delete grade level Grade 8",
    })
    await expect(deleteGradeDialog).toContainText(
        "This action cannot be undone."
    )
    await deleteGradeDialog.getByRole("button", { name: "Cancel" }).click()
    await expect(deleteGradeDialog).toBeHidden()
    await expect(classDialog).toBeVisible()
    await classDialog.getByRole("button", { name: "Cancel" }).click()

    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page.getByRole("button", { name: "New question bank" }).click()
    await expect(
        page.getByRole("dialog", { name: "New question bank" })
    ).toBeVisible()
    await expect(page.getByLabel("Question bank title")).toBeEditable()
})

test("teacher can sign out and return to the login form", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Log out" }).click()

    await expect(page).toHaveURL(/\/teacher\/login$/)
    await expect(page.getByLabel("Username")).toBeVisible()
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/auth/logout" &&
                request.method() === "POST"
        )
    ).toBe(true)
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-refresh-proof")
            )
        )
        .toBeNull()
})

function refreshRequests(requests: Request[]) {
    return requests.filter(
        (request) => new URL(request.url()).pathname === "/api/auth/refresh"
    ).length
}

test("signing in restores the session once, not again on the dashboard or a language change", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/login")
    await expect(page).toHaveURL(/\/teacher\/dashboard$/)
    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()

    for (const section of ["Classes", "Results", "Students"] as const)
        await page.getByRole("button", { name: section, exact: true }).click()
    await page.getByRole("button", { name: "Change language" }).click()
    await page.getByRole("menuitemradio", { name: "Français" }).click()
    await expect(
        page.getByRole("heading", { name: "Bienvenue, Ada Lovelace" })
    ).toBeVisible()

    expect(refreshRequests(requests)).toBe(1)
})

test("a teacher opening the admin page stays signed in on their dashboard", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/admin/dashboard")

    await expect(page).toHaveURL(/\/teacher\/dashboard$/)
    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()
    expect(
        requests.filter(
            (request) => new URL(request.url()).pathname === "/api/auth/logout"
        )
    ).toEqual([])
})

test("an expired session takes the teacher back to the login form", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()

    // From now on the server refuses the access token and its renewal.
    await page.route("**/api/quizzes/sessions/results**", (route) =>
        route.fulfill({ status: 401, json: {} })
    )
    await page.route("**/api/auth/refresh", (route) =>
        route.fulfill({ status: 401, json: {} })
    )
    await page.getByRole("button", { name: "Results", exact: true }).click()

    await expect(page).toHaveURL(/\/teacher\/login$/)
    await expect(
        page.getByText("Your session has expired. Sign in again to continue.")
    ).toBeVisible()
})

test("names with apostrophes and ampersands are shown as typed", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.route("http://127.0.0.1:4173/api/users/me", (route) =>
        route.fulfill({
            json: { ...teacher, display_name: "D'Artagnan & Q<A>" },
        })
    )
    await page.goto("/teacher/dashboard")
    await expect(
        page.getByRole("heading", { name: "Welcome, D'Artagnan & Q<A>" })
    ).toBeVisible()
})

test("the dashboard section lives in the URL, across reloads and Back", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    await expect(page).toHaveURL(/[?&]section=exam-quizzes\b/)

    await page.reload()
    await expect(
        page.getByRole("button", { name: "Exam quizzes", exact: true })
    ).toHaveAttribute("aria-current", "page")

    await page.goBack()
    await expect(page).toHaveURL(/[?&]section=classes\b/)
    await expect(
        page.getByRole("button", { name: "Classes", exact: true })
    ).toHaveAttribute("aria-current", "page")

    await page.goto("/teacher/dashboard?section=unknown")
    await expect(
        page.getByRole("button", { name: "Students", exact: true })
    ).toHaveAttribute("aria-current", "page")
})
