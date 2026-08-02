import { expect, test } from "@playwright/test"

const baseSession = {
    quiz_title: "Science review",
    source_language: "en",
    class_name: "Class 8B",
    student_name: "Alex Example",
    join_code: "ABCD",
    ends_at: null,
    question_number: null,
    total_questions: 3,
    has_answered: false,
    answered_count: 0,
    allow_previous_questions: false,
    selected_choice_ids: null,
    written_answer: null,
    question: null,
}

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        sessionStorage.setItem(
            "open-quiz-student-access-token",
            "student-access-token"
        )
    })
    await page.route("**/api/student-auth/me", async (route) => {
        await route.fulfill({
            json: {
                id: 7,
                identifier: "alex-8b",
                display_name: "Alex Example",
                is_active: true,
                class_id: 2,
                class_name: "Class 8B",
                created_at: "2026-01-01T00:00:00Z",
            },
        })
    })
})

test("joining an active quiz stores the session and requests full screen", async ({
    page,
}) => {
    await page.route("**/api/quizzes/join", async (route) => {
        expect(route.request().postDataJSON()).toEqual({
            join_code: "ABCD",
        })
        expect(route.request().headers().authorization).toBe(
            "Bearer student-access-token"
        )
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...baseSession,
                status: "waiting",
                participant_token: "participant-token",
            }),
        })
    })
    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("abcd")
    await page.getByRole("button", { name: "Join the quiz" }).click()

    await expect(page.getByText("Alex Example", { exact: true })).toBeVisible()
    await expect(page.getByText("Full-screen mode is required")).toBeVisible()
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
            joinCode: "ABCD",
            participantToken: "participant-token",
        })
})

test("student can leave a quiz before entering full screen", async ({
    page,
}) => {
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...baseSession,
                status: "waiting",
                participant_token: "participant-token",
            }),
        })
    })
    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()
    await page.getByRole("button", { name: "Leave quiz" }).click()

    await expect(
        page.getByRole("heading", { name: "Join a quiz" })
    ).toBeVisible()
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-student-session")
            )
        )
        .toBeNull()
})

test("student can join and leave when session storage is unavailable", async ({
    page,
}) => {
    await page.addInitScript(() => {
        Object.defineProperties(window.sessionStorage, {
            setItem: {
                configurable: true,
                value: () => {
                    throw new DOMException("Storage disabled", "SecurityError")
                },
            },
            removeItem: {
                configurable: true,
                value: () => {
                    throw new DOMException("Storage disabled", "SecurityError")
                },
            },
        })
    })
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...baseSession,
                status: "waiting",
                participant_token: "participant-token",
            }),
        })
    })
    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()

    await expect(page.getByText("Full-screen mode is required")).toBeVisible()
    await expect(
        page.getByText(/Leaving it during the quiz may be reported/)
    ).toBeVisible()
    await page.getByRole("button", { name: "Leave quiz" }).click()
    await expect(
        page.getByRole("heading", { name: "Join a quiz" })
    ).toBeVisible()
})

test("an expired stored quiz session is discarded", async ({ page }) => {
    await page.addInitScript(() => {
        sessionStorage.setItem(
            "open-quiz-student-session",
            JSON.stringify({
                joinCode: "OLD1",
                participantToken: "expired-token",
            })
        )
    })
    await page.route("**/api/quizzes/student/sessions/OLD1", async (route) => {
        await route.fulfill({ status: 403, body: "{}" })
    })
    await page.goto("/student/exam")

    await expect(page.getByRole("alert")).toHaveText(
        "The previous session is no longer available. Ask your teacher for help."
    )
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-student-session")
            )
        )
        .toBeNull()
})

