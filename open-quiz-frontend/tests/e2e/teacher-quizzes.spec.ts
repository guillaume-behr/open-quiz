import {
    expect,
    test,
    type Page,
    type Request,
    type WebSocketRoute,
} from "./fixtures"
import { existingClass, mockTeacherApi } from "./teacher-api"

test("teacher can review configured quizzes", async ({ page }) => {
    await mockTeacherApi(page)
    await page.route(
        "http://127.0.0.1:4173/api/question-banks/21/questions",
        (route) =>
            route.fulfill({
                json: [
                    {
                        id: 71,
                        question_bank_id: 21,
                        prompt: "What does this program print?",
                        points: 1,
                        difficulty: "easy",
                        answer_mode: "single",
                        answer_mode_disclosed: true,
                        response_language: null,
                        has_image: true,
                        code_language: "python",
                        code_content: 'print("energy")',
                        choices: [
                            {
                                id: 72,
                                label: "energy",
                                is_correct: true,
                                points: 1,
                                position: 0,
                                has_image: true,
                                code_language: "text",
                                code_content: "energy",
                            },
                        ],
                        created_at: "2026-01-06T12:00:00Z",
                    },
                ],
            })
    )
    const pixel = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64"
    )
    for (const path of [
        "/api/question-banks/questions/71/image",
        "/api/question-banks/choices/72/image",
    ]) {
        await page.route(`http://127.0.0.1:4173${path}`, (route) =>
            route.fulfill({ contentType: "image/png", body: pixel })
        )
    }
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()

    await expect(
        page.getByRole("heading", { name: "Science checkpoint" })
    ).toBeVisible()
    await expect(page.getByText("Matter and energy")).toBeVisible()
    const previewButton = page.getByRole("button", { name: "Preview" })
    const printButton = page.getByRole("button", {
        name: "Print exam papers",
    })
    await expect(previewButton).toBeVisible()
    await expect(page.getByRole("button", { name: "Launch" })).toBeVisible()
    await expect(printButton).toBeVisible()
    expect((await printButton.boundingBox())!.x).toBeGreaterThan(
        (await previewButton.boundingBox())!.x
    )

    await printButton.click()
    const printDialog = page.getByRole("dialog", {
        name: "Print exam papers",
    })
    await expect(printDialog.getByLabel("Class")).toHaveValue("")
    await printDialog.getByLabel("Class").selectOption("11")
    const printAction = printDialog.getByRole("button", {
        name: "Print exam papers",
    })
    await expect(printAction).toBeEnabled()
    const popupPromise = page.waitForEvent("popup")
    await printAction.click()
    const printPage = await popupPromise
    await expect(printPage.locator(".subject")).toHaveCount(
        existingClass.students.length
    )
    await expect(printPage.locator(".identity")).toContainText("Last name")
    await expect(printPage.locator(".identity")).toContainText("First name")
    await expect(printPage.locator(".question-image")).toHaveCount(
        existingClass.students.length
    )
    await expect(printPage.locator(".choice-image")).toHaveCount(
        existingClass.students.length
    )
    await expect(printPage.locator("pre").first()).toContainText(
        'print("energy")'
    )
    await printPage.close()
})

test("finished quiz sessions disappear from the active quiz list", async ({
    page,
}) => {
    await mockTeacherApi(page)
    const waitingSession = {
        id: 79,
        quiz_id: 31,
        quiz_title: "Running checkpoint",
        class_id: 11,
        class_name: "Class 8B",
        join_code: "RUN079",
        status: "waiting",
        participant_count: 0,
        participants: [],
        total_questions: 10,
        created_at: "2026-01-06T10:00:00Z",
        started_at: null,
        ends_at: null,
    }
    let resolveSocket: (socket: WebSocketRoute) => void = () => undefined
    const socketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions$/,
        (socket) => {
            socket.onMessage((message) => {
                const credentials = JSON.parse(String(message)) as {
                    token?: string
                }
                expect(credentials.token).toBeTruthy()
                resolveSocket(socket)
            })
        }
    )

    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    const socket = await socketReady
    socket.send(
        JSON.stringify({ type: "active_sessions", data: [waitingSession] })
    )
    await expect(
        page.getByRole("heading", { name: "Active quizzes" })
    ).toBeVisible()
    socket.send(
        JSON.stringify({
            type: "active_sessions",
            data: [],
        })
    )

    await expect(
        page.getByRole("heading", { name: "Active quizzes" })
    ).toHaveCount(0)
    await expect(page.getByText("Recent sessions")).toHaveCount(0)
})

