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
    students: [
        {
            id: 40,
            class_id: 11,
            account_id: 41,
            identifier: "alex-8b",
            display_name: "Alex Example",
            created_at: "2026-01-03T00:00:00Z",
        },
    ],
    created_at: "2026-01-02T00:00:00Z",
}

async function mockTeacherApi(page: Page) {
    const requests: Request[] = []
    let classes = [existingClass]
    let trainingBankIds: number[] = []
    let activeSessions: Array<Record<string, unknown>> = []
    let resultSessions: Array<Record<string, unknown>> = [
        {
            id: 90,
            quiz_id: 31,
            quiz_title: "Science checkpoint",
            class_id: 11,
            class_name: "Class 8B",
            join_code: "DONE90",
            status: "finished",
            participant_count: 1,
            median_maximum_score: 5,
            participants: [
                {
                    id: 91,
                    student_identifier: "alex-8b",
                    student_display_name: "Alex Example",
                    answered_count: 10,
                    score: 2,
                    maximum_score: 10,
                    pending_manual_grading_count: 1,
                    violation_count: 1,
                    last_violation_type: "fullscreen_exit",
                    last_violation_at: "2026-01-06T10:10:00Z",
                    joined_at: "2026-01-06T10:00:00Z",
                },
            ],
            current_question_number: 10,
            total_questions: 10,
            current_submission_count: 1,
            created_at: "2026-01-06T10:00:00Z",
            started_at: "2026-01-06T10:01:00Z",
            ends_at: "2026-01-06T10:31:00Z",
            grades_published_at: null,
        },
    ]
    let writtenAnswer = {
        id: 92,
        question_id: 93,
        position: 10,
        prompt: "Explain the energy transfer.",
        difficulty: "hard",
        answer_mode: "written",
        submitted_answers: ["Energy moves between systems."],
        expected_answers: ["Energy is conserved while being transferred."],
        score: 0,
        max_score: 5,
        is_graded: false,
        is_correct: null as boolean | null,
    }
    let makeupSessions = [
        {
            id: 50,
            class_id: 11,
            class_name: "Class 8B",
            join_code: "OLD123",
            status: "cancelled",
            quizzes: [
                {
                    id: 31,
                    title: "Previous checkpoint",
                    duration_seconds: 900,
                },
            ],
            participant_count: 0,
            created_at: "2026-01-01T00:00:00Z",
        },
    ]
    const studentAccount = {
        id: 41,
        identifier: "alex-8b",
        display_name: "Alex Example",
        is_active: true,
        class_id: 11,
        class_name: "Class 8B",
        created_at: "2026-01-03T00:00:00Z",
    }
    const availableStudentAccount = {
        ...studentAccount,
        id: 43,
        identifier: "dorothy-v",
        display_name: "Dorothy Vaughan",
        class_id: 99,
        class_name: "Former class",
    }
    let students = [studentAccount, availableStudentAccount]
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
    let questionBanks = [bank, otherGradeBank]
    let questions: Array<Record<string, unknown>> = []
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
            if (request.method() === "POST") {
                const body = request.postDataJSON() as { name: string }
                return route.fulfill({
                    status: 201,
                    json: { id: 2, name: body.name },
                })
            }
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
        const classUpdateMatch = url.pathname.match(
            /^\/api\/classes\/(\d+)\/update$/
        )
        if (classUpdateMatch && request.method() === "POST") {
            const id = Number(classUpdateMatch[1])
            const body = request.postDataJSON() as {
                name: string
                grade_level: string
            }
            const updated = {
                ...classes.find((item) => item.id === id)!,
                name: body.name,
                grade_level: body.grade_level,
            }
            classes = classes.map((item) => (item.id === id ? updated : item))
            return route.fulfill({ json: updated })
        }
        const classAccountMatch = url.pathname.match(
            /^\/api\/classes\/(\d+)\/accounts\/(\d+)$/
        )
        if (classAccountMatch) {
            const classId = Number(classAccountMatch[1])
            const accountId = Number(classAccountMatch[2])
            if (request.method() === "DELETE") {
                classes = classes.map((item) =>
                    item.id === classId
                        ? {
                              ...item,
                              student_count: Math.max(
                                  0,
                                  item.student_count - 1
                              ),
                              students: item.students.filter(
                                  (student) => student.account_id !== accountId
                              ),
                          }
                        : item
                )
                return route.fulfill({ status: 204 })
            }
            const account = students.find((item) => item.id === accountId)!
            const updated = {
                ...classes.find((item) => item.id === classId)!,
                student_count:
                    classes.find((item) => item.id === classId)!.student_count +
                    1,
                students: [
                    {
                        id: 101,
                        class_id: classId,
                        account_id: account.id,
                        identifier: account.identifier,
                        display_name: account.display_name,
                        created_at: account.created_at,
                    },
                ],
            }
            classes = classes.map((item) =>
                item.id === classId ? updated : item
            )
            return route.fulfill({ json: updated })
        }
        const classDeleteMatch = url.pathname.match(/^\/api\/classes\/(\d+)$/)
        if (classDeleteMatch && request.method() === "DELETE") {
            classes = classes.filter(
                (item) => item.id !== Number(classDeleteMatch[1])
            )
            return route.fulfill({ status: 204 })
        }
        if (url.pathname === "/api/question-banks/import") {
            const imported = {
                ...bank,
                id: 24,
                grade_level: "Grade 10",
                chapter: "Imported mechanics",
                question_count: 1,
            }
            questionBanks = [...questionBanks, imported]
            return route.fulfill({
                status: 201,
                json: {
                    question_bank: imported,
                    questions: [{ id: 70 }],
                },
            })
        }
        if (url.pathname === "/api/question-banks/example") {
            return route.fulfill({
                contentType: "application/json",
                body: '{"grade_level":"Grade 8","chapter":"Example"}',
            })
        }
        const bankExportMatch = url.pathname.match(
            /^\/api\/question-banks\/(\d+)\/export$/
        )
        if (bankExportMatch) {
            return route.fulfill({
                contentType: "application/json",
                body: JSON.stringify({
                    grade_level: "Grade 8",
                    chapter: "Matter and energy",
                }),
            })
        }
        const bankDeleteMatch = url.pathname.match(
            /^\/api\/question-banks\/(\d+)$/
        )
        if (bankDeleteMatch && request.method() === "DELETE") {
            questionBanks = questionBanks.filter(
                (item) => item.id !== Number(bankDeleteMatch[1])
            )
            return route.fulfill({ status: 204 })
        }
        if (url.pathname === "/api/question-banks") {
            if (request.method() === "POST") {
                const body = request.postDataJSON() as {
                    grade_level: string
                    chapter: string
                }
                const created = {
                    ...bank,
                    id: 23,
                    grade_level: body.grade_level,
                    chapter: body.chapter,
                    question_count: 0,
                    easy_question_count: 0,
                    medium_question_count: 0,
                    hard_question_count: 0,
                }
                questionBanks = [...questionBanks, created]
                return route.fulfill({ status: 201, json: created })
            }
            return route.fulfill({
                json: questionBanks,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "100",
                    "X-Total-Count": String(questionBanks.length),
                },
            })
        }
        if (url.pathname === "/api/question-banks/21/questions") {
            if (request.method() === "POST") {
                const created = {
                    id: 61,
                    question_bank_id: 21,
                    prompt: "Which form of energy is stored?",
                    points: 1,
                    difficulty: "hard",
                    answer_mode: "single",
                    answer_mode_disclosed: true,
                    response_language: null,
                    has_image: false,
                    code_language: null,
                    code_content: null,
                    choices: [
                        {
                            id: 62,
                            label: "Potential energy",
                            is_correct: true,
                            points: 4,
                            position: 0,
                            has_image: false,
                            code_language: null,
                            code_content: null,
                        },
                        {
                            id: 63,
                            label: "Sound energy",
                            is_correct: false,
                            points: -1,
                            position: 1,
                            has_image: false,
                            code_language: null,
                            code_content: null,
                        },
                    ],
                    created_at: "2026-01-06T12:00:00Z",
                }
                questions = [created]
                return route.fulfill({ status: 201, json: created })
            }
            return route.fulfill({ json: questions })
        }
        if (url.pathname === "/api/question-banks/questions/61/update") {
            const updated = {
                ...questions[0],
                prompt: "Which kind of energy is stored?",
            }
            questions = [updated]
            return route.fulfill({ json: updated })
        }
        if (
            url.pathname === "/api/question-banks/questions/61" &&
            request.method() === "DELETE"
        ) {
            questions = []
            return route.fulfill({ status: 204 })
        }
        if (url.pathname === "/api/students" && request.method() === "POST") {
            const body = request.postDataJSON() as {
                first_name: string
                last_name: string
            }
            const created = {
                ...studentAccount,
                id: 42,
                identifier: "hopper-grace",
                display_name: `${body.first_name} ${body.last_name}`,
                class_id: studentAccount.class_id,
                class_name: studentAccount.class_name,
                generated_password: "generated-password",
            }
            students = [...students, created]
            return route.fulfill({ status: 201, json: created })
        }
        const studentUpdateMatch = url.pathname.match(
            /^\/api\/students\/(\d+)\/update$/
        )
        if (studentUpdateMatch && request.method() === "POST") {
            const id = Number(studentUpdateMatch[1])
            const updated = {
                ...students.find((student) => student.id === id)!,
                ...(request.postDataJSON() as Record<string, unknown>),
            }
            students = students.map((student) =>
                student.id === id ? updated : student
            )
            return route.fulfill({ json: updated })
        }
        const studentDeleteMatch = url.pathname.match(
            /^\/api\/students\/(\d+)$/
        )
        if (studentDeleteMatch && request.method() === "DELETE") {
            students = students.filter(
                (student) => student.id !== Number(studentDeleteMatch[1])
            )
            return route.fulfill({ status: 204 })
        }
        if (url.pathname === "/api/students") {
            return route.fulfill({
                json: students,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "12",
                    "X-Total-Count": String(students.length),
                },
            })
        }
        if (url.pathname === "/api/quizzes/sessions/active") {
            return route.fulfill({ json: activeSessions })
        }
        if (url.pathname === "/api/quizzes/sessions/results") {
            return route.fulfill({
                json: resultSessions,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": String(resultSessions.length),
                },
            })
        }
        if (url.pathname === "/api/quizzes/sessions/results/export") {
            return route.fulfill({
                status: 200,
                contentType: "text/csv; charset=utf-8",
                body: "student,score\nAlex Example,5.5\n",
            })
        }
        if (
            url.pathname === "/api/quizzes/sessions/90/participants/91/answers"
        ) {
            return route.fulfill({ json: [writtenAnswer] })
        }
        if (url.pathname === "/api/quizzes/sessions/90/answers/92/grade") {
            const { score } = request.postDataJSON() as { score: number }
            writtenAnswer = {
                ...writtenAnswer,
                score,
                is_graded: true,
                is_correct: score >= writtenAnswer.max_score,
            }
            resultSessions = resultSessions.map((result) => ({
                ...result,
                participants: (
                    result.participants as Array<Record<string, unknown>>
                ).map((participant) => ({
                    ...participant,
                    score: Number(participant.score) + score,
                    pending_manual_grading_count: 0,
                })),
            }))
            return route.fulfill({ json: writtenAnswer })
        }
        if (
            url.pathname === "/api/quizzes/sessions/90/publish-grades" &&
            request.method() === "POST"
        ) {
            resultSessions = resultSessions.map((result) => ({
                ...result,
                grades_published_at: "2026-01-06T11:00:00Z",
            }))
            return route.fulfill({ json: resultSessions[0] })
        }
        if (url.pathname === "/api/quizzes/makeup/quiz-options") {
            return route.fulfill({ json: quizzes })
        }
        const launchMatch = url.pathname.match(
            /^\/api\/quizzes\/(\d+)\/launch$/
        )
        if (launchMatch) {
            const created = {
                id: 80,
                quiz_id: Number(launchMatch[1]),
                quiz_title: "Science checkpoint",
                class_id: 11,
                class_name: "Class 8B",
                join_code: "LIVE80",
                status: "waiting",
                participant_count: 1,
                participants: [
                    {
                        id: 81,
                        student_identifier: "alex-8b",
                        student_display_name: "Alex Example",
                        answered_count: 0,
                        score: 0,
                        pending_manual_grading_count: 0,
                        violation_count: 0,
                        last_violation_type: null,
                        last_violation_at: null,
                        joined_at: "2026-01-06T10:00:00Z",
                    },
                ],
                current_question_number: null,
                total_questions: 10,
                current_submission_count: 0,
                created_at: "2026-01-06T10:00:00Z",
                started_at: null,
                ends_at: null,
            }
            activeSessions = [created]
            return route.fulfill({ status: 201, json: created })
        }
        const sessionMatch = url.pathname.match(
            /^\/api\/quizzes\/sessions\/(\d+)$/
        )
        if (sessionMatch) {
            const id = Number(sessionMatch[1])
            if (request.method() === "DELETE") {
                activeSessions = activeSessions.filter(
                    (session) => session.id !== id
                )
                resultSessions = resultSessions.filter(
                    (session) => session.id !== id
                )
                return route.fulfill({ status: 204 })
            }
            return route.fulfill({
                json: activeSessions.find((session) => session.id === id),
            })
        }
        const sessionControlMatch = url.pathname.match(
            /^\/api\/quizzes\/sessions\/(\d+)\/(start|pause|resume|cancel)$/
        )
        if (sessionControlMatch) {
            const id = Number(sessionControlMatch[1])
            const action = sessionControlMatch[2]
            const status =
                action === "start" || action === "resume"
                    ? "in_progress"
                    : action === "pause"
                      ? "paused"
                      : "cancelled"
            const updated = {
                ...activeSessions.find((session) => session.id === id)!,
                status,
                started_at: action === "start" ? "2026-01-06T10:01:00Z" : null,
                ends_at:
                    status === "in_progress" ? "2026-01-06T10:31:00Z" : null,
            }
            activeSessions = activeSessions.map((session) =>
                session.id === id ? updated : session
            )
            return route.fulfill({ json: updated })
        }
        if (url.pathname === "/api/quizzes/makeup/sessions") {
            if (request.method() === "POST") {
                const created = {
                    id: 51,
                    class_id: 11,
                    class_name: "Class 8B",
                    join_code: "MAKE51",
                    status: "waiting",
                    quizzes: [
                        {
                            id: 31,
                            title: "Science checkpoint",
                            duration_seconds: 1800,
                        },
                    ],
                    participant_count: 0,
                    created_at: "2026-01-06T00:00:00Z",
                }
                makeupSessions = [created, ...makeupSessions]
                return route.fulfill({ status: 201, json: created })
            }
            return route.fulfill({ json: makeupSessions })
        }
        const makeupControlMatch = url.pathname.match(
            /^\/api\/quizzes\/makeup\/sessions\/(\d+)\/(start|pause|resume|finish|cancel)$/
        )
        if (makeupControlMatch) {
            const id = Number(makeupControlMatch[1])
            const action = makeupControlMatch[2]
            const status =
                action === "start" || action === "resume"
                    ? "in_progress"
                    : action === "pause"
                      ? "paused"
                      : action === "finish"
                        ? "finished"
                        : "cancelled"
            const updated = {
                ...makeupSessions.find((session) => session.id === id)!,
                status,
            }
            makeupSessions = makeupSessions.map((session) =>
                session.id === id ? updated : session
            )
            return route.fulfill({ json: updated })
        }
        if (
            url.pathname === "/api/quizzes/training/classes/11/question-banks"
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
    await page.getByRole("button", { name: "Classes", exact: true }).click()
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

test("teacher creates, exports, imports, and deletes question banks", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()

    await page.getByRole("button", { name: "New question bank" }).click()
    const createDialog = page.getByRole("dialog", {
        name: "New question bank",
    })
    await createDialog.getByLabel("Grade level").selectOption("Grade 8")
    await createDialog.getByLabel("Question bank title").fill("Thermodynamics")
    await createDialog.getByRole("button", { name: "Create" }).click()
    await expect(page.getByText("Thermodynamics")).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/question-banks" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({ grade_level: "Grade 8", chapter: "Thermodynamics" })

    const existingBank = page.getByRole("listitem").filter({
        hasText: "Matter and energy",
    })
    const exportPromise = page.waitForEvent("download")
    await existingBank.getByRole("button", { name: "Export" }).click()
    expect((await exportPromise).suggestedFilename()).toBe(
        "banque-grade-8-matter-and-energy.json"
    )

    const examplePromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Download example" }).click()
    expect((await examplePromise).suggestedFilename()).toBe(
        "open-quiz-questions-example.json"
    )

    await page.getByRole("button", { name: "Import" }).click()
    const importDialog = page.getByRole("dialog", {
        name: "Import a question bank",
    })
    await importDialog.getByLabel(".json file").setInputFiles({
        name: "mechanics.json",
        mimeType: "application/json",
        buffer: Buffer.from('{"grade_level":"Grade 10"}'),
    })
    await importDialog.getByRole("button", { name: "Import" }).click()
    await expect(page.getByText("Imported mechanics")).toBeVisible()
    await expect(page.getByRole("status")).toHaveText(
        "New question bank created with 1 question."
    )

    const createdBank = page.getByRole("listitem").filter({
        hasText: "Thermodynamics",
    })
    await createdBank
        .getByRole("button", { name: "Delete question bank" })
        .click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete question bank",
    })
    await deleteDialog
        .getByRole("button", { name: "Delete question bank" })
        .click()
    await expect(page.getByText("Thermodynamics")).toHaveCount(0)
})

