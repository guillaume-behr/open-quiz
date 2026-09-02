import { expect, test } from "@playwright/test"

const student = {
    id: 7,
    identifier: "alex-8b",
    display_name: "Alex Example",
    is_active: true,
    class_id: 2,
    class_name: "Class 8B",
    created_at: "2026-01-01T00:00:00Z",
}

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
    })
})

test("the root redirects to the student login", async ({ page }) => {
    await page.goto("/")

    await expect(page).toHaveURL(/\/student\/login$/)

    await expect(
        page.getByRole("heading", { name: "Student space" })
    ).toBeVisible()
    await expect(page.getByLabel("Student ID")).toBeVisible()
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled()
})

test("student login shows the localized API error type", async ({ page }) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            status: 429,
            json: { detail: { code: "AUTH_RATE_LIMITED" } },
        })
    })
    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("incorrect")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page.getByRole("alert")).toHaveText(
        "Too many sign-in attempts. Please wait before trying again."
    )
})

test("a signed-in student enters exam mode from the dashboard", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page).toHaveURL(/\/student\/dashboard$/)
    await expect(
        page.getByRole("heading", { name: "Welcome, Alex Example" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("button", { name: "Log out" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("link", { name: "Professor space" })
    ).toHaveCount(0)
    await page.getByRole("button", { name: "Exams", exact: true }).click()

    await expect(page.getByRole("heading", { name: "Exams" })).toBeVisible()
    await expect(
        page.getByRole("heading", { name: "Join a quiz", exact: true })
    ).toBeVisible()
    await expect(page.getByLabel("Quiz code")).toBeVisible()
})

test("student authentication clears activity sessions between users", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.goto("/student/login")
    await page.evaluate(() => {
        sessionStorage.setItem("open-quiz-student-session", "stale-exam")
        sessionStorage.setItem("open-quiz-training-session", "stale-training")
    })
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page).toHaveURL(/\/student\/dashboard$/)
    expect(
        await page.evaluate(() => ({
            exam: sessionStorage.getItem("open-quiz-student-session"),
            training: sessionStorage.getItem("open-quiz-training-session"),
        }))
    ).toEqual({ exam: null, training: null })

    await page.evaluate(() => {
        sessionStorage.setItem("open-quiz-student-session", "current-exam")
        sessionStorage.setItem("open-quiz-training-session", "current-training")
    })
    await page.getByRole("button", { name: "Log out" }).click()

    await expect(page).toHaveURL(/\/student\/login$/)
    expect(
        await page.evaluate(() => ({
            account: sessionStorage.getItem("open-quiz-student-access-token"),
            exam: sessionStorage.getItem("open-quiz-student-session"),
            training: sessionStorage.getItem("open-quiz-training-session"),
        }))
    ).toEqual({ account: null, exam: null, training: null })
})

