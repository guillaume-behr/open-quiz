import {
    QUIZ_SESSION_STORAGE_KEY,
    clearStoredStudentSession,
    readStoredStudentSession,
    storeStudentSession,
    type StoredStudentSession,
} from "@/lib/student-session-storage"

export function readStoredQuizSession(): StoredStudentSession | null {
    return readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)
}

export function storeQuizSession(session: StoredStudentSession): void {
    storeStudentSession(QUIZ_SESSION_STORAGE_KEY, session)
}

export function clearStoredQuizSession(): void {
    clearStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)
}
