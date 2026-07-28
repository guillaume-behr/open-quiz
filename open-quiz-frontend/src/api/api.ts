const API_URL = import.meta.env.VITE_API_URL ?? ""

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null

export type User = {
    id: number
    username: string
    display_name: string
    is_admin: boolean
    is_active: boolean
    created_at: string
}

export type NewUser = {
    username: string
    display_name: string
    password: string
}

export type Student = {
    id: number
    class_id: number
    identifier: string
    display_name: string
    created_at: string
}

export type StudentClass = {
    id: number
    name: string
    grade_level: string
    student_count: number
    students: Student[]
    created_at: string
}

export type QuestionBank = {
    id: number
    grade_level: string
    chapter: string
    created_at: string
    question_count: number
}

export type NewQuestionBank = {
    grade_level: string
    chapter: string
}

export type QuestionBankImportResult = {
    question_bank: QuestionBank
    questions: Question[]
}

export type QuestionDifficulty = "easy" | "medium" | "hard"
export type AnswerMode = "single" | "multiple" | "written"
export type CodeLanguage =
    | "javascript"
    | "typescript"
    | "python"
    | "java"
    | "csharp"
    | "cpp"
    | "markup"
    | "css"
    | "sql"
    | "bash"
    | "json"

export type QuestionChoice = {
    id: number
    label: string
    is_correct: boolean
    points: number
    position: number
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
}

export type EncodedImage = {
    content_type: "image/jpeg" | "image/png" | "image/webp" | "image/gif"
    data_base64: string
}

export type Question = {
    id: number
    question_bank_id: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: QuestionChoice[]
    created_at: string
}

export type NewQuestion = {
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: Array<{
        id?: number
        label: string
        is_correct: boolean
        points: number
        image?: EncodedImage | null
        remove_image?: boolean
        code_language: CodeLanguage | null
        code_content: string | null
    }>
}

export type QuestionUpdate = NewQuestion & {
    remove_image: boolean
}

export type Quiz = {
    id: number
    title: string
    question_count: number
    duration_seconds: number
    allow_previous_questions: boolean
    easy_percentage: number
    medium_percentage: number
    hard_percentage: number
    question_banks: Array<{
        id: number
        grade_level: string
        chapter: string
        question_count: number
    }>
    created_at: string
}

export type NewQuiz = {
    title: string
    question_bank_ids: number[]
    question_count: number
    duration_seconds: number
    allow_previous_questions: boolean
    easy_percentage: number
    medium_percentage: number
    hard_percentage: number
}

export type QuizParticipant = {
    id: number
    student_identifier: string
    student_display_name: string | null
    answered_count: number
    score: number
    violation_count: number
    last_violation_type: string | null
    last_violation_at: string | null
    joined_at: string
}

export type QuizSession = {
    id: number
    quiz_id: number
    quiz_title: string
    class_id: number | null
    class_name: string
    join_code: string
    status: "waiting" | "in_progress" | "finished"
    participant_count: number
    participants: QuizParticipant[]
    current_question_number: number | null
    total_questions: number
    current_submission_count: number
    created_at: string
    started_at: string | null
    ends_at: string | null
}

export type StudentQuizChoice = {
    id: number
    label: string
    position: number
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
}

export type StudentQuizQuestion = {
    id: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: StudentQuizChoice[]
}

export type StudentQuizSession = {
    quiz_title: string
    class_name: string
    join_code: string
    status: "waiting" | "in_progress" | "finished"
    ends_at: string | null
    question_number: number | null
    total_questions: number
    has_answered: boolean
    answered_count: number
    allow_previous_questions: boolean
    selected_choice_ids: number[] | null
    written_answer: string | null
    question: StudentQuizQuestion | null
}

export type StudentQuizJoin = StudentQuizSession & {
    participant_token: string
}

export type StudentQuizAnswer = {
    selected_choice_ids?: number[]
    written_answer?: string
}

type TokenResponse = {
    access_token: string
}

export class ApiError extends Error {
    readonly status: number

    constructor(message: string, status: number) {
        super(message)
        this.name = "ApiError"
        this.status = status
    }
}

export type TwoFactorChallenge = {
    status: "setup_required" | "verification_required"
    challenge_token: string
    secret: string | null
    provisioning_uri: string | null
}

async function errorFrom(response: Response): Promise<Error> {
    const body = (await response.json().catch(() => ({}))) as {
        detail?: string
    }
    return new ApiError(
        body.detail ?? "Une erreur est survenue.",
        response.status
    )
}

async function refreshAccessToken(): Promise<boolean> {
    if (!refreshPromise) {
        refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
            method: "POST",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok) {
                    accessToken = null
                    return false
                }
                const result = (await response.json()) as TokenResponse
                accessToken = result.access_token
                return true
            })
            .finally(() => {
                refreshPromise = null
            })
    }
    return refreshPromise
}