test("a student translates a training quiz and its correction", async ({
    page,
}) => {
    await page.addInitScript(() => {
        Object.defineProperty(globalThis, "Translator", {
            configurable: true,
            value: {
                availability: async () => "available" as const,
                create: async () => ({
                    translate: async (text: string) =>
                        ({
                            "Entraînement scientifique": "Science practice",
                            "Nommez une planète rouge.": "Name a red planet.",
                            "Mars est la planète rouge.":
                                "Mars is the red planet.",
                        })[text] ?? text,
                    destroy: () => undefined,
                }),
            },
        })
    })
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/training", async (route) => {
        await route.fulfill({
            json: [
                {
                    id: 12,
                    grade_level: "Grade 8",
                    chapter: "Entraînement scientifique",
                    question_count: 1,
                    easy_question_count: 1,
                    medium_question_count: 0,
                    hard_question_count: 0,
                    created_at: "2026-01-01T00:00:00Z",
                },
            ],
        })
    })
    const session = {
        quiz_title: "Entraînement scientifique",
        source_language: "fr",
        class_name: "Class 8B",
        student_name: "Alex Example",
        join_code: "TRAIN2",
        status: "in_progress",
        ends_at: null,
        question_number: 1,
        total_questions: 1,
        has_answered: false,
        answered_count: 0,
        allow_previous_questions: false,
        selected_choice_ids: null,
        written_answer: null,
        question: {
            id: 51,
            prompt: "Nommez une planète rouge.",
            difficulty: "easy",
            answer_mode: "written",
            answer_mode_disclosed: true,
            response_language: null,
            has_image: false,
            code_language: null,
            code_content: null,
            choices: [],
        },
        training_feedback: null,
    }
    await page.route("**/api/quizzes/training/12/start", async (route) => {
        await route.fulfill({
            json: { ...session, participant_token: "training-token" },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/TRAIN2/answer",
        async (route) => {
            await route.fulfill({
                json: {
                    ...session,
                    status: "finished",
                    question: null,
                    answered_count: 1,
                    training_feedback: {
                        question_id: 51,
                        is_correct: null,
                        correct_choice_ids: [],
                        expected_answer: "Mars est la planète rouge.",
                        submitted_answer: "Mars",
                        requires_manual_review: true,
                    },
                },
            })
        }
    )

    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByRole("button", { name: "Training", exact: true }).click()
    await page.getByRole("button", { name: "Start training" }).click()
    await expect(page).toHaveURL(/\/student\/training$/)

    await expect(page.getByText("Nommez une planète rouge.")).toBeVisible()
    await page.getByRole("button", { name: "Automatic translation" }).click()
    await page.getByRole("button", { name: "Translate the quiz" }).click()
    await expect(page.getByText("Name a red planet.")).toBeVisible()
    await expect(page.getByText("Science practice")).toBeVisible()

    await page.getByLabel("Written answer").fill("Mars")
    await page.getByRole("button", { name: "Submit my answer" }).click()
    await expect(page.getByText("Mars is the red planet.")).toBeVisible()
    await expect(page.getByText("Name a red planet.")).toBeVisible()
})

test("a student launches training and sees the correct answer", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/training", async (route) => {
        await route.fulfill({
            json: [
                {
                    id: 12,
                    grade_level: "Grade 8",
                    chapter: "Practice science",
                    question_count: 1,
                    easy_question_count: 1,
                    medium_question_count: 0,
                    hard_question_count: 0,
                    created_at: "2026-01-01T00:00:00Z",
                },
            ],
        })
    })
    const question = {
        id: 41,
        prompt: "Which planet is red?",
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 101,
                label: "Mars",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
            {
                id: 102,
                label: "Venus",
                position: 1,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    const session = {
        quiz_title: "Practice science",
        source_language: "en",
        class_name: "Class 8B",
        student_name: "Alex Example",
        join_code: "TRAIN1",
        status: "in_progress",
        ends_at: null,
        question_number: 1,
        total_questions: 1,
        has_answered: false,
        answered_count: 0,
        allow_previous_questions: false,
        selected_choice_ids: null,
        written_answer: null,
        question,
        training_feedback: null,
    }
    await page.route("**/api/quizzes/training/12/start", async (route) => {
        await route.fulfill({
            json: { ...session, participant_token: "training-token" },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/TRAIN1/answer",
        async (route) => {
            expect(route.request().postDataJSON()).toEqual({
                selected_choice_ids: [101],
            })
            await route.fulfill({
                json: {
                    ...session,
                    status: "finished",
                    question: null,
                    answered_count: 1,
                    training_feedback: {
                        question_id: 41,
                        is_correct: true,
                        correct_choice_ids: [101],
                        expected_answer: null,
                    },
                },
            })
        }
    )

    await page.goto("/student/login")
    const studentLoginHeading = page.getByRole("heading", {
        name: "Student space",
    })
    const studentSignInButton = page.getByRole("button", { name: "Sign in" })
    await expect(studentLoginHeading.locator("..").locator("svg")).toHaveCount(
        0
    )
    await expect(studentSignInButton.locator("svg")).toHaveCount(0)
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await studentSignInButton.click()
    await page.getByRole("button", { name: "Training", exact: true }).click()
    await expect(page.getByText("Practice science")).toBeVisible()
    await page.getByRole("button", { name: "Start training" }).click()
    await expect(page).toHaveURL(/\/student\/training$/)
    await expect(
        page
            .locator("header")
            .getByRole("button", { name: "Student dashboard" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("link", { name: "Professor space" })
    ).toHaveCount(0)
    await page.getByLabel("Mars").check()
    const submitButton = page.getByRole("button", { name: "Submit my answer" })
    const questionFormBox = await submitButton
        .locator("xpath=ancestor::form")
        .boundingBox()
    const submitButtonBox = await submitButton.boundingBox()
    await submitButton.click()

    const correctionHeading = page.getByRole("heading", {
        name: "Correct answer",
    })
    await expect(correctionHeading).toBeVisible()
    await expect(page.getByText("Mars", { exact: true })).toBeVisible()
    await expect(page.getByText(/score/i)).toHaveCount(0)
    const correctionBox = await correctionHeading
        .locator("xpath=ancestor::section")
        .boundingBox()
    const continueButtonBox = await page
        .getByRole("button", { name: "Continue" })
        .boundingBox()
    expect(questionFormBox).not.toBeNull()
    expect(correctionBox).not.toBeNull()
    expect(correctionBox!.height).toBeGreaterThanOrEqual(
        questionFormBox!.height - 1
    )
    expect(
        Math.abs(continueButtonBox!.y - submitButtonBox!.y)
    ).toBeLessThanOrEqual(25)
    await page.getByRole("button", { name: "Continue" }).click()
    await page.getByRole("button", { name: "Back to home" }).click()
    await expect(page).toHaveURL(/\/student\/dashboard$/)
})

test("training history ignores a response from a previously closed dialog", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/training", async (route) => {
        const bank = (id: number, chapter: string) => ({
            id,
            grade_level: "Grade 8",
            chapter,
            question_count: 1,
            easy_question_count: 1,
            medium_question_count: 0,
            hard_question_count: 0,
            created_at: "2026-01-01T00:00:00Z",
        })
        await route.fulfill({
            json: [bank(12, "Practice science"), bank(13, "Practice maths")],
        })
    })
    let releaseFirstHistory: (() => void) | undefined
    const firstHistoryCanFinish = new Promise<void>((resolve) => {
        releaseFirstHistory = resolve
    })
    await page.route("**/api/quizzes/training/12/history", async (route) => {
        await firstHistoryCanFinish
        await route.fulfill({
            json: [
                {
                    session_id: 120,
                    score: 1,
                    maximum_score: 4,
                    started_at: "2026-01-01T10:00:00Z",
                },
            ],
        })
    })
    await page.route("**/api/quizzes/training/13/history", async (route) => {
        await route.fulfill({
            json: [
                {
                    session_id: 130,
                    score: 4,
                    maximum_score: 4,
                    started_at: "2026-01-02T10:00:00Z",
                },
            ],
        })
    })

    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByRole("button", { name: "Training", exact: true }).click()

    const firstRequest = page.waitForRequest(
        "**/api/quizzes/training/12/history"
    )
    await page
        .getByRole("article")
        .filter({ hasText: "Practice science" })
        .getByRole("button", { name: "View history" })
        .click()
    await firstRequest
    await page.getByRole("button", { name: "Close" }).click()
    await page
        .getByRole("article")
        .filter({ hasText: "Practice maths" })
        .getByRole("button", { name: "View history" })
        .click()
    await expect(page.getByText("4 / 4 (100%)")).toBeVisible()

    const staleResponse = page.waitForResponse(
        "**/api/quizzes/training/12/history"
    )
    releaseFirstHistory?.()
    await staleResponse
    await page.waitForTimeout(100)
    await expect(page.getByText("4 / 4 (100%)")).toBeVisible()
    await expect(page.getByText("1 / 4 (25%)")).toHaveCount(0)
})

test("a student joins a retake room and selects an eligible quiz", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/makeup/join", async (route) => {
        expect(route.request().postDataJSON()).toEqual({ join_code: "RETAKE1" })
        await route.fulfill({
            json: {
                join_code: "RETAKE1",
                class_name: "Class 8B",
                status: "waiting",
                quizzes: [
                    {
                        id: 31,
                        title: "Science checkpoint",
                        duration_seconds: 1800,
                    },
                ],
            },
        })
    })
    await page.route("**/api/quizzes/makeup/RETAKE1/select", async (route) => {
        expect(route.request().postDataJSON()).toEqual({ quiz_id: 31 })
        await route.fulfill({
            json: {
                quiz_title: "Science checkpoint",
                source_language: "en",
                class_name: "Class 8B",
                student_name: "Alex Example",
                join_code: "CHILD31",
                status: "waiting",
                ends_at: null,
                question_number: null,
                total_questions: 10,
                has_answered: false,
                answered_count: 0,
                allow_previous_questions: false,
                selected_choice_ids: null,
                written_answer: null,
                question: null,
                training_feedback: null,
                participant_token: "retake-participant-token",
            },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/CHILD31",
        async (route) => {
            await route.fulfill({
                json: {
                    quiz_title: "Science checkpoint",
                    source_language: "en",
                    class_name: "Class 8B",
                    student_name: "Alex Example",
                    join_code: "CHILD31",
                    status: "waiting",
                    ends_at: null,
                    question_number: null,
                    total_questions: 10,
                    has_answered: false,
                    answered_count: 0,
                    allow_previous_questions: false,
                    selected_choice_ids: null,
                    written_answer: null,
                    question: null,
                    training_feedback: null,
                },
            })
        }
    )

    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByRole("button", { name: "Retake", exact: true }).click()
    await expect(
        page.getByRole("heading", { name: "Retake", exact: true })
    ).toBeVisible()
    await expect(
        page.locator('section[aria-labelledby="makeup-title"] svg')
    ).toHaveCount(0)
    await page.getByLabel("Session code").fill("retake1")
    await page.getByRole("button", { name: "Join" }).click()

    await expect(page.getByText("Science checkpoint")).toBeVisible()
    await page.getByRole("button", { name: /Science checkpoint/ }).click()
    await expect(page).toHaveURL(/\/student\/exam$/)
    await expect
        .poll(() =>
            page.evaluate(() =>
                JSON.parse(
                    sessionStorage.getItem("open-quiz-student-session") ??
                        "null"
                )
            )
        )
        .toEqual({
            joinCode: "CHILD31",
            participantToken: "retake-participant-token",
        })
})

test("a student reviews the correction history", async ({ page }) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/student/results", async (route) => {
        await route.fulfill({
            json: [
                {
                    session_id: 90,
                    quiz_title: "Science checkpoint",
                    class_name: "Class 8B",
                    started_at: "2026-01-06T10:01:00Z",
                    score: 7,
                    maximum_score: 10,
                    answers: [
                        {
                            question_id: 93,
                            position: 1,
                            prompt: "Which planet is red?",
                            difficulty: "easy",
                            answer_mode: "single",
                            submitted_answers: ["Venus"],
                            expected_answers: ["Mars"],
                            is_correct: false,
                        },
                    ],
                },
            ],
        })
    })

    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password", { exact: true }).fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByRole("button", { name: "Results", exact: true }).click()
    await expect(page).toHaveURL(/\/student\/results$/)

    const correctionTrigger = page.getByRole("button", {
        name: /Science checkpoint/,
    })
    await expect(correctionTrigger).toHaveAttribute("aria-expanded", "false")
    await correctionTrigger.click()
    await expect(correctionTrigger).toHaveAttribute("aria-expanded", "true")
    await expect(page.getByText("Grade: 7 / 10")).toBeVisible()
    await expect(page.getByText("Which planet is red?")).toBeVisible()
    await expect(page.getByText("Venus", { exact: true })).toHaveClass(
        /text-destructive/
    )
    await expect(page.getByText("Review this answer")).toBeAttached()
    await expect(page.getByText("Mars", { exact: true })).toBeVisible()
    await correctionTrigger.click()
    await expect(correctionTrigger).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByText("Which planet is red?")).toBeHidden()
})

test("teacher area navigation works without a page reload", async ({
    page,
}) => {
    await page.goto("/student/login")
    await page.getByRole("link", { name: "Teacher area" }).click()

    await expect(page).toHaveURL(/\/teacher\/login$/)
    await expect(
        page.getByRole("heading", { name: "Teacher area" })
    ).toBeVisible()
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible()
})

test("student login remains usable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/student/login")

    const loginButton = page.getByRole("button", { name: "Sign in" })
    await expect(loginButton).toBeInViewport()
    await expect(page.getByLabel("Student ID")).toBeEditable()
    await expect(page.getByLabel("Password", { exact: true })).toBeEditable()
})
