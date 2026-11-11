import {
    clearStudentStorage,
    readStudentItem,
    rememberStudent,
    STUDENT_TOKEN_STORAGE_KEY,
    writeStudentItem,
} from "@/lib/student-session-storage"
import { request } from "./client"
import type { StudentAccount, StudentQuizHistoryItem } from "./types"

export function readStudentToken(): string | null {
    return readStudentItem(STUDENT_TOKEN_STORAGE_KEY)
}

export function clearStudentSession(): void {
    clearStudentStorage()
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
    clearStudentStorage()
    writeStudentItem(STUDENT_TOKEN_STORAGE_KEY, result.access_token)
    rememberStudent(result.access_token, result.student)
    return { student: result.student, token: result.access_token }
}

export async function logoutStudent(token: string): Promise<void> {
    try {
        await request<void>(
            "/api/student-auth/logout",
            {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            },
            false
        )
    } catch {
        // The caller still drops the token locally; it then expires by itself.
    }
}

export async function restoreStudent(token: string): Promise<StudentAccount> {
    const student = await request<StudentAccount>(
        "/api/student-auth/me",
        { headers: { Authorization: `Bearer ${token}` } },
        false
    )
    rememberStudent(token, student)
    return student
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
