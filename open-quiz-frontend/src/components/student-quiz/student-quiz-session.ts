const QUIZ_SESSION_STORAGE_KEY = "open-quiz-student-session"

export type StoredQuizSession = {
    joinCode: string
    studentIdentifier: string
    participantToken: string
}

export function readStoredQuizSession(): StoredQuizSession | null {
    try {
        const value = JSON.parse(
            sessionStorage.getItem(QUIZ_SESSION_STORAGE_KEY) ?? "null"
        ) as Partial<StoredQuizSession> | null

        return value &&
            typeof value.joinCode === "string" &&
            typeof value.studentIdentifier === "string" &&
            typeof value.participantToken === "string"
            ? {
                  joinCode: value.joinCode,
                  studentIdentifier: value.studentIdentifier,
                  participantToken: value.participantToken,
              }
            : null
    } catch {
        return null
    }
}

export function storeQuizSession(session: StoredQuizSession): void {
    try {
        sessionStorage.setItem(
            QUIZ_SESSION_STORAGE_KEY,
            JSON.stringify(session)
        )
    } catch {
        // The current quiz remains usable when browser storage is unavailable.
    }
}

export function clearStoredQuizSession(): void {
    try {
        sessionStorage.removeItem(QUIZ_SESSION_STORAGE_KEY)
    } catch {
        // Clearing the in-memory session must not depend on browser storage.
    }
}
