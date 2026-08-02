import { expect, test, type Page, type Request } from "@playwright/test"

const teacher = {
    id: 7,
    username: "ada",
    display_name: "Ada Lovelace",
    is_admin: false,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
}

const existingClass = {
    id: 11,
    name: "Class 8B",
    grade_level: "Grade 8",
    student_count: 24,
    completed_quiz_count: 3,
    students: [],
    created_at: "2026-01-02T00:00:00Z",
}

async function mockTeacherApi(page: Page) {
    const requests: Request[] = []
    let classes = [existingClass]
    let trainingBankIds: number[] = []
    const studentAccount = {
        id: 41,
        identifier: "alex-8b",
        display_name: "Alex Example",
        is_active: true,
        class_id: 11,
        class_name: "Class 8B",
        created_at: "2026-01-03T00:00:00Z",
    }
    const bank = {
        id: 21,
        grade_level: "Grade 8",
        chapter: "Matter and energy",
        created_at: "2026-01-03T00:00:00Z",
        question_count: 30,
        easy_question_count: 10,
        medium_question_count: 10,
        hard_question_count: 10,
    }
    const otherGradeBank = {
        ...bank,
        id: 22,
        grade_level: "Grade 9",
        chapter: "Advanced matter",
    }
    let quizzes = [
        {
            id: 31,
            mode: "exam",
            title: "Science checkpoint",
            source_language: "en",
            question_count: 10,
            duration_seconds: 1800,
            allow_previous_questions: false,
            same_questions_for_all: true,
            easy_question_count: 3,
            medium_question_count: 4,
            hard_question_count: 3,
            easy_points: 6,
            medium_points: 10,
            hard_points: 12,
            question_banks: [bank],
            created_at: "2026-01-04T00:00:00Z",
        },
    ]

    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        sessionStorage.setItem("open-quiz-refresh-proof", "initial-proof")
    })
    await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
        const request = route.request()
        const url = new URL(request.url())
        requests.push(request)

        if (url.pathname === "/api/auth/refresh") {
            return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    access_token: "teacher-access-token",
                    refresh_proof: "rotated-proof",
                }),
            })
        }
        if (url.pathname === "/api/users/me") {
            return route.fulfill({ json: teacher })
        }
        if (url.pathname === "/api/grade-levels") {
            return route.fulfill({ json: [{ id: 1, name: "Grade 8" }] })
        }
        if (url.pathname === "/api/classes" && request.method() === "POST") {
            const body = request.postDataJSON() as {
                name: string
                grade_level: string
            }
            const created = {
                ...existingClass,
                id: 12,
                name: body.name,
                grade_level: body.grade_level,
                student_count: 0,
                completed_quiz_count: 0,
            }
            classes = [...classes, created]
            return route.fulfill({ status: 201, json: created })
        }
        if (url.pathname === "/api/classes") {
            return route.fulfill({
                json: classes,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": String(classes.length),
                },
            })
        }
        if (url.pathname === "/api/question-banks") {
            return route.fulfill({
                json: [bank, otherGradeBank],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "100",
                    "X-Total-Count": "2",
                },
            })
        }
        if (url.pathname === "/api/students") {
            return route.fulfill({
                json: [studentAccount],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "12",
                    "X-Total-Count": "1",
                },
            })
        }
        if (url.pathname === "/api/quizzes/sessions/active") {
            return route.fulfill({ json: [] })
        }
        if (url.pathname === "/api/quizzes/sessions/results") {
            return route.fulfill({
                json: [],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": "0",
                },
            })
        }
        if (
            url.pathname ===
            "/api/quizzes/training/classes/11/question-banks"
        ) {
            if (request.method() === "PUT") {
                trainingBankIds = (
                    request.postDataJSON() as { question_bank_ids: number[] }
                ).question_bank_ids
            }
            return route.fulfill({
                json: trainingBankIds.includes(bank.id) ? [bank] : [],
            })
        }
        if (url.pathname === "/api/quizzes") {
            if (request.method() === "POST") {
                const payload = request.postDataJSON() as Record<
                    string,
                    unknown
                >
                const created = {
                    id: 32,
                    ...payload,
                    question_banks: [bank],
                    created_at: "2026-01-05T00:00:00Z",
                }
                quizzes = [created as (typeof quizzes)[number], ...quizzes]
                return route.fulfill({ status: 201, json: created })
            }
            return route.fulfill({
                json: quizzes,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": String(quizzes.length),
                },
            })
        }
        if (url.pathname === "/api/auth/logout") {
            return route.fulfill({ status: 204 })
        }
        return route.fulfill({ status: 404, body: "{}" })
    })

    return requests
}