test("teacher dialog tracks progress from the active sessions stream", async ({
    page,
}) => {
    await mockTeacherApi(page)
    const runningSession = {
        id: 79,
        quiz_id: 31,
        quiz_title: "Running checkpoint",
        class_id: 11,
        class_name: "Class 8B",
        join_code: "RUN079",
        status: "in_progress",
        participant_count: 1,
        participants: [
            {
                id: 81,
                student_identifier: "alex-8b",
                student_display_name: "Alex Example",
                answered_count: 0,
                score: 0,
                maximum_score: 10,
                pending_manual_grading_count: 0,
                violation_count: 0,
                last_violation_type: null,
                last_violation_at: null,
                joined_at: "2026-01-06T10:00:00Z",
            },
        ],
        total_questions: 10,
        created_at: "2026-01-06T10:00:00Z",
        started_at: "2026-01-06T10:01:00Z",
        ends_at: "2026-01-06T10:31:00Z",
        grades_published_at: null,
    }
    let resolveSessionsSocket: (socket: WebSocketRoute) => void = () =>
        undefined
    const sessionsSocketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSessionsSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions$/,
        (socket) => {
            socket.onMessage(() => resolveSessionsSocket(socket))
        }
    )
    // Keep the detail stream connected but silent to reproduce a missed
    // per-session notification or reconnect gap.
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions\/79$/,
        () => undefined
    )

    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    const sessionsSocket = await sessionsSocketReady
    sessionsSocket.send(
        JSON.stringify({ type: "active_sessions", data: [runningSession] })
    )
    await page
        .getByRole("button", {
            name: "Running checkpoint · Class 8B · 1",
        })
        .click()

    const sessionDialog = page.getByRole("dialog", {
        name: "Running checkpoint",
    })
    await expect(
        sessionDialog.getByText("Progress: 0 of 10 questions")
    ).toBeVisible()
    sessionsSocket.send(
        JSON.stringify({
            type: "active_sessions",
            data: [
                {
                    ...runningSession,
                    participants: [
                        {
                            ...runningSession.participants[0],
                            answered_count: 4,
                        },
                    ],
                },
            ],
        })
    )

    await expect(
        sessionDialog.getByText("Progress: 4 of 10 questions")
    ).toBeVisible()
})

test("teacher assigns existing question banks to a training class", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Training", exact: true }).click()

    await expect(page.getByLabel("Class")).toHaveValue("11")
    await page.getByText("Matter and energy", { exact: true }).click()
    const configurationDialog = page.getByRole("dialog", {
        name: "Configure question bank",
    })
    await expect(
        configurationDialog.getByLabel("Number of questions")
    ).toHaveValue("10")
    await configurationDialog.getByRole("button", { name: "Save" }).click()
    await expect(
        page.getByText("Advanced matter", { exact: true })
    ).toHaveCount(0)
    await expect
        .poll(
            () =>
                requests
                    .find(
                        (request) =>
                            new URL(request.url()).pathname ===
                                "/api/quizzes/training/classes/11/question-banks" &&
                            request.method() === "PUT"
                    )
                    ?.postDataJSON() as unknown
        )
        .toEqual({
            question_banks: [{ question_bank_id: 21, question_count: 10 }],
        })
    await expect(
        page.getByRole("button", { name: "New training quiz" })
    ).toHaveCount(0)
})