test("teacher creates, edits, and deletes a scored question", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()

    const bankCard = page.getByRole("listitem").filter({
        hasText: "Matter and energy",
    })
    await bankCard.getByRole("button", { name: "Add/edit questions" }).click()
    const questionsDialog = page.getByRole("dialog", {
        name: "Matter and energy",
    })
    await questionsDialog
        .getByRole("button", { name: "Add a question" })
        .click()

    const addDialog = page.getByRole("dialog", { name: "Add a question" })
    await addDialog
        .getByLabel("Question")
        .fill("Which form of energy is stored?")
    await addDialog.getByLabel("Difficulty").selectOption("hard")
    await addDialog.getByPlaceholder("Choice 1").fill("Potential energy")
    await addDialog.getByPlaceholder("Choice 2").fill("Sound energy")
    await addDialog.getByLabel("Points for choice 1").fill("4")
    await addDialog.getByLabel("Points for choice 2").fill("-1")
    await addDialog.getByRole("button", { name: "Save question" }).click()

    await expect(
        questionsDialog.getByText("1. Which form of energy is stored?")
    ).toBeVisible()
    await expect(
        questionsDialog.getByText("Hard", { exact: true })
    ).toBeVisible()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname ===
                "/api/question-banks/21/questions" &&
            request.method() === "POST"
    )
    expect(createRequest?.postData()).toContain(
        "Which form of energy is stored?"
    )
    expect(createRequest?.postData()).toContain("Potential energy")
    expect(createRequest?.postData()).toContain('"points":4')
    expect(createRequest?.postData()).toContain('"points":-1')

    await questionsDialog.getByRole("button", { name: "Edit" }).click()
    const editDialog = page.getByRole("dialog", { name: "Edit question" })
    await editDialog
        .getByLabel("Question")
        .fill("Which kind of energy is stored?")
    await editDialog.getByRole("button", { name: "Save changes" }).click()
    await expect(
        questionsDialog.getByText("1. Which kind of energy is stored?")
    ).toBeVisible()

    await questionsDialog
        .getByRole("button", { name: "Delete question" })
        .click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete question",
    })
    await deleteDialog.getByRole("button", { name: "Delete question" }).click()
    await expect(
        questionsDialog.getByText("No questions in this question bank.")
    ).toBeVisible()
})

