import { request, requestBlob, requestPage } from "./client"
import type { Page, StudentClass } from "./types"

export function getStudentClasses(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = 8
): Promise<Page<StudentClass>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<StudentClass>(`/api/classes?${params}`)
}

export async function getAllStudentClasses(): Promise<StudentClass[]> {
    const first = await getStudentClasses(1, "", "", 100)
    const remaining = await Promise.all(
        Array.from({ length: first.totalPages - 1 }, (_, index) =>
            getStudentClasses(index + 2, "", "", 100)
        )
    )
    return [first, ...remaining].flatMap((result) => result.items)
}

export function createStudentClass(
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>("/api/classes", {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function importStudentClasses(
    payload: unknown
): Promise<{ class_count: number; student_count: number }> {
    return request("/api/classes/import", {
        method: "POST",
        body: JSON.stringify(payload),
    })
}

export function downloadClassImportExample(): Promise<Blob> {
    return requestBlob("/api/classes/example")
}

export function deleteStudentClass(classId: number): Promise<void> {
    return request<void>(`/api/classes/${classId}`, { method: "DELETE" })
}

export function updateStudentClass(
    classId: number,
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>(`/api/classes/${classId}/update`, {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function assignStudentAccount(
    classId: number,
    accountId: number
): Promise<StudentClass> {
    return request<StudentClass>(
        `/api/classes/${classId}/accounts/${accountId}`,
        { method: "POST" }
    )
}

export function unassignStudentAccount(
    classId: number,
    accountId: number
): Promise<void> {
    return request<void>(`/api/classes/${classId}/accounts/${accountId}`, {
        method: "DELETE",
    })
}
