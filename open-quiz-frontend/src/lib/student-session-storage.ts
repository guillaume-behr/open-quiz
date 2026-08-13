export const STUDENT_TOKEN_STORAGE_KEY = "open-quiz-student-access-token"
export const QUIZ_SESSION_STORAGE_KEY = "open-quiz-student-session"
export const TRAINING_SESSION_STORAGE_KEY = "open-quiz-training-session"

export const STUDENT_STORAGE_KEYS = [
    STUDENT_TOKEN_STORAGE_KEY,
    QUIZ_SESSION_STORAGE_KEY,
    TRAINING_SESSION_STORAGE_KEY,
] as const

export type StoredStudentSession = {
    joinCode: string
    participantToken: string
}

export function readStoredStudentSession(
    storageKey: string
): StoredStudentSession | null {
    try {
        const value = JSON.parse(
            sessionStorage.getItem(storageKey) ?? "null"
        ) as Partial<StoredStudentSession> | null
        return value &&
            typeof value.joinCode === "string" &&
            typeof value.participantToken === "string"
            ? {
                  joinCode: value.joinCode,
                  participantToken: value.participantToken,
              }
            : null
    } catch {
        return null
    }
}

export function storeStudentSession(
    storageKey: string,
    session: StoredStudentSession
): void {
    try {
        sessionStorage.setItem(storageKey, JSON.stringify(session))
    } catch {
        // Route state keeps the current session usable without browser storage.
    }
}

export function clearStoredStudentSession(storageKey: string): void {
    try {
        sessionStorage.removeItem(storageKey)
    } catch {
        // The caller also clears its in-memory state.
    }
}
