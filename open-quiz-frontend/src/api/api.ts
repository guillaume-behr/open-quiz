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

export type QuestionDifficulty = "easy" | "medium" | "hard"
export type AnswerMode = "single" | "multiple"
export type CorrectionMode = "automatic" | "manual"
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
    position: number
}

export type Question = {
    id: number
    question_bank_id: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    correction_mode: CorrectionMode
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
    correction_mode: CorrectionMode
    code_language: CodeLanguage | null
    code_content: string | null
    choices: Array<{
        label: string
        is_correct: boolean
    }>
}

export type QuestionUpdate = NewQuestion & {
    remove_image: boolean
}

type TokenResponse = {
    access_token: string
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
    return new Error(body.detail ?? "Une erreur est survenue.")
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
    password: string
): Promise<TwoFactorChallenge> {
    accessToken = null
    return request<TwoFactorChallenge>(
        "/api/auth/login",
        {
            method: "POST",
            body: JSON.stringify({ username, password }),
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

export function getQuestions(questionBankId: number): Promise<Question[]> {
    return request<Question[]>(
        `/api/question-banks/${questionBankId}/questions`
    )
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

export function downloadQuestionBank(
    questionBankId: number
): Promise<Blob> {
    return downloadAuthenticatedFile(
        `/api/question-banks/${questionBankId}/export`
    )
}

export function downloadQuestionBatchExample(): Promise<Blob> {
    return downloadAuthenticatedFile("/api/question-banks/example")
}

export async function importQuestionBatch(
    questionBankId: number,
    file: File
): Promise<Question[]> {
    return request<Question[]>(
        `/api/question-banks/${questionBankId}/import`,
        {
            method: "POST",
            body: await file.text(),
        }
    )
}
