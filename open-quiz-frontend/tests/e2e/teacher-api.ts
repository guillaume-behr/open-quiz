// The teacher account, its class and the mocked API every teacher spec starts from.
import { type Page, type Request } from "./fixtures"

export const teacher = {
    id: 7,
    username: "ada",
    display_name: "Ada Lovelace",
    is_admin: false,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
}

export const existingClass = {
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

/** Mocks every API route the teacher dashboard calls, recording each request. */
export async function mockTeacherApi(page: Page) {
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
        trainable_question_count: 30,
        quiz_count: 1,
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
        if (url.pathname === "/api/classes/grade-levels") {
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
                    trainable_question_count: 0,
                    quiz_count: 0,
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
            return route.fulfill({
                json: { ...updated, published_sessions_not_regraded: 2 },
            })
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
                    participant_count: 1,
                    participants: [
                        {
                            id: 901,
                            student_identifier: "student-1",
                            student_display_name: "Student One",
                            answered_count: 0,
                            score: 0,
                            maximum_score: 0,
                            pending_manual_grading_count: 0,
                            violation_count: 0,
                            last_violation_type: null,
                            last_violation_at: null,
                            joined_at: "2026-01-06T00:01:00Z",
                            quiz_title: "Science checkpoint",
                            total_questions: 10,
                        },
                    ],
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
