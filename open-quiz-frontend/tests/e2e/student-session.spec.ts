import { expect, test, type Page, type WebSocketRoute } from "@playwright/test"

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
    accessible_question_numbers: [],
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

// Joining an exam happens on the student dashboard; the exam page then
// restores the saved session once before subscribing to live updates.
async function joinExamViaDashboard(page: Page, code: string): Promise<void> {
    await page.goto("/student/dashboard")
    await page.getByLabel("Quiz code").fill(code)
    await page.getByRole("button", { name: "Join the quiz" }).click()
    await expect(page).toHaveURL(/\/student\/exam$/)
}

test("joining a waiting quiz immediately requests full screen", async ({
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
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...baseSession,
                status: "waiting",
            }),
        })
    })
    await joinExamViaDashboard(page, "abcd")

    await expect(page.getByText("Alex Example", { exact: true })).toBeVisible()
    await expect(
        page.locator("header").getByRole("button", { name: "Leave quiz" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("link", { name: "Professor space" })
    ).toHaveCount(0)
    await expect(page.getByText("Signed in as Alex Example")).toHaveCount(0)
    await expect(page.getByText("Alex Example", { exact: true })).toHaveCount(1)
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
    let joinCount = 0
    await page.route("**/api/quizzes/join", async (route) => {
        joinCount += 1
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
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...baseSession,
                status: "waiting",
            }),
        })
    })
    let leaveRequested = false
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/leave",
        async (route) => {
            leaveRequested = true
            expect(route.request().method()).toBe("POST")
            expect(route.request().headers()["x-quiz-token"]).toBe(
                "participant-token"
            )
            await route.fulfill({ status: 204, body: "" })
        }
    )
    await joinExamViaDashboard(page, "ABCD")
    await page.getByRole("button", { name: "Leave quiz" }).click()

    await expect(page).toHaveURL(/\/student\/dashboard$/)
    expect(leaveRequested).toBe(true)
    await expect
        .poll(() =>
            page.evaluate(() =>
                sessionStorage.getItem("open-quiz-student-session")
            )
        )
        .toBeNull()

    await joinExamViaDashboard(page, "ABCD")
    await expect(page.getByText("Alex Example", { exact: true })).toBeVisible()
    expect(joinCount).toBe(2)
})

test("student uses the numbered progress bar to revisit a question", async ({
    page,
}) => {
    await page.addInitScript(() => {
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => document.documentElement,
        })
    })
    const question = {
        id: 202,
        prompt: "Second question",
        difficulty: "medium",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 203,
                label: "Second answer",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    let authenticatedSocketCount = 0
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/student\/sessions\/ABCD$/,
        (socket) => {
            socket.onMessage((message) => {
                expect(JSON.parse(String(message))).toEqual({
                    token: "participant-token",
                })
                authenticatedSocketCount += 1
            })
        }
    )
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 2,
                allow_previous_questions: true,
                accessible_question_numbers: [1, 2],
                question,
                participant_token: "participant-token",
            },
        })
    })
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 2,
                allow_previous_questions: true,
                accessible_question_numbers: [1, 2],
                question,
            },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/navigate",
        async (route) => {
            expect(route.request().postDataJSON()).toEqual({
                question_number: 1,
            })
            await route.fulfill({
                json: {
                    ...baseSession,
                    status: "in_progress",
                    question_number: 1,
                    answered_count: 1,
                    allow_previous_questions: true,
                    accessible_question_numbers: [1, 2],
                    has_answered: true,
                    selected_choice_ids: [201],
                    question: {
                        ...question,
                        id: 200,
                        prompt: "First question",
                        choices: [{ ...question.choices[0], id: 201 }],
                    },
                },
            })
        }
    )

    await joinExamViaDashboard(page, "ABCD")
    await expect.poll(() => authenticatedSocketCount).toBe(1)

    await page.getByRole("button", { name: "Question 1 on 3" }).click()
    await expect(
        page.getByRole("heading", { name: "First question" })
    ).toBeVisible()
    await expect(
        page.getByRole("button", { name: "Question 1 on 3" })
    ).toHaveAttribute("aria-current", "step")
    expect(authenticatedSocketCount).toBe(1)
})

