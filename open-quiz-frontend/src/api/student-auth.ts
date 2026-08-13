import {
    STUDENT_STORAGE_KEYS,
    STUDENT_TOKEN_STORAGE_KEY,
} from "@/lib/student-session-storage"
import { request } from "./client"
import type { StudentAccount, StudentQuizHistoryItem } from "./types"

export function readStudentToken(): string | null {
    try {
        return sessionStorage.getItem(STUDENT_TOKEN_STORAGE_KEY)
    } catch {
        return null
    }
}

export function clearStudentSession(): void {
    try {
        for (const key of STUDENT_STORAGE_KEYS) sessionStorage.removeItem(key)
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
        for (const key of STUDENT_STORAGE_KEYS) sessionStorage.removeItem(key)
        sessionStorage.setItem(STUDENT_TOKEN_STORAGE_KEY, result.access_token)
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

export function getStudentQuizHistory(
    token: string
): Promise<StudentQuizHistoryItem[]> {
    return request<StudentQuizHistoryItem[]>(
        "/api/quizzes/student/results",
        { headers: { Authorization: `Bearer ${token}` } },
        false
    )
}
