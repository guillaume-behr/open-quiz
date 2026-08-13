import {
    expect,
    test,
    type Page,
    type Request,
    type WebSocketRoute,
} from "@playwright/test"

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
            total_questions: 10,
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
        grade_level: "Grade 8",
        created_at: "2026-01-03T00:00:00Z",
    }
    const availableStudentAccount = {
        ...studentAccount,
        id: 43,
        identifier: "dorothy-v",
        display_name: "Dorothy Vaughan",
        class_id: 99,
        class_name: "Former class",
        grade_level: "Grade 7",
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
                total_questions: 10,
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
                    request.postDataJSON() as {
                        question_banks: {
                            question_bank_id: number
                            question_count: number
                        }[]
                    }
                ).question_banks.map((item) => item.question_bank_id)
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
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()
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
    await bankCard.getByRole("button", { name: "Edit question bank" }).click()
    const questionsDialog = page.getByRole("dialog", {
        name: "Edit question bank",
    })
    const questionFilters = questionsDialog.getByRole("button", {
        name: /Filters/,
    })
    await expect(questionFilters).toHaveAttribute("aria-expanded", "false")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeHidden()
    await questionFilters.click()
    await expect(questionFilters).toHaveAttribute("aria-expanded", "true")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeVisible()
    await questionFilters.click()
    await expect(questionFilters).toHaveAttribute("aria-expanded", "false")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeHidden()
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
        questionsDialog.locator("ol").getByText("Hard", { exact: true })
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

    await expect(
        page.getByRole("article").filter({ hasText: "Class 9A" })
    ).toBeVisible()
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
    await editDialog
        .getByRole("combobox", { name: "Class", exact: true })
        .fill("Class 8 Advanced")
    await editDialog.getByRole("button", { name: "Save class" }).click()
    await expect(page.getByText("Class 8 Advanced")).toBeVisible()

    const updatedCard = page.getByRole("article").filter({
        hasText: "Class 8 Advanced",
    })
    await updatedCard.getByRole("button", { name: "Edit class" }).click()
    const manageDialog = page.getByRole("dialog", {
        name: "Edit class",
    })
    await manageDialog.getByRole("button", { name: "Assign a student" }).click()
    const assignDialog = page.getByRole("dialog", {
        name: "Assign a student",
    })
    const availableStudent = assignDialog
        .getByRole("button")
        .filter({ hasText: "Dorothy Vaughan" })
    await expect(availableStudent).toContainText("Former class")
    await expect(availableStudent).toContainText("Grade 7")
    await availableStudent.click()
    await assignDialog.getByRole("button", { name: "Assign 1 student" }).click()
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

    await expect(page.getByText("hopper-grace", { exact: true })).toBeVisible()
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
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()

    await page.getByPlaceholder("Search for a class").fill("first request")
    await expect(page.getByRole("alert")).toHaveText("Failed to load classes.")
    await page.getByPlaceholder("Search for a class").fill("Class")
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()
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
    await socket.send(
        JSON.stringify({ type: "active_sessions", data: [waitingSession] })
    )
    await expect(
        page.getByRole("heading", { name: "Active quizzes" })
    ).toBeVisible()
    await socket.send(
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
        .poll(() =>
            requests
                .find(
                    (request) =>
                        new URL(request.url()).pathname ===
                            "/api/quizzes/training/classes/11/question-banks" &&
                        request.method() === "PUT"
                )
                ?.postDataJSON()
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
    let resolveStartedSocket: (socket: WebSocketRoute) => void = () => undefined
    const waitingSocketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveWaitingSocket = resolve
    })
    const startedSocketReady = new Promise<WebSocketRoute>((resolve) => {
        resolveStartedSocket = resolve
    })
    let authenticatedSocketCount = 0
    await page.routeWebSocket(
        /\/api\/quizzes\/live\/teacher\/sessions\/80$/,
        (socket) => {
            socket.onMessage(() => {
                authenticatedSocketCount += 1
                if (authenticatedSocketCount === 1) {
                    resolveWaitingSocket(socket)
                } else {
                    resolveStartedSocket(socket)
                }
            })
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
    await waitingSocketReady
    await sessionDialog.getByRole("button", { name: "Start quiz" }).click()
    await expect(sessionDialog.getByText("Quiz started")).toBeVisible()
    const startedSocket = await startedSocketReady
    await startedSocket.send(
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
    await socket.send(
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

test("question bank import identifies JSON syntax and validation locations", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page.getByRole("button", { name: "Import" }).click()

    const dialog = page.getByRole("dialog", {
        name: "Import a question bank",
    })
    const fileInput = dialog.getByLabel(".json file")
    await fileInput.setInputFiles({
        name: "invalid.json",
        mimeType: "application/json",
        buffer: Buffer.from('{\n  "version": 1,\n  "questions": [}\n'),
    })
    await dialog.getByRole("button", { name: "Import" }).click()
    await expect(dialog.getByRole("alert")).toContainText(
        /JSON — line 3, column \d+:/
    )

    await page.route("**/api/question-banks/import", async (route) => {
        await route.fulfill({
            status: 422,
            json: {
                detail: [
                    {
                        type: "string_too_short",
                        loc: ["body", "questions", 1, "choices", 0, "label"],
                        msg: "String should have at least 1 character",
                    },
                ],
            },
        })
    })
    await fileInput.setInputFiles({
        name: "invalid-bank.json",
        mimeType: "application/json",
        buffer: Buffer.from(
            JSON.stringify({
                version: 1,
                question_bank: {
                    grade_level: "Grade 8",
                    chapter: "Invalid bank",
                },
                questions: [],
            })
        ),
    })
    await dialog.getByRole("button", { name: "Import" }).click()
    await expect(dialog.getByRole("alert")).toContainText(
        "$.questions[1].choices[0].label: String should have at least 1 character"
    )
})

test("teacher creates and controls a retake session", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Retake", exact: true }).click()

    const activePanel = page.getByRole("region", { name: "Retake" })
    const dashboardGrid = activePanel.locator("..")
    const activePanelBox = await activePanel.boundingBox()
    const dashboardGridBox = await dashboardGrid.boundingBox()
    expect(activePanelBox).not.toBeNull()
    expect(dashboardGridBox).not.toBeNull()
    expect(activePanelBox!.height).toBeCloseTo(dashboardGridBox!.height, 0)

    const classSelector = page.getByRole("combobox", { name: "Class" })
    const createButton = page.getByRole("button", { name: "Create session" })
    const createForm = page
        .getByRole("heading", { name: "New retake session" })
        .locator("xpath=ancestor::form")
    const classSelectorBox = await classSelector.boundingBox()
    const createButtonBox = await createButton.boundingBox()
    const createFormBox = await createForm.boundingBox()
    expect(classSelectorBox).not.toBeNull()
    expect(createButtonBox).not.toBeNull()
    expect(createFormBox).not.toBeNull()
    expect(createButtonBox!.width).toBeCloseTo(classSelectorBox!.width, 0)
    expect(createFormBox!.width).toBeCloseTo(classSelectorBox!.width + 42, 0)

    await classSelector.selectOption("11")
    await page.getByText("Science checkpoint", { exact: true }).click()
    await createButton.click()

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
    await socket.send(
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

test("teacher reviews, grades, exports, and deletes quiz results", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Results", exact: true }).click()
    await expect(
        page.getByRole("heading", { name: "Results", level: 3 })
    ).toBeVisible()
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
    const resultStatusIcon = resultCard.getByRole("img", {
        name: "Grades not published",
    })
    const resultTitle = resultCard.getByRole("heading", {
        name: "Science checkpoint",
    })
    await expect(resultStatusIcon).toHaveClass(/text-amber-700/)
    const resultStatusIconBox = await resultStatusIcon.boundingBox()
    const resultTitleBox = await resultTitle.boundingBox()
    expect(resultStatusIconBox).not.toBeNull()
    expect(resultTitleBox).not.toBeNull()
    expect(resultStatusIconBox!.x + resultStatusIconBox!.width).toBeLessThan(
        resultTitleBox!.x
    )
    await page.getByRole("button", { name: "Schedule" }).click()
    await expect(
        page.getByRole("button", { name: "Previous week" })
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Next week" })).toBeVisible()
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
    await expect
        .poll(() =>
            resultDialog.evaluate((element) =>
                element
                    .getAnimations()
                    .every((animation) => animation.playState === "finished")
            )
        )
        .toBe(true)
    const scoreHeadingBox = await scoreHeading.boundingBox()
    const participantScoreBox = await participantScore.boundingBox()
    expect(scoreHeadingBox).not.toBeNull()
    expect(participantScoreBox).not.toBeNull()
    expect(participantScoreBox!.x).toBeCloseTo(scoreHeadingBox!.x, 0)
    expect(participantScoreBox!.width).toBeCloseTo(scoreHeadingBox!.width, 0)
    const medianGapIndicator = resultDialog.getByRole("button", {
        name: "Available points differ from the median by at least 3 points",
    })
    await expect(medianGapIndicator).toBeVisible()
    const medianGapIndicatorBox = await medianGapIndicator.boundingBox()
    const participantScoreValueBox = await participantScore
        .locator("span")
        .last()
        .boundingBox()
    expect(medianGapIndicatorBox).not.toBeNull()
    expect(participantScoreValueBox).not.toBeNull()
    expect(
        medianGapIndicatorBox!.x + medianGapIndicatorBox!.width
    ).toBeLessThan(participantScoreValueBox!.x)
    await medianGapIndicator.hover()
    await expect(
        page
            .getByRole("tooltip")
            .getByText(
                "Available points differ from the median by at least 3 points"
            )
    ).toBeVisible()
    await expect(
        resultDialog.getByText("alex-8b", { exact: true })
    ).toHaveCount(1)
    const pendingGradingIndicator = resultDialog.getByRole("button", {
        name: "1 to grade",
    })
    await expect(pendingGradingIndicator).toBeVisible()
    const participantRow = resultDialog.locator('[data-participant-id="91"]')
    await expect(participantRow).toHaveClass(/bg-amber-500\/10/)
    const participantGradingStatus = participantRow.locator(
        '[data-grading-status="pending"]'
    )
    await expect(participantGradingStatus).toHaveClass(/text-amber-700/)
    await pendingGradingIndicator.hover()
    await expect(
        page.getByRole("tooltip").getByText("1 to grade")
    ).toBeVisible()
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
    await expect(participantRow).not.toHaveClass(/bg-amber-500\/10/)
    await expect(
        participantRow.locator('[data-grading-status="complete"]')
    ).toHaveClass(/text-emerald-700/)
    await expect(
        resultDialog.getByRole("button", { name: "1 to grade" })
    ).toHaveCount(0)
    await expect(medianGapIndicator).toBeVisible()
    await resultDialog.getByRole("button", { name: "Publish grades" }).click()
    await expect(
        resultDialog.getByRole("button", { name: "Grades published" })
    ).toBeDisabled()
    await resultDialog.getByRole("button", { name: "View answers" }).click()
    await expect(answersDialog.getByLabel("Awarded score")).toBeDisabled()
    await expect(
        answersDialog.getByRole("button", { name: "Update score" })
    ).toBeDisabled()
    await answersDialog.getByRole("button", { name: "Close" }).click()
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname ===
                    "/api/quizzes/sessions/90/publish-grades" &&
                request.method() === "POST"
        )
    ).toBe(true)
    await resultDialog.getByRole("button", { name: "Close" }).click()
    await expect(
        resultCard.getByRole("img", { name: "Grades published" })
    ).toHaveClass(/text-emerald-700/)

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
        duration_seconds: 900,
        easy_question_count: 10,
        medium_question_count: 0,
        hard_question_count: 0,
    })
})
