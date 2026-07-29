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
        clearStoredQuizSession()
        return null
    }
}

export function storeQuizSession(session: StoredQuizSession): void {
    sessionStorage.setItem(QUIZ_SESSION_STORAGE_KEY, JSON.stringify(session))
}

export function clearStoredQuizSession(): void {
    sessionStorage.removeItem(QUIZ_SESSION_STORAGE_KEY)
}