test("student can submit a multiple-choice answer", async ({ page }) => {
    await page.addInitScript(() => {
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => document.documentElement,
        })
    })
    const question = {
        id: 41,
        prompt: "Which planet is known as the Red Planet?",
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
                position: 1,
                has_image: false,
                code_language: null,
                code_content: null,
            },
            {
                id: 102,
                label: "Venus",
                position: 2,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 1,
                question,
                participant_token: "participant-token",
            },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/answer",
        async (route) => {
            expect(route.request().postDataJSON()).toEqual({
                selected_choice_ids: [101],
            })
            expect(route.request().headers()["x-quiz-token"]).toBe(
                "participant-token"
            )
            await route.fulfill({
                json: {
                    ...baseSession,
                    status: "in_progress",
                    question_number: 1,
                    has_answered: true,
                    answered_count: 1,
                },
            })
        }
    )
    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()

    await expect(
        page.getByRole("heading", {
            name: "Which planet is known as the Red Planet?",
        })
    ).toBeVisible()
    await expect(
        page.getByRole("button", { name: "Submit my answer" })
    ).toBeDisabled()
    await page.getByLabel("Mars").check()
    await page.getByRole("button", { name: "Submit my answer" }).click()
    await expect(page.getByText("Response recorded")).toBeVisible()
})

test("a delayed poll cannot restore a question after submission", async ({
    page,
}) => {
    await page.addInitScript(() => {
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => document.documentElement,
        })
    })
    const question = {
        id: 43,
        prompt: "Which state should remain visible?",
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 103,
                label: "The completed state",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
            {
                id: 104,
                label: "The stale question",
                position: 1,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    let markPollStarted: () => void = () => undefined
    const pollStarted = new Promise<void>((resolve) => {
        markPollStarted = resolve
    })
    let releasePoll: () => void = () => undefined
    const pollRelease = new Promise<void>((resolve) => {
        releasePoll = resolve
    })

    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 1,
                question,
                participant_token: "participant-token",
            },
        })
    })
    await page.route(
        /\/api\/quizzes\/student\/sessions\/ABCD$/,
        async (route) => {
            markPollStarted()
            await pollRelease
            await route.fulfill({
                json: {
                    ...baseSession,
                    status: "in_progress",
                    question_number: 1,
                    question,
                },
            })
        }
    )
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/answer",
        async (route) => {
            await route.fulfill({
                json: {
                    ...baseSession,
                    status: "finished",
                    answered_count: 1,
                },
            })
        }
    )

    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()
    await pollStarted
    await page.getByLabel("The completed state").check()
    await page.getByRole("button", { name: "Submit my answer" }).click()
    await expect(
        page.getByText("The quiz is over. Thank you for your participation!")
    ).toBeVisible()

    releasePoll()
    await expect(
        page.getByText("The quiz is over. Thank you for your participation!")
    ).toBeVisible()
    await expect(
        page.getByRole("heading", {
            name: "Which state should remain visible?",
        })
    ).toHaveCount(0)
})

test("student can submit a written answer", async ({ page }) => {
    await page.addInitScript(() => {
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => document.documentElement,
        })
    })
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 1,
                participant_token: "participant-token",
                question: {
                    id: 42,
                    prompt: "Explain photosynthesis briefly.",
                    difficulty: "medium",
                    answer_mode: "written",
                    answer_mode_disclosed: true,
                    response_language: null,
                    has_image: false,
                    code_language: null,
                    code_content: null,
                    choices: [],
                },
            },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/answer",
        async (route) => {
            expect(route.request().postDataJSON()).toEqual({
                written_answer:
                    "Plants convert light energy into chemical energy.",
            })
            await route.fulfill({
                json: {
                    ...baseSession,
                    status: "finished",
                    has_answered: true,
                    answered_count: 1,
                },
            })
        }
    )
    await page.goto("/student/exam")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()
    const submitAnswer = page.getByRole("button", {
        name: "Submit my answer",
    })
    await expect(submitAnswer).toBeDisabled()
    await page.getByLabel("Written answer").fill("   ")
    await expect(submitAnswer).toBeDisabled()
    await page
        .getByLabel("Written answer")
        .fill("Plants convert light energy into chemical energy.")
    await expect(submitAnswer).toBeEnabled()
    await submitAnswer.click()

    await expect(
        page.getByText("The quiz is over. Thank you for your participation!")
    ).toBeVisible()
    await expect(
        page.getByRole("button", { name: "Join another quiz" })
    ).toBeVisible()
})
