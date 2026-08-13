import { request, requestBlob, requestPage } from "./client"
import type {
    MakeupJoin,
    MakeupSession,
    NewQuiz,
    Page,
    Question,
    QuestionBank,
    QuizAnswerReview,
    Quiz,
    QuizSession,
    StudentQuizAnswer,
    StudentQuizJoin,
    StudentQuizSession,
    TrainingHistoryItem,
} from "./types"

export function getQuizzes(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = 8
): Promise<Page<Quiz>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        mode: "exam",
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<Quiz>(`/api/quizzes?${params}`)
}

export async function getAllQuizzes(): Promise<Quiz[]> {
    const firstPage = await getQuizzes(1, "", "", 100)
    const quizzes = [...firstPage.items]
    for (let page = 2; page <= firstPage.totalPages; page += 1) {
        quizzes.push(...(await getQuizzes(page, "", "", 100)).items)
    }
    return quizzes
}

export function getTrainingQuestionBanks(
    studentToken: string
): Promise<QuestionBank[]> {
    return request<QuestionBank[]>(
        "/api/quizzes/training",
        { headers: { Authorization: `Bearer ${studentToken}` } },
        false
    )
}

export function startTrainingQuiz(
    questionBankId: number,
    studentToken: string
): Promise<StudentQuizJoin> {
    return request<StudentQuizJoin>(
        `/api/quizzes/training/${questionBankId}/start`,
        {
            method: "POST",
            headers: { Authorization: `Bearer ${studentToken}` },
        },
        false
    )
}

export function getTrainingHistory(
    questionBankId: number,
    studentToken: string
): Promise<TrainingHistoryItem[]> {
    return request<TrainingHistoryItem[]>(
        `/api/quizzes/training/${questionBankId}/history`,
        { headers: { Authorization: `Bearer ${studentToken}` } },
        false
    )
}

export function getClassTrainingQuestionBanks(
    classId: number
): Promise<QuestionBank[]> {
    return request<QuestionBank[]>(
        `/api/quizzes/training/classes/${classId}/question-banks`
    )
}

export function updateClassTrainingQuestionBanks(
    classId: number,
    questionBanks: { question_bank_id: number; question_count: number }[]
): Promise<QuestionBank[]> {
    return request<QuestionBank[]>(
        `/api/quizzes/training/classes/${classId}/question-banks`,
        {
            method: "PUT",
            body: JSON.stringify({ question_banks: questionBanks }),
        }
    )
}

export function createQuiz(quiz: NewQuiz): Promise<Quiz> {
    return request<Quiz>("/api/quizzes", {
        method: "POST",
        body: JSON.stringify(quiz),
    })
}

