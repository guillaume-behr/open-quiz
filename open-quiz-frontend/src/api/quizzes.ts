import { request, requestBlob, requestPage } from "./client"
import type {
    NewQuiz,
    Page,
    Question,
    QuizAnswerReview,
    Quiz,
    QuizSession,
    StudentQuizAnswer,
    StudentQuizJoin,
    StudentQuizSession,
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
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<Quiz>(`/api/quizzes?${params}`)
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

export function getQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}`)
}

export function getActiveQuizSessions(): Promise<QuizSession[]> {
    return request<QuizSession[]>("/api/quizzes/sessions/active")
}

export function getQuizResults(page = 1): Promise<Page<QuizSession>> {
    return requestPage<QuizSession>(
        `/api/quizzes/sessions/results?page=${page}&page_size=8`
    )
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

export function deleteQuizSession(sessionId: number): Promise<void> {
    return request<void>(`/api/quizzes/sessions/${sessionId}`, {
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

export function cancelQuizSession(sessionId: number): Promise<QuizSession> {
    return request<QuizSession>(`/api/quizzes/sessions/${sessionId}/cancel`, {
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