test("teacher launches and controls a live quiz session", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    let resolveWaitingSocket: (socket: WebSocketRoute) => void = () => undefined
    const waitingSocketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveWaitingSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions\/80$/,
        (socket) => {
            socket.onMessage(() => resolveWaitingSocket(socket))
        }
    )
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    await page.getByRole("button", { name: "Launch" }).click()

    const launchDialog = page.getByRole("dialog", { name: "Launch" })
    await launchDialog.getByLabel("Class").selectOption("11")
    await launchDialog
        .getByRole("button", { name: "Open waiting room" })
        .click()

    const sessionDialog = page.getByRole("dialog", {
        name: "Science checkpoint",
    })
    await expect(sessionDialog.getByText("LIVE80")).toBeVisible()
    await expect(sessionDialog.getByText("Alex Example")).toBeVisible()
    const sessionSocket = await waitingSocketReady
    await sessionDialog.getByRole("button", { name: "Start quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()
    sessionSocket.send(
        JSON.stringify({
            type: "session",
            data: {
                id: 80,
                quiz_id: 31,
                quiz_title: "Science checkpoint",
                class_id: 11,
                class_name: "Class 8B",
                join_code: "LIVE80",
                status: "in_progress",
                participant_count: 1,
                participants: [
                    {
                        id: 81,
                        student_identifier: "alex-8b",
                        student_display_name: "Alex Example",
                        answered_count: 10,
                        has_finished: true,
                        score: 999,
                        maximum_score: 10,
                        pending_manual_grading_count: 0,
                        violation_count: 0,
                        last_violation_type: null,
                        last_violation_at: null,
                        joined_at: "2026-01-06T10:00:00Z",
                    },
                ],
                total_questions: 10,
                created_at: "2026-01-06T10:00:00Z",
                started_at: "2026-01-06T10:01:00Z",
                ends_at: "2026-01-06T10:31:00Z",
                grades_published_at: null,
            },
        })
    )
    await expect(sessionDialog.getByText("Quiz completed")).toBeVisible()
    await expect(sessionDialog.getByText(/Score:/)).toHaveCount(0)
    await expect(sessionDialog.getByText("999", { exact: true })).toHaveCount(0)

    // The enlarged view is a passive mirror of this dialog, in its own tab.
    const displayPage = await Promise.all([
        page.context().waitForEvent("page"),
        sessionDialog.getByRole("button", { name: "Enlarge" }).click(),
    ]).then(([opened]) => opened)
    await expect(displayPage).toHaveURL(/\/teacher\/session-display\/quiz-80$/)
    await expect(displayPage.getByText("LIVE80", { exact: true })).toBeVisible()
    await expect(displayPage.getByRole("timer")).toBeVisible()
    await expect(displayPage.getByText("1 student finished")).toBeVisible()
    await displayPage.close()

    await sessionDialog.getByRole("button", { name: "Pause quiz" }).click()
    await expect(
        sessionDialog.getByText("Quiz paused", { exact: true })
    ).toBeVisible()
    await sessionDialog.getByRole("button", { name: "Resume quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()

    await sessionDialog.getByRole("button", { name: "Cancel quiz" }).click()
    const cancelDialog = page.getByRole("dialog", { name: "Cancel quiz" })
    await cancelDialog
        .getByRole("button", { name: "Confirm cancellation" })
        .click()
    await expect(sessionDialog).toHaveCount(0)

    expect(
        requests
            .filter((request) =>
                new URL(request.url()).pathname.startsWith(
                    "/api/quizzes/sessions/80"
                )
            )
            .filter((request) => request.method() !== "GET")
            .map((request) => ({
                method: request.method(),
                action: new URL(request.url()).pathname.split("/").at(-1),
            }))
    ).toEqual([
        { method: "POST", action: "start" },
        { method: "POST", action: "pause" },
        { method: "POST", action: "resume" },
        { method: "POST", action: "cancel" },
    ])
})

test("teacher waiting room updates when a student joins", async ({ page }) => {
    await mockTeacherApi(page)
    const waitingSession = {
        id: 80,
        quiz_id: 31,
        quiz_title: "Science checkpoint",
        class_id: 11,
        class_name: "Class 8B",
        join_code: "LIVE80",
        status: "waiting",
        participant_count: 0,
        participants: [],
        total_questions: 10,
        created_at: "2026-01-06T10:00:00Z",
        started_at: null,
        ends_at: null,
        grades_published_at: null,
    }
    await page.route("**/api/quizzes/31/launch", (route) =>
        route.fulfill({ status: 201, json: waitingSession })
    )
    let resolveSocket: (socket: WebSocketRoute) => void = () => undefined
    const socketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions\/80$/,
        (socket) => {
            socket.onMessage(() => resolveSocket(socket))
        }
    )

    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Exam quizzes", exact: true })
        .click()
    await page.getByRole("button", { name: "Launch" }).click()
    const launchDialog = page.getByRole("dialog", { name: "Launch" })
    await launchDialog.getByLabel("Class").selectOption("11")
    await launchDialog
        .getByRole("button", { name: "Open waiting room" })
        .click()

    const sessionDialog = page.getByRole("dialog", {
        name: "Science checkpoint",
    })
    await expect(
        sessionDialog.getByText("No students have joined the quiz yet.")
    ).toBeVisible()
    const socket = await socketReady
    socket.send(
        JSON.stringify({
            type: "session",
            data: {
                ...waitingSession,
                participant_count: 1,
                participants: [
                    {
                        id: 81,
                        student_identifier: "alex-8b",
                        student_display_name: "Alex Example",
                        answered_count: 0,
                        score: 0,
                        maximum_score: 10,
                        pending_manual_grading_count: 0,
                        violation_count: 0,
                        last_violation_type: null,
                        last_violation_at: null,
                        joined_at: "2026-01-06T10:02:00Z",
                    },
                ],
            },
        })
    )

    await expect(sessionDialog.getByText("Alex Example")).toBeVisible()
    await expect(
        sessionDialog.getByText("No students have joined the quiz yet.")
    ).toHaveCount(0)
})

test("teacher creates and controls a retake session", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()
    await expect(page.getByText("Class 8B · OLD123")).toHaveCount(0)

    await expect(
        page.getByRole("button", { name: "New retake session" })
    ).toHaveCount(0)
    await selectRetakeClass(page)
    await page.getByText("Science checkpoint", { exact: true }).click()
    await page.getByRole("button", { name: "Create session" }).click()

    await expect
        .poll(() =>
            requests.some(
                (request) =>
                    new URL(request.url()).pathname ===
                        "/api/quizzes/makeup/sessions" &&
                    request.method() === "POST"
            )
        )
        .toBe(true)
    const sessionDialog = page.getByRole("dialog", { name: "Retake" })
    await expect(sessionDialog.getByText("MAKE51")).toBeVisible()
    await expect(sessionDialog.getByText("Student One")).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname ===
                        "/api/quizzes/makeup/sessions" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({ class_id: 11, quiz_ids: [31] })

    await sessionDialog.getByRole("button", { name: "Start quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()
    await sessionDialog.getByRole("button", { name: "Pause quiz" }).click()
    await expect(
        sessionDialog.getByText("Quiz paused", { exact: true })
    ).toBeVisible()
    await sessionDialog.getByRole("button", { name: "Resume quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()
    await sessionDialog.getByRole("button", { name: "Finish quiz" }).click()
    await page
        .getByRole("dialog", { name: "Finish quiz" })
        .getByRole("button", { name: "Finish quiz" })
        .click()
    await expect(sessionDialog).toHaveCount(0)

    expect(
        requests
            .filter((request) =>
                new URL(request.url()).pathname.startsWith(
                    "/api/quizzes/makeup/sessions/51/"
                )
            )
            .map((request) => new URL(request.url()).pathname.split("/").at(-1))
    ).toEqual(["start", "pause", "resume", "finish"])
})

test("teacher receives a retake created while the local list is empty", async ({
    page,
}) => {
    await mockTeacherApi(page)
    let resolveSocket: (socket: WebSocketRoute) => void = () => undefined
    const socketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/makeup-sessions$/,
        (socket) => {
            socket.onMessage((message) => {
                const credentials = JSON.parse(String(message)) as {
                    token?: string
                }
                expect(credentials.token).toBeTruthy()
                resolveSocket(socket)
            })
        }
    )

    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()
    const socket = await socketReady
    socket.send(
        JSON.stringify({
            type: "makeup_sessions",
            data: [
                {
                    id: 52,
                    class_id: 11,
                    class_name: "Class 8B",
                    join_code: "REMOTE52",
                    status: "waiting",
                    quizzes: [
                        {
                            id: 31,
                            title: "Science checkpoint",
                            duration_seconds: 1800,
                        },
                    ],
                    participant_count: 0,
                    created_at: "2026-01-06T10:00:00Z",
                },
            ],
        })
    )

    await expect(page.getByText("Class 8B · REMOTE52")).toBeVisible()
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
    await dialog.getByLabel("Grade level").selectOption("Grade 8")
    await dialog.getByText("Matter and energy", { exact: true }).click()
    await dialog.getByLabel("Easy", { exact: true }).fill("10")
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
        duration_seconds: 900,
        easy_question_count: 10,
        medium_question_count: 0,
        hard_question_count: 0,
    })
})

// The retake panel is loaded lazily: until it appears, the previous section,
// with its own "Class" filter, is still on screen. Choosing a class before the
// panel is there would pick it in that filter, and no quiz would be offered.
async function selectRetakeClass(page: Page) {
    await expect(
        page.getByRole("heading", { name: "New retake session" })
    ).toBeVisible()
    await page.getByRole("combobox", { name: "Class" }).selectOption("11")
}

async function openNewRetake(page: Page) {
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()
    await selectRetakeClass(page)
    await page.getByText("Science checkpoint", { exact: true }).click()
    await page.getByRole("button", { name: "Create session" }).click()
    const dialog = page.getByRole("dialog", { name: "Retake" })
    await expect(dialog.getByText("MAKE51")).toBeVisible()
    return dialog
}

const retakeControls = (requests: Request[]) =>
    requests
        .filter((request) =>
            new URL(request.url()).pathname.startsWith(
                "/api/quizzes/makeup/sessions/51/"
            )
        )
        .map((request) => new URL(request.url()).pathname.split("/").at(-1))

test("a retake is cancelled only once the cancellation is confirmed", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    const dialog = await openNewRetake(page)

    await dialog.getByRole("button", { name: "Cancel quiz" }).click()
    const confirmation = page.getByRole("dialog", { name: "Cancel quiz" })
    await expect(confirmation).toBeVisible()
    expect(retakeControls(requests)).toEqual([])
    await confirmation
        .getByRole("button", { name: "Cancel", exact: true })
        .click()
    await expect(confirmation).toBeHidden()
    expect(retakeControls(requests)).toEqual([])

    await dialog.getByRole("button", { name: "Cancel quiz" }).click()
    await confirmation
        .getByRole("button", { name: "Confirm cancellation" })
        .click()
    await expect(confirmation).toBeHidden()
    await expect(dialog).toBeHidden()
    expect(retakeControls(requests)).toEqual(["cancel"])
})