test("restores a teacher session and displays their classes", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")

    await expect(
        page.getByRole("heading", { name: "Welcome, Ada Lovelace" })
    ).toBeVisible()
    await expect(page.getByText("Class 8B", { exact: true })).toBeVisible()
    await expect(page.getByText(/Grade 8/).last()).toBeVisible()
    await expect
        .poll(
            () =>
                requests
                    .find((request) =>
                        request.url().includes("/api/grade-levels")
                    )
                    ?.headers()["authorization"]
        )
        .toBe("Bearer teacher-access-token")
})

test("teacher dashboard does not overflow on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")

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
            page.getByRole("heading", { name: section, exact: true })
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
    await expect(page.getByRole("button", { name: "New class" })).toBeVisible()

    await page.getByRole("button", { name: "New class" }).click()
    const classDialog = page.getByRole("dialog", { name: "New class" })
    await expect(classDialog).toBeVisible()
    await expect(
        classDialog.getByRole("combobox", { name: "Class" })
    ).toBeEditable()
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

test("teacher can create a class", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "New class" }).click()
    const dialog = page.getByRole("dialog", { name: "New class" })
    await dialog.getByRole("combobox", { name: "Class" }).fill("Class 9A")
    await dialog.getByLabel("Grade level").selectOption("Grade 8")
    await dialog.getByRole("button", { name: "New class", exact: true }).click()

    await expect(page.getByText("Class 9A", { exact: true })).toBeVisible()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname === "/api/classes" &&
            request.method() === "POST"
    )
    expect(createRequest?.postDataJSON()).toEqual({
        name: "Class 9A",
        grade_level: "Grade 8",
    })
})

test("class list recovers after a temporary load failure", async ({ page }) => {
    await mockTeacherApi(page)
    let classRequests = 0
    await page.route(
        /^http:\/\/127\.0\.0\.1:4173\/api\/classes\?/,
        async (route) => {
            classRequests += 1
            // React StrictMode performs the initial effect twice in development.
            if (classRequests === 3) {
                await route.fulfill({ status: 503, body: "{}" })
                return
            }
            await route.fallback()
        }
    )
    await page.goto("/teacher/dashboard")
    await expect(page.getByText("Class 8B", { exact: true })).toBeVisible()

    await page.getByPlaceholder("Search for a class").fill("first request")
    await expect(page.getByRole("alert")).toHaveText("Failed to load classes.")
    await page.getByPlaceholder("Search for a class").fill("Class")
    await expect(page.getByText("Class 8B", { exact: true })).toBeVisible()
    await expect(page.getByRole("alert")).toHaveCount(0)
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

test("teacher can review configured quizzes", async ({ page }) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()

    await expect(
        page.getByRole("heading", { name: "Science checkpoint" })
    ).toBeVisible()
    await expect(page.getByText("Matter and energy")).toBeVisible()
    await expect(page.getByRole("button", { name: "Preview" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Launch" })).toBeVisible()
})

test("teacher assigns existing question banks to a training class", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Training", exact: true })
        .click()

    await expect(page.getByLabel("Class")).toHaveValue("11")
    await page.getByText("Matter and energy", { exact: true }).click()
    await expect(page.getByText("Advanced matter", { exact: true })).toHaveCount(
        0
    )
    await page.getByRole("button", { name: "Save question banks" }).click()
    await expect(
        page.getByText("The class training question banks have been saved.")
    ).toBeVisible()

    const saveRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname ===
                "/api/quizzes/training/classes/11/question-banks" &&
            request.method() === "PUT"
    )
    expect(saveRequest?.postDataJSON()).toEqual({ question_bank_ids: [21] })
    await expect(
        page.getByRole("button", { name: "New training quiz" })
    ).toHaveCount(0)
})

test("teacher can create a quiz from a question bank", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    await page.getByRole("button", { name: "New exam quiz" }).click()

    const dialog = page.getByRole("dialog", { name: "New exam quiz" })
    await dialog.getByLabel("Quiz title").fill("Energy assessment")
    await dialog.getByText("Matter and energy", { exact: true }).click()
    await dialog.getByLabel("Easy", { exact: true }).fill("10")
    await dialog.getByLabel("Points for Easy questions").fill("15")
    await dialog.getByRole("button", { name: "New quiz", exact: true }).click()

    await expect(
        page.getByRole("heading", { name: "Energy assessment" })
    ).toBeVisible()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname === "/api/quizzes" &&
            request.method() === "POST"
    )
    expect(createRequest?.postDataJSON()).toMatchObject({
        title: "Energy assessment",
        mode: "exam",
        same_questions_for_all: false,
        source_language: "en",
        question_bank_ids: [21],
        duration_seconds: 1800,
        easy_question_count: 10,
        medium_question_count: 0,
        hard_question_count: 0,
        easy_points: 15,
        medium_points: 0,
        hard_points: 0,
    })
})
