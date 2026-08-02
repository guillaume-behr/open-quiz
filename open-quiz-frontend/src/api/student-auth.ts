import { request } from "./client"
import type { StudentAccount } from "./types"

const TOKEN_KEY = "open-quiz-student-access-token"

export function readStudentToken(): string | null {
    try {
        return sessionStorage.getItem(TOKEN_KEY)
    } catch {
        return null
    }
}

export function clearStudentSession(): void {
    try {
        sessionStorage.removeItem(TOKEN_KEY)
    } catch {
        // The in-memory portal state is cleared by its caller.
    }
}

export async function loginStudent(
    identifier: string,
    password: string
): Promise<{ student: StudentAccount; token: string }> {
    const result = await request<{
        access_token: string
        student: StudentAccount
    }>(
        "/api/student-auth/login",
        {
            method: "POST",
            body: JSON.stringify({ identifier, password }),
        },
        false
    )
    try {
        sessionStorage.setItem(TOKEN_KEY, result.access_token)
    } catch {
        // The session still works in memory if storage is unavailable.
    }
    return { student: result.student, token: result.access_token }
}

export function restoreStudent(token: string): Promise<StudentAccount> {
    return request<StudentAccount>(
        "/api/student-auth/me",
        { headers: { Authorization: `Bearer ${token}` } },
        false
    )
}
