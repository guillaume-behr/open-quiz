import type { StudentAccount } from "@/api/types"

/**
 * The one place a student's identity and tokens live in the browser.
 *
 * Tokens are kept in `sessionStorage`, or in memory when the browser blocks
 * it, and never in router state: `history.state` outlives a logout, so a
 * token put there would let the next person on a shared computer press Back
 * into the previous student's session. Logging out clears everything here.
 */
export const STUDENT_TOKEN_STORAGE_KEY = "open-quiz-student-access-token"
export const QUIZ_SESSION_STORAGE_KEY = "open-quiz-student-session"
export const TRAINING_SESSION_STORAGE_KEY = "open-quiz-training-session"

export const STUDENT_STORAGE_KEYS = [
    STUDENT_TOKEN_STORAGE_KEY,
    QUIZ_SESSION_STORAGE_KEY,
    TRAINING_SESSION_STORAGE_KEY,
] as const

// Used only when sessionStorage throws (blocked by the browser): it keeps
// the session usable until the page is reloaded.
const memoryFallback = new Map<string, string>()
// The signed-in student, so pages need not fetch it again; bound to a token.
let rememberedStudent: { token: string; student: StudentAccount } | null = null

export function readStudentItem(key: string): string | null {
    try {
        return sessionStorage.getItem(key)
    } catch {
        return memoryFallback.get(key) ?? null
    }
}

export function writeStudentItem(key: string, value: string): void {
    try {
        sessionStorage.setItem(key, value)
    } catch {
        memoryFallback.set(key, value)
    }
}

function removeStudentItem(key: string): void {
    memoryFallback.delete(key)
    try {
        sessionStorage.removeItem(key)
    } catch {
        // Only the memory fallback held it.
    }
}

/** Forget every token and the signed-in student. */
export function clearStudentStorage(): void {
    for (const key of STUDENT_STORAGE_KEYS) removeStudentItem(key)
    rememberedStudent = null
}

export function rememberStudent(token: string, student: StudentAccount): void {
    rememberedStudent = { token, student }
}

/** The student signed in with this token, if this page already knows them. */
export function rememberedStudentFor(
    token: string | null
): StudentAccount | null {
    return token && rememberedStudent?.token === token
        ? rememberedStudent.student
        : null
}

export type StoredStudentSession = {
    joinCode: string
    participantToken: string
}

export function readStoredStudentSession(
    storageKey: string
): StoredStudentSession | null {
    try {
        const value = JSON.parse(
            readStudentItem(storageKey) ?? "null"
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
    writeStudentItem(storageKey, JSON.stringify(session))
}

export function clearStoredStudentSession(storageKey: string): void {
    removeStudentItem(storageKey)
}