export function updateQuiz(quizId: number, quiz: NewQuiz): Promise<Quiz> {
    return request<Quiz>(`/api/quizzes/${quizId}/update`, {
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

export function getMakeupSessions(): Promise<MakeupSession[]> {
    return request<MakeupSession[]>("/api/quizzes/makeup/sessions")
}

export function getMakeupQuizOptions(classId: number): Promise<Quiz[]> {
    return request<Quiz[]>(
        `/api/quizzes/makeup/quiz-options?class_id=${classId}`
    )
}

export function createMakeupSession(
    classId: number,
    quizIds: number[]
): Promise<MakeupSession> {
    return request<MakeupSession>("/api/quizzes/makeup/sessions", {
        method: "POST",
        body: JSON.stringify({ class_id: classId, quiz_ids: quizIds }),
    })
}

export function controlMakeupSession(
    sessionId: number,
    action: "start" | "pause" | "resume" | "finish" | "cancel"
): Promise<MakeupSession | undefined> {
    return request<MakeupSession | undefined>(
        `/api/quizzes/makeup/sessions/${sessionId}/${action}`,
        { method: "POST" }
    )
}

export function joinMakeupSession(
    joinCode: string,
    studentToken: string
): Promise<MakeupJoin> {
    return request<MakeupJoin>(
        "/api/quizzes/makeup/join",
        {
            method: "POST",
            headers: { Authorization: `Bearer ${studentToken}` },
            body: JSON.stringify({ join_code: joinCode }),
        },
        false
    )
}

export function selectMakeupQuiz(
    joinCode: string,
    quizId: number,
    studentToken: string
): Promise<StudentQuizJoin> {
    return request<StudentQuizJoin>(
        `/api/quizzes/makeup/${encodeURIComponent(joinCode)}/select`,
        {
            method: "POST",
            headers: { Authorization: `Bearer ${studentToken}` },
            body: JSON.stringify({ quiz_id: quizId }),
        },
        false
    )
}

export function getQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}`)
}

export function getActiveQuizSessions(): Promise<QuizSession[]> {
    return request<QuizSession[]>("/api/quizzes/sessions/active")
}

export function getQuizResults(
    page = 1,
    quizSearch = "",
    classSearch = ""
): Promise<Page<QuizSession>> {
    const params = new URLSearchParams({ page: String(page), page_size: "8" })
    if (quizSearch) params.set("quiz_search", quizSearch)
    if (classSearch) params.set("class_search", classSearch)
    return requestPage<QuizSession>(`/api/quizzes/sessions/results?${params}`)
}

export function downloadQuizResults(
    classId: number,
    quizId: number | null
): Promise<Blob> {
    const params = new URLSearchParams({ class_id: String(classId) })
    if (quizId !== null) params.set("quiz_id", String(quizId))
    return requestBlob(`/api/quizzes/sessions/results/export?${params}`)
}

export function getParticipantAnswers(
    sessionId: number,
    participantId: number
): Promise<QuizAnswerReview[]> {
    return request<QuizAnswerReview[]>(
        `/api/quizzes/sessions/${sessionId}/participants/${participantId}/answers`
    )
}

export function gradeWrittenAnswer(
    sessionId: number,
    answerId: number,
    score: number
): Promise<QuizAnswerReview> {
    return request<QuizAnswerReview>(
        `/api/quizzes/sessions/${sessionId}/answers/${answerId}/grade`,
        {
            method: "POST",
            body: JSON.stringify({ score }),
        }
    )
}

export function publishQuizGrades(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(
        `/api/quizzes/sessions/${sessionId}/publish-grades`,
        { method: "POST" }
    )
}

export function deleteQuizSession(sessionId: number): Promise<void> {
    return request<void>(`/api/quizzes/sessions/${sessionId}`, {
        method: "DELETE",
    })
}

export function deleteQuiz(quizId: number): Promise<void> {
    return request<void>(`/api/quizzes/${quizId}`, {
        method: "DELETE",
    })
}

export function startQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}/start`, {
        method: "POST",
    })
}

export function pauseQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}/pause`, {
        method: "POST",
    })
}

export function resumeQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}/resume`, {
        method: "POST",
    })
}

export function cancelQuizSession(sessionId: number): Promise<void> {
    return request<void>(`/api/quizzes/sessions/${sessionId}/cancel`, {
        method: "POST",
    })
}

export function joinQuiz(
    joinCode: string,
    studentToken: string
): Promise<StudentQuizJoin> {
    return request<StudentQuizJoin>(
        "/api/quizzes/join",
        {
            method: "POST",
            headers: { Authorization: `Bearer ${studentToken}` },
            body: JSON.stringify({ join_code: joinCode }),
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

export function leaveStudentQuiz(
    joinCode: string,
    participantToken: string
): Promise<void> {
    return request<void>(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/leave`,
        {
            method: "POST",
            headers: { "X-Quiz-Token": participantToken },
        },
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

export function getStudentQuizImage(
    path: "questions" | "choices",
    id: number,
    joinCode: string,
    participantToken: string
): Promise<Blob> {
    return requestBlob(
        `/api/quizzes/student/sessions/${encodeURIComponent(joinCode)}/${path}/${id}/image`,
        { headers: { "X-Quiz-Token": participantToken } },
        false,
        false
    )
}