test("teacher can create a class", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
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

test("teacher updates a class and manages student assignments", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    const classCard = page.getByRole("article").filter({ hasText: "Class 8B" })
    await classCard.getByRole("button", { name: "Edit class" }).click()
    const editDialog = page.getByRole("dialog", { name: "Edit class" })
    await editDialog.getByLabel("Class").fill("Class 8 Advanced")
    await editDialog.getByRole("button", { name: "Save class" }).click()
    await expect(page.getByText("Class 8 Advanced")).toBeVisible()

    const updatedCard = page.getByRole("article").filter({
        hasText: "Class 8 Advanced",
    })
    await updatedCard.getByRole("button", { name: "Manage students" }).click()
    const manageDialog = page.getByRole("dialog", {
        name: "Class 8 Advanced",
    })
    await manageDialog.getByRole("button", { name: "Assign a student" }).click()
    const assignDialog = page.getByRole("dialog", {
        name: "Assign a student",
    })
    await expect(assignDialog.locator("select")).toContainText(
        "Dorothy Vaughan"
    )
    await assignDialog.getByRole("button", { name: "Assign" }).click()
    await expect(manageDialog.getByText("Dorothy Vaughan")).toBeVisible()

    await manageDialog
        .getByRole("button", { name: "Remove from class" })
        .click()
    await expect(manageDialog.getByText("Dorothy Vaughan")).toHaveCount(0)
    await manageDialog.getByRole("button", { name: "Close" }).click()

    await updatedCard.getByRole("button", { name: "Delete class" }).click()
    const deleteDialog = page.getByRole("dialog", { name: "Delete class" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(page.getByText("Class 8 Advanced")).toHaveCount(0)

    expect(
        requests
            .filter((request) =>
                new URL(request.url()).pathname.startsWith("/api/classes/11")
            )
            .map((request) => ({
                method: request.method(),
                path: new URL(request.url()).pathname,
            }))
    ).toEqual([
        { method: "POST", path: "/api/classes/11/update" },
        { method: "POST", path: "/api/classes/11/accounts/43" },
        { method: "DELETE", path: "/api/classes/11/accounts/43" },
        { method: "DELETE", path: "/api/classes/11" },
    ])
})

test("teacher creates, updates, disables, and deletes a student account", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")

    await page.getByRole("button", { name: "New student account" }).click()
    const createDialog = page.getByRole("dialog", {
        name: "New student account",
    })
    await createDialog.getByLabel("First name").fill("Grace")
    await createDialog.getByLabel("Last name").fill("Hopper")
    await createDialog.getByRole("button", { name: "Save student" }).click()

    const credentialsDialog = page.getByRole("dialog", {
        name: "Student credentials created",
    })
    await expect(credentialsDialog.getByText("hopper-grace")).toBeVisible()
    await expect(
        credentialsDialog.getByText("generated-password")
    ).toBeVisible()
    await credentialsDialog.getByText("Close", { exact: true }).click()
    await expect(page.getByText("Grace Hopper")).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/students" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({ first_name: "Grace", last_name: "Hopper" })

    const studentCard = page.getByRole("article").filter({
        hasText: "hopper-grace",
    })
    await studentCard.getByRole("button", { name: "Edit student" }).click()
    const editDialog = page.getByRole("dialog", {
        name: "Edit student account",
    })
    await editDialog.getByLabel("Student name").fill("Rear Admiral Hopper")
    await editDialog.getByLabel("Student ID").fill("grace-hopper")
    await editDialog
        .getByLabel("New password (optional)")
        .fill("new-student-password")
    await editDialog.getByLabel("Active account").uncheck()
    await editDialog.getByRole("button", { name: "Save student" }).click()

    await expect(page.getByText("Rear Admiral Hopper")).toBeVisible()
    await expect(page.getByText(/Account disabled/)).toBeVisible()
    expect(
        requests
            .find((request) =>
                new URL(request.url()).pathname.endsWith("/42/update")
            )
            ?.postDataJSON()
    ).toEqual({
        display_name: "Rear Admiral Hopper",
        identifier: "grace-hopper",
        password: "new-student-password",
        is_active: false,
    })

    const updatedCard = page.getByRole("article").filter({
        hasText: "grace-hopper",
    })
    await updatedCard.getByRole("button", { name: "Delete student" }).click()
    const deleteDialog = page.getByRole("dialog", { name: "Delete student" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(page.getByText("Rear Admiral Hopper")).toHaveCount(0)
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/students/42" &&
                request.method() === "DELETE"
        )
    ).toBe(true)
})

test("class list recovers after a temporary load failure", async ({ page }) => {
    await mockTeacherApi(page)
    await page.route(
        /^http:\/\/127\.0\.0\.1:4173\/api\/classes\?/,
        async (route) => {
            const search = new URL(route.request().url()).searchParams.get(
                "search"
            )
            if (search === "first request") {
                await route.fulfill({ status: 503, body: "{}" })
                return
            }
            await route.fallback()
        }
    )
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
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
    await page.getByRole("button", { name: "Training", exact: true }).click()

    await expect(page.getByLabel("Class")).toHaveValue("11")
    await page.getByText("Matter and energy", { exact: true }).click()
    await expect(
        page.getByText("Advanced matter", { exact: true })
    ).toHaveCount(0)
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

test("teacher launches and controls a live quiz session", async ({ page }) => {
    const requests = await mockTeacherApi(page)
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
    await sessionDialog.getByRole("button", { name: "Start quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()
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
    await expect(sessionDialog.getByText("Quiz cancelled")).toBeVisible()
    await sessionDialog.getByRole("button", { name: "Delete session" }).click()
    const deleteDialog = page.getByRole("dialog", { name: "Delete session" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
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
        { method: "DELETE", action: "80" },
    ])
})

test("teacher creates and controls a retake session", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()

    await page.getByRole("combobox", { name: "Class" }).selectOption("11")
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
    await expect(page.getByText("Class 8B · MAKE51")).toBeVisible()
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

    const sessionCard = page.getByRole("article").filter({ hasText: "MAKE51" })
    await sessionCard.getByRole("button", { name: "Start quiz" }).click()
    await expect(sessionCard.getByText("In progress")).toBeVisible()
    await sessionCard.getByRole("button", { name: "Pause quiz" }).click()
    await expect(sessionCard.getByText("Paused")).toBeVisible()
    await sessionCard.getByRole("button", { name: "Resume quiz" }).click()
    await expect(sessionCard.getByText("In progress")).toBeVisible()
    await sessionCard.getByRole("button", { name: "Finish quiz" }).click()
    await expect(sessionCard.getByText("Finished")).toBeVisible()

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

test("teacher reviews, grades, exports, and deletes quiz results", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Results", exact: true }).click()
    await page
        .getByRole("combobox", { name: "Class", exact: true })
        .selectOption("Class 8B")
    await expect
        .poll(() =>
            requests.some((request) => {
                const url = new URL(request.url())
                return (
                    url.pathname === "/api/quizzes/sessions/results" &&
                    url.searchParams.get("class_search") === "Class 8B"
                )
            })
        )
        .toBe(true)

    const resultCard = page.getByRole("article").filter({
        hasText: "Science checkpoint",
    })
    await expect(resultCard.getByText("Class 8B")).toBeVisible()
    await page.getByRole("button", { name: "Schedule" }).click()
    await expect(page.getByText(/\d{1,2}:00/).first()).toBeVisible()
    await page
        .getByRole("button", { name: "Grade quiz — Science checkpoint" })
        .click()
    await expect(
        page.getByRole("dialog", { name: "Science checkpoint" })
    ).toBeVisible()
    await page
        .getByRole("dialog", { name: "Science checkpoint" })
        .getByRole("button", { name: "Close" })
        .click()
    await page.getByRole("button", { name: "Cards" }).click()
    await resultCard.getByRole("button", { name: "Grade quiz" }).click()

    const resultDialog = page.getByRole("dialog", {
        name: "Science checkpoint",
    })
    await expect(resultDialog.getByText("Class 8B")).toHaveCount(1)
    await expect(resultDialog.getByText("Alex Example")).toBeVisible()
    await expect(
        resultDialog.getByText("Median available points")
    ).toBeVisible()
    const scoreHeading = resultDialog.getByText("Points / possible total", {
        exact: true,
    })
    const participantScore = resultDialog
        .locator("p")
        .filter({ hasText: /2\s*\/\s*10\s*pts?/ })
    await expect(scoreHeading).toBeVisible()
    await expect(participantScore).toBeVisible()
    const scoreHeadingBox = await scoreHeading.boundingBox()
    const participantScoreBox = await participantScore.boundingBox()
    expect(scoreHeadingBox).not.toBeNull()
    expect(participantScoreBox).not.toBeNull()
    expect(participantScoreBox!.x).toBeCloseTo(scoreHeadingBox!.x, 0)
    expect(participantScoreBox!.width).toBeCloseTo(scoreHeadingBox!.width, 0)
    await expect(
        resultDialog.getByText("Available points above the median")
    ).toBeVisible()
    await expect(
        resultDialog.getByText("alex-8b", { exact: true })
    ).toHaveCount(1)
    await expect(resultDialog.getByText("1 to grade")).toBeVisible()
    await resultDialog.getByRole("button", { name: "View answers" }).click()

    const answersDialog = page.getByRole("dialog", { name: "Student answers" })
    await expect(
        answersDialog.getByText("Energy moves between systems.")
    ).toBeVisible()
    await answersDialog.getByLabel("Awarded score").fill("3.5")
    await answersDialog.getByRole("button", { name: "Confirm grade" }).click()
    await expect(answersDialog.getByText("3.5 / 5")).toBeVisible()
    await expect(
        answersDialog.getByText("Energy moves between systems.").locator("..")
    ).toHaveClass(/text-destructive/)
    expect(
        requests
            .find((request) =>
                new URL(request.url()).pathname.endsWith("/answers/92/grade")
            )
            ?.postDataJSON()
    ).toEqual({ score: 3.5 })
    await answersDialog.getByRole("button", { name: "Close" }).click()
    await resultDialog.getByRole("button", { name: "Publish grades" }).click()
    await expect(
        resultDialog.getByRole("button", { name: "Grades published" })
    ).toBeDisabled()
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname ===
                    "/api/quizzes/sessions/90/publish-grades" &&
                request.method() === "POST"
        )
    ).toBe(true)
    await resultDialog.getByRole("button", { name: "Close" }).click()

    await page.getByRole("button", { name: "Export results" }).click()
    const exportDialog = page.getByRole("dialog", { name: "Export results" })
    await exportDialog.getByLabel("Quiz title").selectOption("31")
    const downloadPromise = page.waitForEvent("download")
    await exportDialog.getByRole("button", { name: "Export CSV" }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe("resultats-classe-11-quiz-31.csv")
    expect(
        requests.some((request) => {
            const url = new URL(request.url())
            return (
                url.pathname === "/api/quizzes/sessions/results/export" &&
                url.searchParams.get("class_id") === "11" &&
                url.searchParams.get("quiz_id") === "31"
            )
        })
    ).toBe(true)

    await resultCard.getByRole("button", { name: "Delete this result" }).click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete this result",
    })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(resultCard).toHaveCount(0)
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
        duration_seconds: 1800,
        easy_question_count: 10,
        medium_question_count: 0,
        hard_question_count: 0,
    })
})