async function request<T>(
    path: string,
    options: RequestInit = {},
    allowRefresh = true
): Promise<T> {
    const isFormData = options.body instanceof FormData
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: {
            ...(!isFormData ? { "Content-Type": "application/json" } : {}),
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            ...options.headers,
        },
    })

    if (
        response.status === 401 &&
        allowRefresh &&
        (await refreshAccessToken())
    ) {
        return request<T>(path, options, false)
    }
    if (!response.ok) {
        throw await errorFrom(response)
    }
    if (response.status === 204) {
        return undefined as T
    }
    return response.json() as Promise<T>
}

export async function login(
    username: string,
    password: string,
    audience: "professor" | "admin"
): Promise<TwoFactorChallenge> {
    accessToken = null
    return request<TwoFactorChallenge>(
        "/api/auth/login",
        {
            method: "POST",
            body: JSON.stringify({ username, password, audience }),
        },
        false
    )
}

export async function verifyTwoFactor(
    challengeToken: string,
    code: string
): Promise<User> {
    const result = await request<TokenResponse>(
        "/api/auth/2fa/verify",
        {
            method: "POST",
            body: JSON.stringify({
                challenge_token: challengeToken,
                code,
            }),
        },
        false
    )
    accessToken = result.access_token
    return currentUser()
}

export function restoreSession(): Promise<User> {
    return currentUser()
}

export async function logout(): Promise<void> {
    try {
        await request<void>("/api/auth/logout", { method: "POST" }, false)
    } finally {
        accessToken = null
    }
}

function currentUser(): Promise<User> {
    return request<User>("/api/users/me")
}

export function getUsers(): Promise<User[]> {
    return request<User[]>("/api/admin/users")
}

export function getStudentClasses(): Promise<StudentClass[]> {
    return request<StudentClass[]>("/api/classes")
}

