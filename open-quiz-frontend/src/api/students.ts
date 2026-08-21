import { request, requestBlob, requestPage } from "./client"
import type {
    CreatedStudentAccount,
    Page,
    StudentAccount,
    StudentCredential,
} from "./types"

export function getStudents(
    page = 1,
    search = "",
    pageSize = 12,
    classFilter = "",
    statusFilter = ""
): Promise<Page<StudentAccount>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (classFilter === "unassigned") params.set("unassigned", "true")
    else if (classFilter) params.set("class_id", classFilter)
    if (statusFilter) params.set("is_active", statusFilter)
    return requestPage<StudentAccount>(`/api/students?${params}`)
}

export async function getAllStudents(): Promise<StudentAccount[]> {
    const first = await getStudents(1, "", 100)
    const rest = await Promise.all(
        Array.from({ length: first.totalPages - 1 }, (_, index) =>
            getStudents(index + 2, "", 100)
        )
    )
    return [first, ...rest].flatMap((page) => page.items)
}

export function createStudentAccount(payload: {
    first_name: string
    last_name: string
}): Promise<CreatedStudentAccount> {
    return request<CreatedStudentAccount>("/api/students", {
        method: "POST",
        body: JSON.stringify(payload),
    })
}

export function updateStudentAccount(
    studentId: number,
    payload: {
        identifier: string
        display_name: string
        password?: string
        is_active: boolean
    }
): Promise<StudentAccount> {
    return request<StudentAccount>(`/api/students/${studentId}/update`, {
        method: "POST",
        body: JSON.stringify(payload),
    })
}

export function deleteStudentAccount(studentId: number): Promise<void> {
    return request<void>(`/api/students/${studentId}`, { method: "DELETE" })
}

export function getClassStudentCredentials(
    classId: number
): Promise<StudentCredential[]> {
    return request<StudentCredential[]>(
        `/api/students/credentials?class_id=${classId}`
    )
}

export function exportStudentCredentials(): Promise<Blob> {
    return requestBlob("/api/students/credentials/export")
}