test("student stays on a usable join screen when session storage is unavailable", async ({
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
    await page.goto("/student/dashboard")
    await page.getByLabel("Quiz code").fill("ABCD")
    await page.getByRole("button", { name: "Join the quiz" }).click()

    // The session cannot be persisted, so the exam page cannot restore it and
    // the student is returned to a usable join screen instead of crashing.
    await expect(page).toHaveURL(/\/student\/dashboard$/)
    await expect(page.getByLabel("Quiz code")).toBeVisible()
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

    // The stored entry cannot be restored, so the student returns to the
    // dashboard and the stale session is cleared.
    await expect(page).toHaveURL(/\/student\/dashboard$/)
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
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 1,
                question,
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
    await joinExamViaDashboard(page, "ABCD")

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

test("student translates a quiz and monitoring reports leaving the viewport", async ({
    page,
}) => {
    await page.addInitScript(() => {
        Object.defineProperty(document, "fullscreenElement", {
            configurable: true,
            get: () => document.documentElement,
        })
        Object.defineProperty(globalThis, "Translator", {
            configurable: true,
            value: {
                availability: async () => "available" as const,
                create: async () => ({
                    translate: async (text: string) =>
                        ({
                            "Révision scientifique": "Science review",
                            "Quelle planète est rouge ?":
                                "Which planet is red?",
                            Mars: "Mars",
                            Vénus: "Venus",
                        })[text] ?? text,
                    destroy: () => undefined,
                }),
            },
        })
    })
    const question = {
        id: 141,
        prompt: "Quelle planète est rouge ?",
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 201,
                label: "Mars",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
            {
                id: 202,
                label: "Vénus",
                position: 1,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    const translatedSession = {
        ...baseSession,
        quiz_title: "Révision scientifique",
        source_language: "fr",
        status: "in_progress",
        question_number: 1,
        question,
    }
    const violations: unknown[] = []
    await page.route("**/api/quizzes/join", async (route) => {
        await route.fulfill({
            json: {
                ...translatedSession,
                participant_token: "participant-token",
            },
        })
    })
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({ json: translatedSession })
    })
    await page.route(
        "**/api/quizzes/student/sessions/ABCD/violation",
        async (route) => {
            violations.push(route.request().postDataJSON())
            await route.fulfill({ status: 204 })
        }
    )

    await joinExamViaDashboard(page, "ABCD")
    await expect(page.getByText("Révision scientifique")).toBeVisible()
    await expect(
        page.getByRole("button", { name: "Translate the quiz" })
    ).toBeHidden()
    await page.getByRole("button", { name: "Automatic translation" }).click()
    await page.getByRole("button", { name: "Translate the quiz" }).click()
    await expect(page.getByText("Science review")).toBeVisible()
    await expect(page.getByText("Which planet is red?")).toBeVisible()
    await expect(page.getByLabel("Venus")).toBeVisible()
    await page.getByRole("button", { name: "Show original text" }).click()
    await expect(page.getByText("Quelle planète est rouge ?")).toBeVisible()

    await page.waitForTimeout(1600)
    await page.locator("html").dispatchEvent("mouseleave")
    await expect
        .poll(() => violations)
        .toEqual([{ event_type: "pointer_exit" }])

    // Normal editor operations are allowed. Only an unusually large paste is
    // reported, and different signals do not suppress one another.
    await page.locator("body").dispatchEvent("copy")
    await page.locator("body").evaluate((element) => {
        const clipboard = new DataTransfer()
        clipboard.setData("text/plain", "short paste")
        element.dispatchEvent(
            new ClipboardEvent("paste", {
                bubbles: true,
                clipboardData: clipboard,
            })
        )
    })
    await page.waitForTimeout(100)
    expect(violations).toEqual([{ event_type: "pointer_exit" }])
    await page.locator("body").evaluate((element) => {
        const clipboard = new DataTransfer()
        clipboard.setData("text/plain", "x".repeat(500))
        element.dispatchEvent(
            new ClipboardEvent("paste", {
                bubbles: true,
                clipboardData: clipboard,
            })
        )
    })
    await expect
        .poll(() => violations)
        .toEqual([
            { event_type: "pointer_exit" },
            { event_type: "paste_attempt" },
        ])
})

test("student session state is updated through its live socket", async ({
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
    let stateRequestCount = 0
    let resolveSocket: (socket: WebSocketRoute) => void = () => undefined
    const socketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSocket = resolve
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
            stateRequestCount += 1
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
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/student\/sessions\/ABCD$/,
        (socket) => {
            socket.onMessage((message) => {
                expect(JSON.parse(String(message))).toEqual({
                    token: "participant-token",
                })
                resolveSocket(socket)
            })
        }
    )

    await joinExamViaDashboard(page, "ABCD")
    await expect(
        page.getByRole("heading", {
            name: "Which state should remain visible?",
        })
    ).toBeVisible()
    const socket = await socketReady
    await socket.send(
        JSON.stringify({
            type: "session",
            data: {
                ...baseSession,
                status: "finished",
                answered_count: 1,
            },
        })
    )
    await expect(
        page.getByText("The quiz is over. Thank you for your participation!")
    ).toBeVisible()
    await expect(
        page.getByRole("heading", {
            name: "Which state should remain visible?",
        })
    ).toHaveCount(0)
    expect(stateRequestCount).toBeLessThanOrEqual(2)
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
    await page.route("**/api/quizzes/student/sessions/ABCD", async (route) => {
        await route.fulfill({
            json: {
                ...baseSession,
                status: "in_progress",
                question_number: 1,
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
    await joinExamViaDashboard(page, "ABCD")
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
        page.locator("main").getByRole("button", { name: "Back to home" })
    ).toBeVisible()
    await expect(
        page
            .locator("header")
            .getByRole("button", { name: "Join another quiz" })
    ).toBeVisible()
})