test("a retake action shows its own progress and keeps its error in the dialog", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    let releaseResume = () => {}
    await page.route(
        "http://127.0.0.1:4173/api/quizzes/makeup/sessions/51/resume",
        async (route) => {
            await new Promise<void>((resolve) => {
                releaseResume = resolve
            })
            await route.fulfill({ status: 500, json: { detail: "boom" } })
        }
    )
    const dialog = await openNewRetake(page)
    await dialog.getByRole("button", { name: "Start quiz" }).click()
    await dialog.getByRole("button", { name: "Pause quiz" }).click()
    const resume = dialog.getByRole("button", { name: "Resume quiz" })
    await resume.click()

    await expect(resume.locator(".animate-spin")).toBeVisible()
    await expect(
        dialog.getByRole("button", { name: "Cancel quiz" })
    ).toBeDisabled()
    releaseResume()

    await expect(
        dialog.getByText("Unable to update the session.")
    ).toBeVisible()
    await expect(page.getByText("Unable to update the session.")).toHaveCount(1)
    // The failing resume is answered by this test's route, not the mock.
    expect(retakeControls(requests)).toEqual(["start", "pause"])
})

test("a finished retake never offers a Delete button that does nothing", async ({
    page,
}) => {
    await mockTeacherApi(page)
    let resolveSocket: (socket: WebSocketRoute) => void = () => undefined
    const socketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveSocket = resolve
    })
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/makeup-sessions$/,
        (socket) => socket.onMessage(() => resolveSocket(socket))
    )
    const retake = {
        id: 52,
        class_id: 11,
        class_name: "Class 8B",
        join_code: "REMOTE52",
        status: "in_progress",
        quizzes: [
            { id: 31, title: "Science checkpoint", duration_seconds: 1800 },
        ],
        participant_count: 1,
        created_at: "2026-01-06T10:00:00Z",
    }
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()
    const socket = await socketReady
    socket.send(JSON.stringify({ type: "makeup_sessions", data: [retake] }))
    await page
        .getByRole("article")
        .filter({ hasText: "REMOTE52" })
        .getByRole("button", { name: "Open waiting room" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Retake" })
    await expect(dialog.getByText("REMOTE52")).toBeVisible()

    socket.send(
        JSON.stringify({
            type: "makeup_sessions",
            data: [{ ...retake, status: "finished" }],
        })
    )

    await expect(dialog).toBeHidden()
    await expect(
        page.getByRole("button", { name: "Delete session" })
    ).toHaveCount(0)
})