export function createStudentClass(
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>("/api/classes", {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function deleteStudentClass(classId: number): Promise<void> {
    return request<void>(`/api/classes/${classId}`, { method: "DELETE" })
}

export function updateStudentClass(
    classId: number,
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>(`/api/classes/${classId}/update`, {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function createStudent(
    classId: number,
    identifier: string,
    displayName: string
): Promise<Student> {
    return request<Student>(`/api/classes/${classId}/students`, {
        method: "POST",
        body: JSON.stringify({
            identifier,
            display_name: displayName,
        }),
    })
}

export function deleteStudent(studentId: number): Promise<void> {
    return request<void>(`/api/classes/students/${studentId}`, {
        method: "DELETE",
    })
}

export function updateStudent(
    studentId: number,
    identifier: string,
    displayName: string
): Promise<Student> {
    return request<Student>(`/api/classes/students/${studentId}/update`, {
        method: "POST",
        body: JSON.stringify({
            identifier,
            display_name: displayName,
        }),
    })
}

export function getQuizzes(): Promise<Quiz[]> {
    return request<Quiz[]>("/api/quizzes")
}

export function createQuiz(quiz: NewQuiz): Promise<Quiz> {
    return request<Quiz>("/api/quizzes", {
        method: "POST",
        body: JSON.stringify(quiz),
    })
}

export function previewQuiz(quizId: number): Promise<Question[]> {
    return request<Question[]>(`/api/quizzes/${quizId}/preview`)
}

export function launchQuiz(
    quizId: number,
    classId: number
): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/${quizId}/launch`, {
        method: "POST",
        body: JSON.stringify({ class_id: classId }),
    })
}

export function getQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}`)
}

export function getActiveQuizSessions(): Promise<QuizSession[]> {
    return request<QuizSession[]>("/api/quizzes/sessions/active")
}

export function startQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}/start`, {
        method: "POST",
    })
}

export function joinQuiz(
    joinCode: string,
    studentIdentifier: string
): Promise<StudentQuizJoin> {
    return request<StudentQuizJoin>(
        "/api/quizzes/join",
        {
            method: "POST",
            body: JSON.stringify({
                join_code: joinCode,
                student_identifier: studentIdentifier,
            }),
        },
        false
    )
}

export function getStudentQuizSession(
    joinCode: string,
    participantToken: string
): Promise<StudentQuizSession> {
    return request<StudentQuizSession>(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}`,
        { headers: { "X-Quiz-Token": participantToken } },
        false
    )
}

export function submitStudentQuizAnswer(
    joinCode: string,
    participantToken: string,
    answer: StudentQuizAnswer
): Promise<StudentQuizSession> {
    return request<StudentQuizSession>(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/answer`,
        {
            method: "POST",
            headers: { "X-Quiz-Token": participantToken },
            body: JSON.stringify(answer),
        },
        false
    )
}

export function navigateStudentQuiz(
    joinCode: string,
    participantToken: string,
    questionNumber: number
): Promise<StudentQuizSession> {
    return request<StudentQuizSession>(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/navigate`,
        {
            method: "POST",
            headers: { "X-Quiz-Token": participantToken },
            body: JSON.stringify({ question_number: questionNumber }),
        },
        false
    )
}

export function reportStudentQuizViolation(
    joinCode: string,
    participantToken: string,
    eventType:
        "fullscreen_exit" | "pointer_exit" | "window_blur" | "page_hidden"
): Promise<void> {
    return request<void>(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/violation`,
        {
            method: "POST",
            headers: { "X-Quiz-Token": participantToken },
            body: JSON.stringify({ event_type: eventType }),
        },
        false
    )
}

export async function getStudentQuizImage(
    path: "questions" | "choices",
    id: number,
    joinCode: string,
    participantToken: string
): Promise<Blob> {
    const response = await fetch(
        `${API_URL}/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/${path}/${id}/image`,
        {
            credentials: "include",
            headers: { "X-Quiz-Token": participantToken },
        }
    )
    if (!response.ok) throw await errorFrom(response)
    return response.blob()
}

export function createUser(user: NewUser): Promise<User> {
    return request<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(user),
    })
}

export function getQuestionBanks(): Promise<QuestionBank[]> {
    return request<QuestionBank[]>("/api/question-banks")
}

export function createQuestionBank(
    questionBank: NewQuestionBank
): Promise<QuestionBank> {
    return request<QuestionBank>("/api/question-banks", {
        method: "POST",
        body: JSON.stringify(questionBank),
    })
}

export function deleteQuestionBank(questionBankId: number): Promise<void> {
    return request<void>(`/api/question-banks/${questionBankId}`, {
        method: "DELETE",
    })
}

export function getQuestions(questionBankId: number): Promise<Question[]> {
    return request<Question[]>(
        `/api/question-banks/${questionBankId}/questions`
    )
}

export function deleteQuestion(questionId: number): Promise<void> {
    return request<void>(`/api/question-banks/questions/${questionId}`, {
        method: "DELETE",
    })
}

export function createQuestion(
    questionBankId: number,
    question: NewQuestion,
    image?: File
): Promise<Question> {
    const formData = new FormData()
    formData.set("payload", JSON.stringify(question))
    if (image) formData.set("image", image)
    return request<Question>(
        `/api/question-banks/${questionBankId}/questions`,
        {
            method: "POST",
            body: formData,
        }
    )
}

export function updateQuestion(
    questionId: number,
    question: QuestionUpdate,
    image?: File
): Promise<Question> {
    const formData = new FormData()
    formData.set("payload", JSON.stringify(question))
    if (image) formData.set("image", image)
    return request<Question>(
        `/api/question-banks/questions/${questionId}/update`,
        {
            method: "POST",
            body: formData,
        }
    )
}

export async function getQuestionImage(questionId: number): Promise<Blob> {
    async function fetchImage(allowRefresh: boolean): Promise<Blob> {
        const response = await fetch(
            `${API_URL}/api/question-banks/questions/${questionId}/image`,
            {
                credentials: "include",
                headers: accessToken
                    ? { Authorization: `Bearer ${accessToken}` }
                    : {},
            }
        )
        if (
            response.status === 401 &&
            allowRefresh &&
            (await refreshAccessToken())
        ) {
            return fetchImage(false)
        }
        if (!response.ok) throw await errorFrom(response)
        return response.blob()
    }

    return fetchImage(true)
}

export async function getChoiceImage(choiceId: number): Promise<Blob> {
    async function fetchImage(allowRefresh: boolean): Promise<Blob> {
        const response = await fetch(
            `${API_URL}/api/question-banks/choices/${choiceId}/image`,
            {
                credentials: "include",
                headers: accessToken
                    ? { Authorization: `Bearer ${accessToken}` }
                    : {},
            }
        )
        if (
            response.status === 401 &&
            allowRefresh &&
            (await refreshAccessToken())
        ) {
            return fetchImage(false)
        }
        if (!response.ok) throw await errorFrom(response)
        return response.blob()
    }

    return fetchImage(true)
}

async function downloadAuthenticatedFile(path: string): Promise<Blob> {
    async function download(allowRefresh: boolean): Promise<Blob> {
        const response = await fetch(`${API_URL}${path}`, {
            credentials: "include",
            headers: accessToken
                ? { Authorization: `Bearer ${accessToken}` }
                : {},
        })
        if (
            response.status === 401 &&
            allowRefresh &&
            (await refreshAccessToken())
        ) {
            return download(false)
        }
        if (!response.ok) throw await errorFrom(response)
        return response.blob()
    }

    return download(true)
}

export function downloadQuestionBank(questionBankId: number): Promise<Blob> {
    return downloadAuthenticatedFile(
        `/api/question-banks/${questionBankId}/export`
    )
}

export function downloadQuestionBatchExample(): Promise<Blob> {
    return downloadAuthenticatedFile("/api/question-banks/example")
}

export async function importQuestionBatch(
    file: File
): Promise<QuestionBankImportResult> {
    return request<QuestionBankImportResult>("/api/question-banks/import", {
        method: "POST",
        body: await file.text(),
    })
}