test("the quiz duration can be cleared and typed again", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard?section=exam-quizzes")
    await page.getByRole("button", { name: "New exam quiz" }).click()
    const dialog = page.getByRole("dialog", { name: "New exam quiz" })
    await dialog.getByLabel("Quiz title").fill("Energy assessment")
    await dialog.getByLabel("Grade level").selectOption("Grade 8")
    await dialog.getByText("Matter and energy", { exact: true }).click()
    await dialog.getByLabel("Easy", { exact: true }).fill("10")
    const duration = dialog.getByLabel("Overall duration (minutes)")
    await duration.clear()
    await duration.pressSequentially("30")
    await expect(duration).toHaveValue("30")
    await dialog.getByRole("button", { name: "New quiz", exact: true }).click()

    await expect(
        page.getByRole("heading", { name: "Energy assessment" })
    ).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/quizzes" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toMatchObject({ duration_seconds: 1800 })
})

test("a failed training save restores the question count too", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.route(
        "**/api/quizzes/training/classes/11/question-banks",
        (route) =>
            route.request().method() === "PUT"
                ? route.fulfill({ status: 500, json: {} })
                : route.fallback()
    )
    await page.goto("/teacher/dashboard?section=training-quizzes")
    await expect(page.getByLabel("Class")).toHaveValue("11")
    const configurationDialog = page.getByRole("dialog", {
        name: "Configure question bank",
    })
    await page.getByText("Matter and energy", { exact: true }).click()
    await configurationDialog.getByLabel("Number of questions").fill("4")
    await configurationDialog.getByRole("button", { name: "Save" }).click()
    await expect(page.getByRole("alert")).toBeVisible()

    await page.getByText("Matter and energy", { exact: true }).click()
    await expect(
        configurationDialog.getByLabel("Number of questions")
    ).toHaveValue("10")
})
